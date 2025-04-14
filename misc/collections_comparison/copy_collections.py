"""Copy collections between MongoDB servers.

A script used for various utility / comparision / verification purposed over time,
adding to repo. to capture cross DB (or server) collection copying function.

Usage so far involves editing this file for specific use cases.
"""
import time
from collections import defaultdict

import pymongo
from genraweb.lib.db_connection import open_mongo_db
from tests.lib.misc import deep_diff

# must be True for existing collections on destination to be "overwritten".  In fact
# they're renamed BKUP_<name>_<timestamp>, not really dropped.
drop = False
# when copying collections, add this prefix on the destination copy
# e.g prefix = "cutover20220830_"
prefix = "g2024_"

# list of collections to copy, with some example entries
todo = [
    # "compounds",
    # "physprop",
    # "toxcast_fp",
    # "toxcast_atg_fp",
    # "toxcast_bsk_fp",
    # "toxcast_nvs_fp",
    # "chms_fp",  # Morgan *and* Torsion
    # "aim_fp",
    # "pfas_fp",
    # "pest_fp",
    # "physchem_fp",
    # "chemotypes_fp",
    # "toxref_tr_fp",
    # "toxrefdb_v2",
    # "fp_info",
]

# Collections from "upstream" (DataHub -> DataMart ETL).
# FIXME: integrate with GEN-1272, dependency mapping, when available.
UPSTREAM = [
    "acutetox",
    "aop",
    "chemical_lists",
    "compounds",
    "epa_categories",
    "htpp_category",  # ETL probably needs revising, HT?? FP gen. uses res_ DB
    "htpp_chemical",
    "httk_chemical",
    "http_category",
    "http_chemical",
    "httr_signature",
    "invitrodb",
    "invitrodb_assay_rslt",
    "physprop",
    "toxcast_assays",
    "toxref_effects",
    "toxref_guideline",
    "toxrefdb2",
    "toxval",
    "tox_etaq",
]

# source and destination DBs
src_db = "DEV"
dst_db = "STG"
src = open_mongo_db(which=src_db)
dst = open_mongo_db(which=dst_db)

src_col = src.list_collection_names()
dst_col = dst.list_collection_names()
print("In source not dest.")
print([i for i in set(src_col) - set(dst_col) if "DELME" not in i])
print("In dest not source.")
print([i for i in set(dst_col) - set(src_col) if "DELME" not in i])


def hunt_field(db, collection_name, field_name):
    """Find one document with a non-null value for field_name."""
    query = {field_name: {"$ne": None}}
    return db[collection_name].find_one(query)


def compare_collections(collection):
    """Make deepdiff comparisons between collections.  SID centric."""
    sids = (
        src[collection]
        .find({"dsstox_sid": {"$ne": None}}, {"_id": 0, "dsstox_sid": 1})
        .limit(10_000)
    )
    sids = [i["dsstox_sid"] for i in list(sids)[::100]]
    src_recs = (
        src[collection]
        .find({"dsstox_sid": {"$in": sids}})
        .sort([("dsstox_sid", pymongo.ASCENDING)])
    )
    dst_recs = (
        dst[collection]
        .find({"dsstox_sid": {"$in": sids}})
        .sort([("dsstox_sid", pymongo.ASCENDING)])
    )
    for s, d in zip(src_recs, dst_recs):
        deep_diff(s, d, what=collection, ignore_nan_inequality=True)


# Informational reporting functions, mostly disabled
for collection in sorted(set(src_col) & set(dst_col) | set(UPSTREAM)):
    if False and not collection.startswith("toxref"):
        continue
    if "DELME" in collection:
        continue
    src_count = src[collection].estimated_document_count()
    dst_count = dst[collection].estimated_document_count()
    status = "=" if src_count == dst_count else "!"
    status += " U" if collection in UPSTREAM else "  "
    print(f"{status} {collection} {src_count} -> {dst_count}")

    if False and hunt_field(src, collection, "study_guideline_id"):
        # report collections containing a particular field
        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")

    if False and collection in UPSTREAM:
        # prints keys containing "id" in first record found
        print(
            collection,
            sorted(
                i
                for i in src[collection].find_one()
                if "id" in i.lower() and i != "_id"
            ),
        )

    if False and status == "= ":  # slow
        compare_collections(collection)

if False:
    # check for CID dupes in compounds (20220331 currently 1)
    count = defaultdict(lambda: 0)
    for chem in src.compounds.find(
        {"dsstox_cid": {"$exists": True}}, {"dsstox_cid": True}
    ):
        count[chem.get("dsstox_cid")] += 1
    print(f"CID dupes in {src_db}")
    for id_, n in count.items():
        if n != 1:
            print(id_, n)

# Copy collections between DBs
ts = time.strftime("%Y%m%d%H%M%S")
for coll in todo:
    src_name = coll
    dst_name = prefix + coll
    if dst_name in dst_col:
        if drop:
            print(f"Backing up {dst_name}.")
            dst[dst_name].rename(f"BKUP_{dst_name}_{ts}")
        else:
            print(f"Skipping {dst_name}, exists on destination.")
            continue
    print(f"{src_name} -> {dst_name}")
    block_size = 1000
    incoming = src[src_name].find()
    outgoing = []
    done = 0
    while True:
        for i in range(block_size):
            try:
                outgoing.append(next(incoming))
            except StopIteration:
                break
        done += len(outgoing)
        dst[dst_name].insert_many(outgoing)
        print(done, src_name)
        if len(outgoing) < block_size:
            break
        outgoing = []
