"""Count FP by sel_by in fp_info.

Usage: python fp_info_info.py [<fp_info collection name>]

Defaults to summarizing `fp_info`.

Example output:

    tox_txrf
           0 chm_mrgn
           0 chm_httr
           0 chm_ct
        9329 bio_txct
        1088 tox_txrf
         270 bio_htpp_MCF7
        1450 bio_htpp_U2OS
    no_filter
           0 chm_mrgn
           0 chm_httr
           0 chm_ct
        9329 bio_txct
        1088 tox_txrf
         270 bio_htpp_MCF7
        1450 bio_htpp_U2OS

Not related to other code in this folder.
"""
import os
import sys
from collections import defaultdict, namedtuple
from multiprocessing import Pool, current_process

import pandas as pd

from genraweb.resources import DB

Block = namedtuple("Block", "collection query projection start end")

FP_INFO = os.environ.get("GENRA_FP_INFO_COLLECTION", "fp_info")

if len(sys.argv) > 1:
    fp_info_name = sys.argv[1]
else:
    fp_info_name = FP_INFO

print(f"\n\nUsing {fp_info_name} for fp_info collection")


def iterate_by_chunks(collection, chunksize=1, start_from=0, query={}, projection={}):
    # https://stackoverflow.com/a/54277118/1072212
    print("Counting records")
    if query:
        count = DB[collection].count_documents(query)
    else:
        count = DB[collection].estimated_document_count()
    chunks = range(start_from, count, int(chunksize))
    num_chunks = len(chunks)
    print(f"Counting complete, {count}")
    for i in range(1, num_chunks + 1):
        if i < num_chunks:
            yield Block(collection, query, projection, chunks[i - 1], chunks[i])
        else:
            yield Block(collection, query, projection, chunks[i - 1], chunks.stop)


def proc_block(data):
    count = defaultdict(int)
    populated = defaultdict(int)
    done = 0
    for rec in DB[data.collection].find(data.query, data.projection)[
        data.start : data.end
    ]:
        for key0 in rec:
            if isinstance(rec[key0], dict):
                for key1 in rec[key0]:
                    if isinstance(rec[key0][key1], dict):
                        count[(key0, key1)] += 1
                        populated[(key0, key1)] += 1 if rec[key0][key1].get("n") else 0
        done += 1
        if done % 10_000 == 0:
            print(done, current_process().name)
    return count, populated


_count = {  # for development
    ("chm_aim", "bio_txct"): 1756860,
    ("chm_aim", "no_filter"): 1756860,
    ("chm_aim", "pesticideRAC"): 1756860,
    ("chm_aim", "tox_txrf"): 1756860,
    ("chm_ct", "bio_txct"): 1756860,
    ("chm_ct", "no_filter"): 1756860,
    ("chm_ct", "pesticideRAC"): 1756860,
    ("chm_ct", "tox_txrf"): 1756860,
    ("chm_httr", "bio_txct"): 1696674,
    ("chm_httr", "no_filter"): 1696674,
    ("chm_httr", "pesticideRAC"): 1696674,
    ("chm_httr", "tox_txrf"): 1696674,
    ("chm_mrgn", "bio_txct"): 1696674,
    ("chm_mrgn", "no_filter"): 1696674,
    ("chm_mrgn", "pesticideRAC"): 1696674,
    ("chm_mrgn", "tox_txrf"): 1696674,
    ("chm_phch", "bio_txct"): 826809,
    ("chm_phch", "no_filter"): 826809,
    ("chm_phch", "pesticideRAC"): 826809,
    ("chm_phch", "tox_txrf"): 826809,
    ("chm_pfas", "tox_txrf"): 13007,
    ("chm_pfas", "bio_txct"): 13007,
    ("chm_pfas", "bio_pest"): 13007,
    ("chm_pfas", "no_filter"): 13007,
    ("bio_txct", "tox_txrf"): 9519,
    ("bio_htpp_MCF7", "tox_txrf"): 237,
    ("bio_htpp_MCF7", "bio_txct"): 237,
    ("bio_htpp_U2OS", "tox_txrf"): 1367,
    ("bio_htpp_U2OS", "bio_txct"): 1367,
    ("bio_txct", "bio_txct"): 9373,
    ("bio_txct_ATG", "tox_txrf"): 3984,
    ("bio_txct_ATG", "bio_txct"): 3984,
    ("bio_txct_BSK", "tox_txrf"): 1705,
    ("bio_txct_BSK", "bio_txct"): 1705,
    ("bio_txct_NVS", "tox_txrf"): 2917,
    ("bio_txct_NVS", "bio_txct"): 2917,
    ("tox_txrf", "tox_txrf"): 1046,
    ("tox_txrf", "bio_txct"): 1046,
}


def show(count):
    """Show crosstabed counts."""
    print(
        pd.crosstab(
            (i[0] for i in count),
            (i[1] for i in count),
            count.values(),
            aggfunc=sum,
            colnames=["Filter"],
            rownames=["Fingerprint"],
        )
    )


def main():
    count = defaultdict(int)
    populated = defaultdict(int)
    threads = 5
    with Pool(threads) as pool:
        for count_, populated_ in pool.map(
            proc_block,
            iterate_by_chunks(collection=fp_info_name, chunksize=2_000_000 // threads),
        ):
            for key in count_:
                count[key] += count_[key]
                populated[key] += populated_[key]

    for key in sorted(count):
        print(key, count[key])

    show(count)
    show(populated)


if __name__ == "__main__":
    main()
