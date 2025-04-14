"""Use multioprocessing on the HPC system to calculate the similarity index for
fingerprints to populate fp_info.

Functions are defined for Jaccard, cosine, and Euclid similarity, but as cosine is not
used there's no way to reach it program flow wise.
"""
import multiprocessing
import os
import time
from collections import namedtuple
from contextlib import contextmanager
from functools import partial
from math import sqrt
from multiprocessing import Queue, shared_memory
from multiprocessing.managers import SharedMemoryManager
from queue import Empty

import click
import numpy as np
from pymongo import UpdateOne

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen

BIT_COUNT = np.array(
    [np.unpackbits(np.array([i], dtype=np.uint8)).sum() for i in range(256)],
    dtype=np.uint8,
)


def fp_query_info(fp_id):
    FPQuery = namedtuple("FPQuery", "class_ path query proj getter")
    fp_class = FPGen.FPClass[fp_id]
    fp_path = fp_class.fp_fields[0].path + ".ds"

    query = {
        "$and": [
            {fp_path: {"$exists": True}},
            {
                "$or": [
                    {"dsstox_sid": {"$ne": None}},
                    {"dsstox_cid": {"$ne": None}},
                ]
            },
            {
                "$or": [
                    {"fail": {"$exists": False}},
                    {"fail": None},
                ]
            },
        ]
    }

    proj = {"_id": 0, "dsstox_sid": 1, "dsstox_cid": 1, fp_path: 1}

    # Build function to get foo[a][b][c] from given "a.b.c", used to look up FP
    # c.f. get_with_mongo_path() in genraweb/lib/misc.py
    getter = lambda x: x
    for path in fp_path.split("."):
        getter = lambda x, path=path, prev=getter: prev(x).get(path, None)

    return FPQuery(class_=fp_class, path=fp_path, query=query, proj=proj, getter=getter)


def make_task_list(env):
    """Set up a Mongo collection with metadata and the task list."""
    from genraweb.resources import DB

    fp_id = env["FJ_FP_ID"]
    sel_by = env["FJ_SEL_BY"]
    batch_size = int(env["FJ_BATCH_SIZE"])
    coll = env["FJ_COLLECTION"]

    if DB[coll].count_documents({}) > 0:
        raise ValueError(f"Collection {coll} already exists.")

    # Get list of chems. FPGen.all_chem_ids() seems like an option but includes failed
    # generation records.  Will just assume we consistently use dsstox_sid or
    # dsstox_cid.

    fp_info = fp_query_info(fp_id)

    print("Getting list of chems. and FPs")
    ChemFP = namedtuple("ChemFP", "id fp")
    chems = [
        # (chem_id, bits), prefer CID for chem_ids_in_collection() call in sort_chems()
        ChemFP(
            id=i.get("dsstox_cid") or i.get("dsstox_sid"),
            fp=fp_info.getter(i),
        )
        for i in DB[fp_info.class_.fp_output_basename].find(fp_info.query, fp_info.proj)
    ]
    print(
        f"{len(chems)} chems. for '{fp_info.query}' in "
        f"{fp_info.class_.fp_output_basename}"
    )
    if not chems:
        raise Exception("No chems found")
    mode = env["FJ_SIM_MODE"]
    in_filter, chems = sort_chems(chems, sel_by)

    bit_names = sorted(fp_info.class_.bit_names())
    bit_dict = {i: "0" for i in bit_names}
    if mode == "jaccard":
        # "00010011000100" string for attribute presence / absence Jaccard FP
        data_func = lambda bit_dict, chem: "".join(
            (bit_dict.copy() | {j: "1" for j in chem.fp}).values()
        )
    else:
        # List of real numbers for cosine/euclid similarity based FP
        # Paranoid iteration to avoid any key,value ordering issues in source data.
        data_func = lambda bit_dict, chem: [chem.fp[k] for k in bit_dict]

    rows = 0
    for block_i, chems_block in enumerate(
        (chems[i : i + batch_size] for i in range(0, len(chems), batch_size))
    ):
        print(f"Block {block_i+1} of {len(chems) // batch_size + 1}")
        DB[coll].insert_one(
            {
                "block_i": block_i,
                "chems": [i.id for i in chems_block],
                # Many times faster than "".join("1" if ... else "0" for i in bit_names)
                "bits": [data_func(bit_dict, chem) for chem in chems_block],
                "done": False,
            }
        )
        rows += len(chems_block)

    DB[coll].insert_one(
        {
            "metadata": True,
            "mode": mode,
            "log": [f"{time.asctime()} This collection created"],
            "fp_id": fp_id,
            "sel_by": sel_by,
            "batch_size": batch_size,
            "bit_names": bit_names,
            "max_block": block_i,
            "rows": rows,
            "in_filter": in_filter,
        }
    )
    DB[coll].create_index("block_i")
    DB[coll].create_index("chem_id")  # for upserts later


