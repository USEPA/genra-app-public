"""Fix older collections.

With new data in 2024 we have some compounds records (Mancozeb) which are now
SID+CID where they were previously two separate records SID+null and null+CID.
So toxcast_fp for example has only SID, which is now promoted to CID, so toxcast_fp
record is not found.

This code adds missing SIDs / CIDs to *_fp collection records.
"""
from genraweb.lib.fp.fpclass import FPGen
from genraweb.resources import DB

cid2sid = {}
sid2cid = {}
true_name = {}
sid_name = {}
cid_name = {}
for compound in DB.compounds.find(
    {}, {"_id": 0, "dsstox_sid": 1, "dsstox_cid": 1, "name": 1}
):
    cid2sid[compound["dsstox_cid"]] = compound["dsstox_sid"]
    sid2cid[compound["dsstox_sid"]] = compound["dsstox_cid"]
    true_name[(compound["dsstox_cid"], compound["dsstox_sid"])] = compound["name"]
    sid_name[compound["dsstox_sid"]] = compound["name"]
    cid_name[compound["dsstox_cid"]] = compound["name"]
cid2sid.pop(None)
sid2cid.pop(None)
sid_name.pop(None)
cid_name.pop(None)
if (None, None) in true_name:
    raise Exception("SID == CID == None in compounds?")
print(f"{len(cid2sid) = }")
print(f"{len(sid2cid) = }")

cols = ["fp_info"]
cols.extend(i.fp_output_basename for i in FPGen.FPClass.values())
for col in cols:
    cnt = 0
    for rec_i, rec in enumerate(
        DB[col].find(
            {}, {"dsstox_sid": 1, "dsstox_cid": 1, "dtxcid": 1, "dtxsid": 1, "name": 1}
        )
    ):
        if rec_i % 10_000 == 0:
            print(col, rec_i)
        if not rec.get("dsstox_sid") and cid2sid.get(rec.get("dsstox_cid")):
            cnt += 1
            print(cnt, col, rec, cid2sid.get(rec.get("dsstox_cid")))
            DB[col].update_one(
                {"_id": rec["_id"]},
                {"$set": {"dsstox_sid": cid2sid.get(rec.get("dsstox_cid"))}},
                upsert=False,
            )
        elif not rec.get("dsstox_cid") and sid2cid.get(rec.get("dsstox_sid")):
            cnt += 1
            print(cnt, col, rec, sid2cid.get(rec.get("dsstox_sid")))
            DB[col].update_one(
                {"_id": rec["_id"]},
                {"$set": {"dsstox_cid": sid2cid.get(rec.get("dsstox_sid"))}},
                upsert=False,
            )
        elif not rec.get("dtxsid") and cid2sid.get(rec.get("dtxcid")):
            cnt += 1
            print(cnt, col, rec, cid2sid.get(rec.get("dtxcid")))
            DB[col].update_one(
                {"_id": rec["_id"]},
                {"$set": {"dtxsid": cid2sid.get(rec.get("dtxcid"))}},
                upsert=False,
            )
        elif not rec.get("dtxcid") and sid2cid.get(rec.get("dtxsid")):
            cnt += 1
            print(cnt, col, rec, sid2cid.get(rec.get("dtxsid")))
            DB[col].update_one(
                {"_id": rec["_id"]},
                {"$set": {"dtxcid": sid2cid.get(rec.get("dtxsid"))}},
                upsert=False,
            )
        # this works when rec has a correct cid/sid pair, but changes names to None
        # when it doesn't
        name = true_name.get(
            (
                rec.get("dsstox_cid", rec.get("dtxcid")),
                rec.get("dsstox_sid", rec.get("dtxsid")),
            )
        )
        # so sid / cid only lookup as fall back
        if not name:
            name = sid_name.get(rec.get("dsstox_sid", rec.get("dtxsid")))
        if not name:
            name = cid_name.get(rec.get("dsstox_cid", rec.get("dtxcid")))
        if rec.get("name") != name:
            print(cnt, col, rec.get("name"), '->', name)
            DB[col].update_one(
                {"_id": rec["_id"]}, {"$set": {"name": name}}, upsert=False
            )
