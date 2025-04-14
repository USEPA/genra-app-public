"""Rename pesticideRAC, copy no_filter to tox_txrf.

One off corrections already made, but structure is useful.
"""
import os
import sys

from genraweb.resources import DB

FP_INFO = os.environ.get("GENRA_FP_INFO_COLLECTION", "fp_info")

if len(sys.argv) > 1:
    fp_info_name = sys.argv[1]
else:
    fp_info_name = FP_INFO

print(f"\n\nUsing {fp_info_name} for fp_info collection")

keys = "chm_aim chm_ct chm_httr chm_mrgn chm_phch".split()
proj = {k: 1 for k in keys}
changed = 0
done = 0
query = {}
# query = {"tox_txrf": {"$ne": None}}
# proj = {"tox_txrf": 1}
for rec in DB[fp_info_name].find(query, proj):

    change = {}

    if 1:
        for key in keys:
            if key in rec:
                if "pesticideRAC" in rec[key]:
                    change[key] = rec[key]
                    change[key]["bio_pest"] = change[key].pop("pesticideRAC")
    elif 0:
        if "tox_txrf" not in rec["tox_txrf"] and "no_filter" in rec["tox_txrf"]:
            change["tox_txrf"] = rec["tox_txrf"]
            change["tox_txrf"]["tox_txrf"] = rec["tox_txrf"]["no_filter"]

    if change:
        changed += 1
        DB[fp_info_name].update_one({"_id": rec["_id"]}, {"$set": change}, upsert=False)

    done += 1
    if done % 100 == 0:
        print(done, changed)