def sort_chems(chems: list, sel_by: str) -> tuple[int, list[str]]:
    """If filter (sel_by) specified, sort chems in filter collection first.
    Returns number of chems in filter collection and sorted list of chems.
    """
    if sel_by == "no_filter":
        chems.sort()
        return len(chems), chems

    # Copied from mongo_NN.py
    print(
        FPGen.FPClass[sel_by].fp_output_basename if sel_by in FPGen.FPClass else sel_by
    )
    chem_ids_filter = ChemID.chem_ids_in_collection(
        FPGen.FPClass[sel_by].fp_output_basename if sel_by in FPGen.FPClass else sel_by
    )
    chem_ids_filter = set(chem_ids_filter)  # for fast lookup
    print(len(chem_ids_filter), "chems in filter collection.")
    # (in_filter, chem_id, (chem_id, bits))
    sorter = [(i[0] in chem_ids_filter, i[0], i) for i in chems]
    sorter.sort(key=lambda x: (not x[0], x[1]))  # sort in filter to beginning
    chems = [i[2] for i in sorter]
    return sum(1 for i in sorter if i[0]), chems


def load_array(block, mem, metadata):
    print(f"Loading block {block['block_i']}      ", end="\r")
    with get_array(mem, metadata) as array:
        start_row = block["block_i"] * metadata["batch_size"]
        # print(start_row, start_row + metadata["batch_size"])
        if metadata["mode"] == "jaccard":
            for row in range(start_row, start_row + metadata["batch_size"]):
                if row >= metadata["rows"]:
                    break  # Last block may not be full
                array[row] = np.packbits(
                    [int(i) for i in block["bits"][row - start_row]]
                )
        else:
            array[start_row : start_row + len(block["bits"]), :] = block["bits"]


def build_array(smm: SharedMemoryManager, env):
    """Build array of FP bits for whole collection."""
    # List of all chems. in collection
    from genraweb.resources import DB

    print("Building array.")
    coll = env["FJ_COLLECTION"]

    metadata = DB[coll].find_one({"metadata": True})
    bits = len(metadata["bit_names"])
    if metadata["mode"] == "jaccard":
        bytes = bits // 8 + (1 if bits % 8 else 0)
        metadata["cols"] = bytes
        metadata["type"] = np.uint8
    elif metadata["mode"] in ("cosine", "euclid"):
        bytes = bits * 4 * 4  # FIXME: 4 float32s
        metadata["type"] = np.float32
        metadata["cols"] = 4  # FIXME
    else:
        raise Exception(f"Unknown mode {metadata['mode']}")
    size = metadata["rows"] * bytes
    shm = smm.SharedMemory(size=size)
    # array = np.ndarray((metadata["rows"], bytes), dtype=np.uint8, buffer=shm.buf)
    chems = []
    blocks = []
    for block in DB[coll].find({"block_i": {"$exists": True}}).sort("block_i"):
        chems.extend(block["chems"])
        blocks.append({"block_i": block["block_i"], "bits": block["bits"]})

    print(f"{len(blocks)} blocks to load.")
    with multiprocessing.Pool(int(os.environ["FJ_PROCS"])) as p:
        p.map(
            partial(
                load_array,
                mem=shm.name,
                metadata=metadata,
            ),
            blocks,
        )
    p.join()
    print()

    # Some metrics need normalization etc.
    if metadata["mode"] == "euclid":
        with get_array(shm.name, metadata) as array:
            mins = array.min(axis=0)
            maxs = array.max(axis=0)
            array[:] = (array - mins) / (maxs - mins)
            mins = array.min(axis=0)
            maxs = array.max(axis=0)
            assert mins.min() >= 0, mins
            assert mins.max() <= 1, mins
            assert maxs.min() >= 0, maxs
            assert maxs.max() <= 1, maxs

    print(f"{len(chems)} chems., {len(metadata['bit_names'])} bits.")
    return {
        "metadata": metadata,
        "chems": chems,
        "shm": shm,
    }


