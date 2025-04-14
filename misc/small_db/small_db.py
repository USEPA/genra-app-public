"""
small_db.py - make smll DB for security scan.

Terry N. Brown Brown.TerryN@epa.gov Tue 08 Jun 2021 12:53:44 AM UTC
"""
from itertools import product
from pprint import pformat

import pymongo

# from genraweb.lib.db_connection import open_mongo_db
from genraweb.lib.viewChem_helpers import _viewChemNN
from genraweb.resources import DB

CIDS = [
    "DTXCID30182",  # BPA
    "DTXCID90150942",  # FOOF
    "DTXCID90112",  # Atrazine
]

FPS = ["chm_mrgn", "chm_httr", "chm_ct", "bio_txct", "tox_txrf"]

NN_K0 = 8  # number of neighbors to fetch
NN_S0 = 0.2  # minimum similarity to collect

COLLECTIONS = [
    "compounds",
    "physprop",
    "chemotypes_calc",
    "chms_fp",
    "toxcast_fp",
    "toxref_tr_fp",
]


def neighbors_for_cid(cid, fp):
    """Get list of NN_K0 nearest neighbor for cid"""

    s0 = NN_S0
    k0 = NN_K0
    W = 600
    H = 600
    rs = 1.0
    img_w = 60
    img_h = 60
    rdst = "equal"
    sel_by = "tox_txrf"

    NN, _ = _viewChemNN(cid, s0, k0, W, H, rs, img_w, img_h, rdst, fp, sel_by)

    return NN["dsstox_cid"] if "dsstox_cid" in NN else []


def shorten(obj):
    """Recurse through "JSON" object shortening long lists and dicts to 20 items"""
    if not isinstance(obj, (list, dict)):
        return
    for item in obj if isinstance(obj, list) else obj.values():
        if isinstance(item, list) and len(item) >= 20:
            item[:] = item[:: len(item) // 20]
        elif isinstance(item, dict) and len(item) >= 20:
            keep = list(item.keys())[::len(item)//20]
            for key in list(item.keys()):
                if key not in keep:
                    del item[key]
        shorten(item)


def proc(log):
    cids = set()
    for cid, fp in product(CIDS, FPS):
        old = len(cids)
        ans = neighbors_for_cid(cid, fp)
        cids.update(ans)
        log.write(f"{cid} {fp} {len(cids)-old}\n")

    print(cids)
    # small_db = open_mongo_db(which="SMALL")
    small_db = pymongo.MongoClient("genra_mongodb").genra

    # This is IMPORTANT - it could drop FP data from dev/stg DB otherwise
    assert DB.client.server_info() != small_db.client.server_info()

    # check DB connection is working
    small_db.non_such.drop()
    small_db.non_such.insert_many([{"a": 1}, {"a": 2}])
    assert small_db.non_such.count_documents({"a": 2}) == 1
    small_db.non_such.drop()

    for collection in COLLECTIONS:
        print(collection)
        print(
            DB[collection].count_documents({}), small_db[collection].count_documents({})
        )
        small_db[collection].drop()
        small_db[collection].insert_many(
            DB[collection].find({"dsstox_cid": {"$in": list(cids)}})
        )
        print(
            DB[collection].count_documents({}), small_db[collection].count_documents({})
        )

    for collection in COLLECTIONS:
        if collection.endswith("_fp"):
            # can't use shorten, it breaks bio FP report.
            # for doc in small_db[collection].find({}):
            #     shorten(doc)
            #     small_db[collection].find_one_and_replace({"_id": doc["_id"]}, doc)
            log.write(f"\n{collection}\n")
            # dump one record of collection for reference
            log.write(pformat(small_db[collection].find_one({}, {"_id": 0})))


def main():
    with open("small_db.log", "w") as log:
        proc(log)


if __name__ == "__main__":
    main()
