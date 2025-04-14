"""Utilities for NN precalc. See precalc/precalc.py for more documentation."""
import datetime
import pathlib
from multiprocessing.dummy import Pool as ThreadPool
from time import time

import numpy as np
import pandas as pd
from pymongo import UpdateOne
from sklearn.neighbors import NearestNeighbors

from genraweb.defs import FILTER
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO
from genraweb.lib.fp.genfputils import get_ds_order
from genraweb.lib.logging import logger
from genraweb.resources import DB

try:
    import cPickle as pickle
except ModuleNotFoundError:
    import pickle


COL = FPGen.fp_collection_names()

NUM_NEIGHBORS = 100

# If USE_SCIKIT_MULTIPROCESSING=False in precalc/precalc.py, see N_PRECALC_JOBS in that
# file; this variable should be set to 1 so that container logs won't be clogged with
# scikit warnings
N_JOBS = 1

# ### Utilities for creating, running, and saving sklearn components


def measure_runtime(func):
    """Decorator that appends runtime (seconds) to return object of method.
    This will break code that unpacks the function return object as tuple immediately,
    i.e.: res1, res2 = some_funct()"""

    def wrapper(*args, **kwargs):
        now = time()
        result = func(*args, **kwargs)
        runtime = time() - now
        return result, runtime

    return wrapper


def runtime_str(runtime):
    """Convert seconds into readable time string"""
    if runtime is None:
        return str(None)
    return str(datetime.timedelta(seconds=round(runtime)))


def write_pickle(fname, data, runtime=None):
    with open(fname, "wb") as f:
        pickle.dump({"runtime": runtime, "data": data}, f)


def read_pickle(fname):
    with open(fname, "rb") as f:
        data = pickle.load(f)
    return data["data"], data["runtime"]


def start_print(fname):
    logger.info(f"\nstarting {fname}...")


def finish_print(fname, runtime=None):
    runtime = runtime_str(runtime)
    logger.info(f"...finished {fname} in {runtime}\n")


def get_fname(fp_id, sel_by, model_type, suffix=""):
    return f"models/{fp_id}/{model_type}_{sel_by}{'_'+suffix if suffix else ''}.pkl"


@measure_runtime
def get_FP_df(sel_by, fp_class):
    """Returns FP dataframe, with row index chem_id and column index fpds.
    Uses `sel_by` as filter aggregation level.
    Standardizes the columns (FP bits), and sorts rows by number of assay data points
    to allow for tie breaking behavior. The inner method does most of work, and the
    outer method does the logic for tie breakers.
    """

    def get_FP_df_inner(sel_by, collection, path):
        if sel_by is None or sel_by == "no_filter":
            search = {}
        else:
            search = ChemID.chem_id_search(ChemID.chem_ids_in_collection(COL[sel_by]))
        proj = ChemID.chem_id_proj()
        proj["fpds"] = f"${path}.ds"

        ds_order = get_ds_order(fp_class, collection, path)

        return (
            pd.DataFrame(DB[collection].find(search, proj))
            .explode("fpds")
            .pivot_table(index="chem_id", columns="fpds", aggfunc="size", fill_value=0)
            .reindex(columns=ds_order, fill_value=0)
            .sort_index()
        )

    fp_fields = fp_class.fp_fields[0]
    df = get_FP_df_inner(sel_by, fp_fields.collection, fp_fields.path)

    if sel_by == "no_filter":
        tiebreak_sel_by = "tox_txrf"
    else:
        tiebreak_sel_by = sel_by

    # sort by number of data points for tie breaker
    tiebreak_fp_class = FPGen.FPClass[tiebreak_sel_by]
    tiebreak_collection = tiebreak_fp_class.fp_fields[0].collection
    tiebreak_path = tiebreak_fp_class.fp_fields[0].path
    tiebreak_df = get_FP_df_inner(tiebreak_sel_by, tiebreak_collection, tiebreak_path)
    sorted_indices = tiebreak_df.sum(axis=1).sort_values(ascending=False).index
    if sel_by == "tox_txrf":
        # toxref has "negatives" that should be counted for tiebreakers too
        neg_fp_fields = tiebreak_fp_class.fp_fields[1]  # i.e., tox_fp2.fp_neg
        neg_df = get_FP_df_inner(
            tiebreak_sel_by, neg_fp_fields.collection, neg_fp_fields.path
        )
        sorted_indices = (
            tiebreak_df.sum(axis=1)
            .add(neg_df.sum(axis=1), fill_value=0)
            .sort_values(ascending=False)
            .index
        )
    # remove chems not in FP add chems not in tiebreak filter
    sorted_indices = [idx for idx in sorted_indices if idx in df.index] + sorted(
        set(df.index) - set(sorted_indices)
    )
    return df.reindex(labels=sorted_indices)


@measure_runtime
def fit_model(X_df, fp_class):
    # certain FPs (thus far only bio_htpp_MCF7?) have too few chems
    # NUM_NEIGHBORS+1 to account for target itself being included
    size = min(NUM_NEIGHBORS + 1, X_df.shape[0])
    model = NearestNeighbors(
        n_neighbors=size, algorithm="ball_tree", metric="jaccard", n_jobs=N_JOBS
    )
    model.fit(X_df)
    return model


@measure_runtime
def calc_nns(model, X):
    model = model.set_params(n_jobs=N_JOBS)
    return model.kneighbors(X, return_distance=True)


@measure_runtime
def calc_nns_graph(model, X):
    model = model.set_params(n_jobs=N_JOBS)
    return model.kneighbors_graph(X, mode="distance")