def reserve_blocks(env):
    """Reserve blocks for each process.
    db.COLLECTION.updateMany({}, {$unset:{reserved: 1}}) to reset.
    """
    from genraweb.resources import DB

    coll = env["FJ_COLLECTION"]
    procs = int(env["FJ_PROCS"])
    bpp = int(env["FJ_BLOCKS_PER_PROC"])
    avail = [
        i["block_i"]
        for i in DB[coll]
        .find(
            {"reserved": {"$ne": True}, "block_i": {"$ne": None}},
            {"_id": 0, "block_i": 1},
        )
        .limit(procs * bpp)
    ]
    print(f"Wanted {procs * bpp} blocks, got {len(avail)}")
    if not avail:
        exit(0)
    DB[coll].update_many(
        {"block_i": {"$in": list(avail)}}, {"$set": {"reserved": True}}
    )
    # DB.client.close()
    # del DB  # Try and stop mongo complaining about pre-fork connections
    return avail


@contextmanager
def get_array(mem, metadata):
    memory = shared_memory.SharedMemory(name=mem)
    rows = metadata["rows"]
    yield np.ndarray(
        (rows, metadata["cols"]), dtype=metadata["type"], buffer=memory.buf
    )
    memory.close()


def jaccard_calc(array, copy, in_filter, output, out_of, row, zero_sim):
    OR, AND = 0, 1
    np.bitwise_or(in_filter, array[row], copy)
    out_of[:, OR] = BIT_COUNT[copy].sum(axis=1)
    np.bitwise_and(in_filter, array[row], copy)
    out_of[:, AND] = BIT_COUNT[copy].sum(axis=1)
    # make no bit chems. be 0/1 instead of 0/0
    out_of[out_of[:, OR] == 0, :] = zero_sim
    output[:] = out_of[:, AND] / out_of[:, OR]


def cosine_calc(array, copy, in_filter, output, out_of, row, zero_sim):
    """Cosine distance calc.

    scipy.spatial.distance.cosine only works with two 1d arrays, so use numpy
    directly
    """
    # from https://stackoverflow.com/questions/32688866
    # WARNING: unused but would need to account for in_filter if used
    A = array[row]
    A.shape = (1, len(A))
    B = array
    dots = np.dot(A, B.T)
    l2norms = np.sqrt(((A**2).sum(1)[:, None]) * ((B**2).sum(1)))
    output[:] = 1 - (1 - (dots / l2norms) + 1) / 2


def euclid_calc(array, copy, in_filter, output, out_of, row, zero_sim):
    A = array[row]
    bits = len(A)
    A.shape = (1, bits)
    output[:] = 1 - np.sqrt(np.power(in_filter - A, 2).sum(axis=1)) / sqrt(bits)


def process_blocks(
    blocks: list[int],  # List of blocks to process
    env,
    mem: str,  # Shared memory name
    chems: list[str],  # List of chems
    metadata: dict,  # Metadata
    queue: Queue,  # Queue to send results to
):
    rows = metadata["rows"]
    start = time.time()
    last = start
    done = 0
    chem_lu = np.array(chems)
    # Allocate arrays and reuse assuming that's quicker
    out_of = np.zeros((metadata["in_filter"], 2), dtype=np.uint32)
    # "jaccard" or some other distance metric scalar real value
    similarity = np.zeros(metadata["in_filter"], dtype=np.float32)
    zero_sim = np.array([1, 0])
    calc_func = jaccard_calc if metadata["mode"] == "jaccard" else euclid_calc
    with get_array(mem, metadata) as array:
        in_filter = array[: metadata["in_filter"]]
        copy = np.zeros(in_filter.shape, dtype=np.uint8)
        for block_cnt, block in enumerate(blocks):
            start_row = block * metadata["batch_size"]
            for row in range(start_row, min(rows, start_row + metadata["batch_size"])):
                calc_func(array, copy, in_filter, similarity, out_of, row, zero_sim)

                # Save 105, fp_info doesn't include self, so would need 101, handle in
                # post-processing.
                top = np.argsort(similarity)[::-1][:105]
                nn = chem_lu[top]
                # nn = [chems[i] for i in top]
                sims = similarity[top]
                done += 1
                if time.time() - last >= 60:
                    last = time.time()
                    print(f"{done/(last-start):g} per sec.")
                queue.put(
                    {
                        "filter": {"chem_id": chems[row]},
                        "update": {
                            "$set": {"nn": list(nn), "sims": [float(i) for i in sims]}
                        },
                        "upsert": True,
                    }
                )
            queue.put(
                {
                    "filter": {"block_i": block},
                    "update": {"$set": {"done": True}},
                    "upsert": False,
                }
            )
            # print(f"{block_cnt}/{len(blocks)}")


