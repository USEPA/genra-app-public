import csv
# import time
# from collections import defaultdict

# import pymongo

from genraweb.lib.db_connection import open_mongo_db

# from tests.lib.misc import deep_diff

src_db = "DEV"
src_coll = "compounds"
dst_coll = "chemotypes_20220601"
src = open_mongo_db(which=src_db)

src_coll = src[src_coll]
dst_coll = src[dst_coll]

neq = "$ne"
exists = "$exists"

stats = {
    "Compounds total": {"coll": src_coll, "query": {}},
    "Compounds smiles": {"coll": src_coll, "query": {"smiles": {"$ne": None}}},
    "Compounds smile=FAIL": {"coll": src_coll, "query": {"smiles": "FAIL"}},
    "ToxPrint total": {"coll": dst_coll, "query": {}},
    "ToxPrint bitstring": {
        "coll": dst_coll,
        "query": {"bitstring": {neq: None}},
    },
    "ToxPrint bitstring fail": {
        "coll": dst_coll,
        "query": {"bitstring": {neq: None}, "fail": {neq: None}},
    },
    "ToxPrint characteristics": {
        "coll": dst_coll,
        "query": {"characteristics": {neq: None}},
    },
    "ToxPrint no_id/bad smile": {
        "coll": dst_coll,
        "query": {"no_id": {neq: None}, "dsstox_cid": {exists: False}},
    },
    "ToxPrint known no_id/bad smile": {
        "coll": dst_coll,
        "query": {"no_id": {neq: None}, "dsstox_cid": {neq: None}},
    },
    "ToxPrint timeout": {
        "coll": dst_coll,
        "query": {"fail": "CORINA timeout"},
    },
    "ToxPrint fail other": {
        "coll": dst_coll,
        "query": {
            "$and": [
                {"no_id": {exists: False}},
                {"fail": {neq: "CORINA timeout"}},
                {"fail": {neq: None}},
            ]
        },
    },
    "ToxPrint fail None": {
        "coll": dst_coll,
        "query": {
            "$and": [
                {"fail": {exists: True}},
                {"fail": None},
            ]
        },
    },
    "ToxPrint no fail no bitstring": {
        "coll": dst_coll,
        "query": {
            "$and": [
                {"bitstring": {exists: False}},
                {"fail": {exists: False}},
                {"dsstox_cid": {neq: None}},
            ]
        },
    },
    "Markush?": {
        "coll": src_coll,
        "query": {
            "smiles": {"$regex": "[|*]"},
        },
    },
}

# dst_coll.delete_many(stats["ToxPrint timeout"]["query"])
# dst_coll.delete_many(stats["ToxPrint no fail no bitstring"]["query"])

item = {}
for name, stat in stats.items():
    count = stat["coll"].count_documents(stat["query"])
    print(f"{name:>30} {count}")
    item[name] = count
unaccounted = [
    "ToxPrint bitstring",
    "ToxPrint bitstring fail",
    "ToxPrint characteristics",
    "ToxPrint no_id/bad smile",
    "ToxPrint known no_id/bad smile",
    "ToxPrint timeout",
    "ToxPrint fail other",
    "ToxPrint fail None",
]
count = item["ToxPrint total"] - sum(item[i] for i in unaccounted)

print(f"Unaccounted for {count}")

missing = [
    "Compounds smile=FAIL",
    "ToxPrint bitstring",
    "ToxPrint bitstring fail",
    "ToxPrint no_id/bad smile",
    "ToxPrint known no_id/bad smile",
    "ToxPrint timeout",
    "ToxPrint fail other",
    "ToxPrint fail None",
    "Markush?",
]
count = item["Compounds smiles"] - sum(item[i] for i in missing)
print(f"Missing {count}")

writer = csv.writer(open("fails.csv", "w"))
writer.writerow(["type", "dsstox_cid", "error"])
for kind in (
    "ToxPrint known no_id/bad smile",
    "ToxPrint timeout",
    "ToxPrint fail other",
    "Markush?",
):
    for res in stats[kind]["coll"].find(stats[kind]["query"]):
        if isinstance(res["fail"], list):
            fail = list(reversed(res["fail"]))
        else:
            fail = res["fail"]
        writer.writerow([kind, res.get("dsstox_cid", "NA"), str(fail)])


# unaccounted = [i for i in unaccounted if item[i]]
# for res in dst_coll.find({"$nor": [stats[i]["query"] for i in unaccounted]}):
#     print(res)
#     input()
#
# all_tp = set(
#     i["dsstox_cid"]
#     for i in dst_coll.find({"dsstox_cid": {neq: None}}, {"dsstox_cid": 1, "_id": 0})
# )
# for i in src_coll.find(
#     {"dsstox_cid": {neq: None}},
#     {"dsstox_cid": 1, "_id": 0},
# ):
#     if i["dsstox_cid"] not in all_tp:
#         print(i)