def save_model(model_type, fp_id, sel_by, model_func, *args, redo=False, suffix=""):
    """Saves a "model", which is any one of components that are required
    to populate fp_info. `model_type` is a string shorthand component type:
    - "df": raw FP dataframe
    - "model": the sklearn nearest neighbor, ball tree fitted model
    - "nns": tuples of numpy array of neighbors and similarities for each target chem
    - "nns_graph": sparse symmetric matrix of similarities"""
    fname = get_fname(fp_id, sel_by, model_type, suffix)
    file = pathlib.Path(fname)
    if file.is_file() and not redo:
        print(f"\nloading existing data for {fname}...\n")
        model, runtime = read_pickle(fname)
    else:
        start_print(fname)
        model, runtime = model_func(*args)
        finish_print(fname, runtime)
        write_pickle(fname, model, runtime=runtime)
    return model, runtime


# ### utilities for uploading to mongo

# number of threads
NUM_THREADS = 5
# chunk size to bulk_write to pymongo
CHUNK_SIZE = 10000


def get_model(fname, purpose):
    file = pathlib.Path(fname)
    if not file.is_file():
        raise Exception(f"{fname} needed for {purpose}.")
    return read_pickle(fname)[0]


def chunkify(df, chunk_size):
    return [df[i : i + chunk_size] for i in range(0, df.shape[0], chunk_size)]


def update_fp_info(fp_id, sel_by, df_target=None, suffix="", nns=None):
    """Updates to the fp_info collection"""

    # Set the indexes for cid/sid - if they already exist, nothing happens.
    # Without indexes, this mongo upload will take too long.
    DB[FP_INFO].create_index("dsstox_cid")
    DB[FP_INFO].create_index("dsstox_sid")

    now = time()
    if df_target is None:
        df_target = get_model(
            get_fname(fp_id, "no_filter", "df", suffix), "target chem_id refernce"
        )

    print(f"\nstarting upload to mongo fp={fp_id}, sel_by={sel_by}")

    df = get_model(
        get_fname(fp_id, sel_by, "df"), "neighborhood chem_id reference"
    )  # no suffix because same DF for index consistency
    if nns is None:
        nns = get_model(get_fname(fp_id, sel_by, "nns", suffix), "neighborhood data")

    distances = nns[0]
    # model uses integer indices
    iloc_indices = nns[1]

    def write_chunk_generator(chunk_df):
        for chem_id in chunk_df.index:
            idx_target = df_target.index.get_loc(chem_id)

            chem_distances = distances[idx_target]
            chem_iloc_indices = iloc_indices[idx_target]

            if chem_id in df.index:
                # if target included in neighborhood, remove from consideration
                pop_idx = np.where(chem_iloc_indices == df.index.get_loc(chem_id))[0]
                chem_distances = np.delete(chem_distances, pop_idx)
                chem_iloc_indices = np.delete(chem_iloc_indices, pop_idx)

            # round so we don't have to deal with numpy's float64 decimal issues
            # => sometimes 0.1 becomes 0.0999999..., which is problematic for the
            # default threshold of s0=0.1 since Mongo will evaluate as 0.09999 < 0.1 and
            # incorrectly dis-include
            similarities = np.around(1 - chem_distances[:NUM_NEIGHBORS], 10)

            yield UpdateOne(
                {
                    "$or": [
                        {"dsstox_cid": chem_id},
                        {"dsstox_sid": chem_id},
                    ],
                },
                {
                    "$set": {
                        # upsert with $or doesn't insert the selection keys
                        "dsstox_cid" if "CID" in chem_id else "dsstox_sid": chem_id,
                        f"{fp_id}.{sel_by}": {
                            "n": len(np.where(similarities > 0)[0]),
                            # `np.where(...)` returns tuple, so take the first (index=0)
                            # of tuple result
                            "chem_ids": list(
                                df.iloc[chem_iloc_indices[:NUM_NEIGHBORS]].index
                            ),
                            "similarities": list(similarities),
                        },
                    },
                },
                upsert=True,
            )

    def write_chunk(chunk_df):
        return DB[FP_INFO].bulk_write(
            list(write_chunk_generator(chunk_df)), ordered=False
        )

    # set up the threads, if more than CHUNK_SIZE
    num_threads = NUM_THREADS if len(df_target.index) > CHUNK_SIZE else 1
    num_threads = 1  # it doesn't seem to make much difference
    pool = ThreadPool(num_threads)
    # split up the dataframe into a list of CHUNK_SIZE dataframes
    df_chunks = chunkify(df_target, CHUNK_SIZE)
    # have the threads work on the chunks
    pool.map(write_chunk, df_chunks)
    pool.close()
    pool.join()
    runtime = time() - now
    print(
        f"...finished uploading to mongo fp={fp_id}, sel_by={sel_by}, "
        f"took {runtime_str(runtime)}\n"
    )


def calc_max_s0(DB):
    """Calculates the max s0 for each fp_id and sel_by combination in fp_info.
    Keeping this but see commit msg. - not really used.
    """
    set_count = 0
    done = 0
    last = 0
    print("Counting documents...")
    todo = DB[FP_INFO].count_documents({})
    start = time()
    for chem in DB[FP_INFO].find():
        done += 1
        for fp_id in FPGen.FPClass:
            for sel_by in FILTER:
                if fp_id in chem and sel_by in chem[fp_id]:
                    if "similarities" in chem[fp_id][sel_by]:
                        max_s0 = max(chem[fp_id][sel_by]["similarities"])
                        DB[FP_INFO].update_one(
                            {"_id": chem["_id"]},
                            {"$set": {f"{fp_id}.{sel_by}.max_s0": max_s0}},
                            upsert=False,
                        )
                        set_count += 1
        if time() - last > 10:
            remaining = (time() - start) / done * (todo - done) / 3600
            print(f"{done} done, {set_count} set, {remaining:.2f} hours remaining")
            last = time()