def process_queue(env, queue):
    from genraweb.resources import DB

    written = 0
    waited = 0
    last = waited
    todo = []
    while True:
        try:
            item = queue.get(timeout=1)
        except Empty:
            waited += 1
            continue
        if item is None:
            print("Saw None, writing todo and quitting")
            DB[env["FJ_COLLECTION"]].bulk_write(todo)
            break
        written += 1
        todo.append(UpdateOne(item["filter"], item["update"], upsert=item["upsert"]))
        if time.time() - last >= 10:
            print(f"Wrote {written} records, waited {waited} seconds.")
            last = time.time()
            waited = 0
            DB[env["FJ_COLLECTION"]].bulk_write(todo)
            todo = []


def log(env, text=None):
    """Log text in metadata record."""
    # Log start of run
    from genraweb.resources import DB

    coll = env["FJ_COLLECTION"]
    metadata = DB[coll].find_one({"metadata": True})
    if metadata is None:
        print("No metadata record found - no collection?")
        return
    if text and text.strip():
        DB[coll].update_one(
            {"_id": metadata["_id"]}, {"$push": {"log": time.asctime() + " " + text}}
        )
        metadata = DB[coll].find_one({"metadata": True})
    print("\nMetadata log messages:")
    print("\n".join(metadata.get("log", ["EMPTY"])))
    print()
    metadata = DB[coll].find_one({"metadata": True})
    # DB.client.close()
    # del DB  # Try and stop mongo complaining about pre-fork connections


def load_to_fp_info(env, coll):
    """Load results into fp_info collection.
    This function mostly verifies that the collection is ready and the
    user is sure before calling do_fp_info_load().
    This function will delete existing data if the user requests it.
    """
    if not coll:
        coll = env["FJ_COLLECTION"]
    else:
        coll = coll[0]
    from genraweb.resources import DB

    env = env | {"FJ_COLLECTION": coll}
    log(env)

    metadata = DB[coll].find_one({"metadata": True})
    undone = DB[coll].find_one({"done": {"$ne": True}, "block_i": {"$ne": None}})
    if undone:
        print("Not all done, aborting")
        exit(1)
    FP_INFO = env.get("GENRA_FP_INFO_COLLECTION", "fp_info")
    print(f"Working on `fp_info` collection {FP_INFO}")
    print("Set GENRA_FP_INFO_COLLECTION to change")
    if FP_INFO == "fp_info":
        print("WARNING: working on 'live' fp_info collection")
    print("Continue? (y/n)")
    if input().lower() != "y":
        exit(1)

    print(
        f"Drop ALL existing records for {metadata['fp_id']} "
        f"filtered by {metadata['sel_by']}? (y/n)"
    )
    if input().lower() != "n":
        DB[FP_INFO].update_many(
            {}, {"$unset": {f"{metadata['fp_id']}.{metadata['sel_by']}": 1}}
        )
        log(env, "Dropped existing records")
    else:
        print("Not dropping existing records")
    print("Continue with load operation? (y/n)")
    if input().lower() != "y":
        exit(1)

    do_fp_info_load(env, coll)


def do_fp_info_load(env, coll):
    """Actual loading of data after verification by load_to_fp_info()."""
    from genraweb.resources import DB

    metadata = DB[coll].find_one({"metadata": True})
    FP_INFO = env.get("GENRA_FP_INFO_COLLECTION", "fp_info")
    log(env, "Loading fingerprints to fp_info started")
    last = time.time()
    done = 0
    todo = []
    DB[FP_INFO].create_index("dsstox_sid")
    DB[FP_INFO].create_index("dsstox_cid")
    for chem in DB[coll].find({"chem_id": {"$ne": None}}):
        nn = chem["nn"]
        sims = chem["sims"]
        try:  # Remove self
            nn_i = nn.index(chem["chem_id"])
            nn.pop(nn_i)
            sims.pop(nn_i)
        except ValueError:
            pass
        nn = nn[:100]  # Only keep top 100
        sims = sims[:100]
        todo.append(
            UpdateOne(
                {
                    "$or": [
                        {"dsstox_sid": chem["chem_id"]},
                        {"dsstox_cid": chem["chem_id"]},
                    ]
                },
                {
                    "$set": {
                        f"{metadata['fp_id']}.{metadata['sel_by']}": {
                            "from_fj": True,
                            "n": len(chem["nn"]),
                            "max_s0": max(chem["sims"] or [0]),
                            "chem_ids": chem["nn"],
                            "similarities": chem["sims"],
                        },
                        "dsstox_sid"
                        if "SID" in chem["chem_id"]
                        else "dsstox_cid": chem["chem_id"],
                    }
                },
                upsert=True,
            )
        )
        done += 1
        if time.time() - last >= 10 or len(todo) >= 10000:
            print(f"Writing {len(todo)} records {time.asctime()} ({chem['chem_id']})")
            if todo:
                DB[FP_INFO].bulk_write(todo)
            print(f"Write complete, {done} records written")
            todo = []
            last = time.time()

    if todo:
        DB[FP_INFO].bulk_write(todo)

    log(env, "Loading fingerprints to fp_info completed")


def run_env(env):
    index = "SLURM_ARRAY_TASK_ID"
    if index in env:
        sleep = int(env[index]) * 10
        print(f"Sleeping {sleep} seconds for {index} {env[index]}.")
        print(
            "\n".join(
                f"{k} {env[index]} {v}" for k, v in env.items() if k.startswith("SLURM")
            )
        )
        time.sleep(sleep)

    procs = int(env["FJ_PROCS"])
    blocks = reserve_blocks(env)
    with SharedMemoryManager() as smm:
        data = build_array(smm, env)
        # Spread blocks across processes, we may not have FJ_PROCS * FJ_BLOCKS_PER_PROC
        block_lists = [
            [blocks[i] for i in range(j, len(blocks), procs)] for j in range(procs)
        ]
        block_lists = [i for i in block_lists if i]
        procs = len(block_lists)  # if some block lists are empty after spreading
        queue = multiprocessing.Manager().Queue()
        thread = multiprocessing.Process(target=process_queue, args=(env, queue))
        thread.start()
        with multiprocessing.Pool(procs) as p:
            p.map(
                partial(
                    process_blocks,
                    env=env,
                    mem=data["shm"].name,
                    chems=data["chems"],
                    metadata=data["metadata"],
                    queue=queue,
                ),
                block_lists,
            )
        p.join()  # Wait for all workers to finish
        queue.put(None)  # Sentinel to stop queue processing thread
        thread.join()  # Wait for queue to empty


def show_mongo_cmds():
    from genraweb.resources import DB

    opts = {
        "drop": ".drop()",
        "check_metadata": ".countDocuments({metadata: {$exists: 1}})",
        "delete_chem_id": ".deleteMany({chem_id: {$exists: 1}})",
        "undo_all": ".updateMany({block_i:{$ne:null}}, "
        "{$set:{reserved:false, done:false}})",
        "unreserve_failed": ".updateMany({block_i:{$ne:null}, done:{$ne:true}}, "
        "{$set:{reserved:false, done:false}})",
        "count_chem": ".countDocuments({chem_id: {$exists: 1}})",
        "count_block": ".countDocuments({block_i: {$exists: 1}})",
        "count_done": ".countDocuments({block_i: {$exists: 1}, done: true})",
        "count_not_done": ".countDocuments({block_i: {$exists: 1}, done: {$ne: true}})",
        "count_reserved": ".countDocuments({block_i: {$exists: 1}, reserved: true})",
        "last_log": ".findOne({metadata:true}, {_id:0, log:{$last:'$log'}})",
    }
    for k, v in opts.items():
        print(f"{k}: {v}")
    choice = input("Enter option: ")

    fjs = [i for i in DB.list_collection_names() if i.startswith("fj_")]
    fjs.sort()
    print()
    for name in fjs:
        print(f"db.{name}" + opts[choice])
    print()


def find_missing(env):
    from genraweb.resources import DB

    ids = set(
        i["chem_id"]
        for i in DB[env["FJ_COLLECTION"]].find(
            {"chem_id": {"$exists": 1}}, {"chem_id": 1, "_id": 0}
        )
    )
    ids = set(ids)  # Faster lookup
    for block in DB[env["FJ_COLLECTION"]].find({"block_i": {"$exists": 1}}):
        msg = f"Block {block['block_i']} missing:\n"
        for chem_i, chem in enumerate(block["chems"]):
            if chem not in ids:
                print(f"{msg} {chem_i} {chem}")
                msg = ""


@click.group()
def cli():
    pass


@cli.command("mongo")
def mongo():
    """Print mongosh commands for fj_ collection inspection / maintenance."""
    show_mongo_cmds()


@cli.command("log")
@click.argument("log_text", default=None, nargs=-1)
def show_log(log_text):
    """Show collection log, add text to collection log."""
    log(os.environ, " ".join(log_text))


@cli.command("load")
@click.argument("load", nargs=-1)
def load(load):
    """Load fingerprints to fp_info collection."""
    load_to_fp_info(os.environ, load)


@cli.command("init")
def init():
    """Initialize fj_ collection, creates blocks of work to do."""
    make_task_list(os.environ)


@cli.command("missing")
def missing():
    """Find missing fingerprints in fj_ collection."""
    find_missing(os.environ)


@cli.command("run")
def run():
    """Start a worker which pulls work from the DB."""
    run_env(dict(os.environ))


if __name__ == "__main__":
    cli()
