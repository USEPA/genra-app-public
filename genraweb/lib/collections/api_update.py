"""Use API calls to update MongoDB collections.

Currently a ~PoC used for the compounds collection 202405, will expand to other
collections in the future.

See __main__ at bottom for control of steps.
"""
import concurrent.futures
import os
import time
from itertools import batched
from pathlib import Path

import openpyxl
import psycopg2
import pymongo
import requests
from genraweb.resources import DB

API_BATCH_SIZE = 200


def id_list():
    """List of SIDs / CIDs (?) to request.

    id_list() currently pulls SIDS (only) from downloaded (from figshare) .xlsx
    files, should change to an API call in the future.
    """
    for path in Path("/home/tbrown02/DSSTox_Feb_2024/").glob("*.xlsx"):
        workbook = openpyxl.load_workbook(path, read_only=True)
        sheet = workbook.active
        sheet.reset_dimensions()
        rows = sheet.rows
        next(rows)
        for row in rows:
            yield row[0].value
            # if row[5].value == 'CCCCCCCCC=CCCCCCCCCCCCC(=O)OCCCCCCCCC=CCC(O)CCCCCC':
            # if row[5].value == 'C=CC=O':
            #     exit()
        workbook.close()


def do_load(source):
    """Load "chemical details" (SMILES, mass etc.) to temp. Mongo table by SID."""
    for batch_i, batch in enumerate(batched(source, API_BATCH_SIZE)):
        resp = requests.post(
            "https://api-ccte.epa.gov/chemical/detail/search/by-dtxsid/"
            "?projection=ccdchemicaldetails",
            headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
            json=batch,
        )
        DB.ccd_chem_details.insert_many(resp.json())
        print(API_BATCH_SIZE * batch_i)


def get_one(cid):
    resp = requests.get(
        f"https://api-ccte.epa.gov/chemical/detail/search/by-dtxcid/{cid}"
        "?projection=ccdchemicaldetails",
        headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
    )
    resp.raise_for_status()
    return resp.json()


def do_cid_load(source):
    """Load "chemical details" (SMILES, mass etc.) to temp. Mongo table by CID."""
    # for batch in batched(do_cid_load_int(source), API_BATCH_SIZE):
    #     DB.ccd_chem_details.insert_many(batch)
    for batch_i, batch in enumerate(batched(source, API_BATCH_SIZE)):
        resp = requests.post(
            "https://api-ccte-stg.epa.gov/chemical/detail/search/by-dtxcid/"
            "?projection=ccdchemicaldetails",
            headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
            json=batch,
        )
        DB.ccd_chem_details.insert_many(resp.json())
        print(API_BATCH_SIZE * batch_i)


def do_cid_load_threaded(source):
    # NOT USED
    for batch_i, batch in enumerate(batched(thread_pull(source), API_BATCH_SIZE)):
        print(API_BATCH_SIZE * batch_i)
        DB.ccd_chem_details.insert_many(batch)


def diff_old_new():
    """SMILES comparison, not part of import process."""
    all_smiles = set()
    for i, chem in enumerate(DB.compounds.find({}, {"_id": 0, "smiles": 1})):
        if "smiles" in chem:
            all_smiles.add(chem["smiles"])
        if not i % 10_000:
            print(i, len(all_smiles))
    print(i, len(all_smiles))

    new_smiles = set()
    for i, chem in enumerate(
        DB.ccd_chem_details.find(
            {}, {"_id": 0, "smiles": 1, "qsarReadSmiles": 1, "msReadySmiles": 1}
        )
    ):
        # API has three SMILES fields
        if "smiles" in chem:
            new_smiles.add(chem["smiles"])
        if "qsarReadSmiles" in chem:
            new_smiles.add(chem["qsarReadSmiles"])
        if "msReadySmiles" in chem:
            new_smiles.add(chem["msReadySmiles"])
        if not i % 10_000:
            print(i, len(new_smiles))
    print(i, len(new_smiles))
    Path("tmp.lst").write_text(str(all_smiles - new_smiles))


def find_missing():
    """id_list() currently pulls SIDS (only) from downloaded (from figshare) .xlsx
    files, should change in future.  This looks in the CCD Postgres DataMart which
    drives batchsearch for SIDs and CIDs not seen that way, to add to the chems.
    requested through the API.  Should be removed when id_list() is replaced with an
    API call.
    """
    conn = psycopg2.connect(
        host="ccte-pgsql-dev.epa.gov",
        database="dev_datahub",
        user="tbrown",
        password=os.environ["POSTGRES_PASSWORD"],
    )
    pg_cids = set()
    pg_sids = set()
    cur = conn.cursor()
    cur.execute("select dtxsid, dtxcid from ccd_app.chemical_details")
    for sid, cid in cur:
        pg_cids.add(cid)
        pg_sids.add(sid)

    cd_cids = set()
    cd_sids = set()
    for chem in DB.ccd_chem_details.find({}, {"_id": 0, "dtxcid": 1, "dtxsid": 1}):
        # Two fields to consider
        cd_cids.add(chem.get("dtxcid"))
        cd_sids.add(chem.get("dtxsid"))
    for set_ in pg_sids, pg_cids, cd_sids, cd_cids:
        set_.discard(None)
    Path("sids").write_text("\n".join(pg_sids - cd_sids))
    Path("cids").write_text("\n".join(pg_cids - cd_cids))


def thread_pull(source):
    """NOT USED - thread based code before API supported batches of CIDs."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_cid = {executor.submit(get_one, cid): cid for cid in source}
        for future in concurrent.futures.as_completed(future_to_cid):
            cid = future_to_cid[future]
            try:
                data = future.result()
            except Exception as exc:
                print("%r generated an exception: %s" % (cid, exc))
            else:
                yield data


def sids_no_synonyms_list():
    """List of SIDs missing synonyms.  I.e. from local collection.

    NOTE: currently using temporary ccd_chem_details collection, may use compounds in
    future.
    """
    # query = {"dtxsid": {"$ne": None}, "$or": [{"synonyms": None}, {"synonyms": []}]}
    query = {
        "dtxsid": {"$ne": None},
        "synonyms": None,
        # "casrn": {"$not": {"$regex": "^NOCAS_"}},
    }
    print(DB.ccd_chem_details.count_documents(query))
    for sid in DB.ccd_chem_details.find(query, {"_id": False, "dtxsid": True}):
        yield sid["dtxsid"]


def do_syn_by_sid():
    """Load synonyms by SID."""
    start = 0
    for batch_i, batch in enumerate(batched(sids_no_synonyms_list(), API_BATCH_SIZE)):
        print(API_BATCH_SIZE * batch_i)
        # For many iterations this time, the time in the loop apart from the API call,
        # is < 0.001 seconds.  Then it will become 20 plus seconds and stay that way,
        # exit when that happens so command line `until script; do echo RESTART; done`
        # can clear the condition.
        # Oddly specifically between 17200 and 17400 chem.
        print(time.time() - start)
        if start and time.time() - start > 60:
            exit(1)
        start = time.time()
        values = []
        resp = requests.post(
            "https://api-ccte-stg.epa.gov/chemical/synonym/search/by-dtxsid/",
            headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
            json=batch,
        )
        if resp.status_code < 400 and resp.json():
            values = resp.json()
        else:
            for chem_i, chem in enumerate(batch):  # Try one at a time
                resp = requests.get(
                    "https://api-ccte-stg.epa.gov/chemical/synonym/search/by-dtxsid/"
                    + chem,
                    headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
                )
                if resp.status_code < 400:
                    values.append(resp.json())
                else:
                    print(f"Skipped {chem_i} {chem}, {len(values)} ok")

        print("API call", time.time() - start)
        start = time.time()
        if not values:
            continue
        lists = {
            i["dtxsid"]: (i.get("valid") or [])
            + (i.get("good") or [])
            + (i.get("other") or [])
            for i in values
        }
        print("Max. synonyms", max(map(len, lists.values())))
        ops = [
            pymongo.UpdateOne(
                {"dtxsid": k},
                {"$set": {"synonyms": v}},
            )
            for k, v in lists.items()
        ]
        if ops:
            write_start = time.time()
            DB.ccd_chem_details.bulk_write(ops)
            print("Write time", time.time() - write_start)


def smiles_check():
    """API data has three SMILES per record, "smiles", "msReadySmiles", and
    "qsarReadySmiles".  This tests the set relationships between these three fields and
    GenRA's single smiles field.  Expectation is that CID only entries in GenRA's
    compounds collection include all the ms/qsar-ready forms.
    """
    api_smiles = set()
    api_qsar = set()
    api_ms = set()
    sid = 0
    cid = 0
    sidcid = 0
    for rec in DB.ccd_chem_details.find(
        {},
        {
            "_id": False,
            "smiles": True,
            "qsarReadySmiles": True,
            "msReadySmiles": True,
            "dtxsid": True,
            "dtxcid": True,
        },
    ):
        api_smiles.add(rec.get("smiles"))
        api_ms.add(rec.get("msReadySmiles"))
        api_qsar.add(rec.get("qsarReadySmiles"))
        r_sid = rec.get("dtxsid")
        r_cid = rec.get("dtxcid")
        if r_sid and r_cid:
            sidcid += 1
        elif r_sid:
            sid += 1
        elif r_cid:
            cid += 1
        else:
            raise Exception("No ID for record")

    api_smiles.discard(None)
    api_qsar.discard(None)
    api_ms.discard(None)
    exprs = [
        "api_smiles",
        "api_smiles | api_ms | api_qsar",
        "api_ms",
        "api_qsar",
        "api_ms | api_qsar",
        "(api_ms | api_qsar) - api_smiles",
    ]
    for expr in exprs:
        print(f"{len(eval(expr)):>15,} {expr}")
    print(f"{sidcid = }")
    print(f"{sid = }")
    print(f"{cid = }")
    lost = list((api_ms | api_qsar) - api_smiles)
    for smile in lost[::len(lost)//40]:
        print(smile)


if __name__ == "__main__":
    pass
    ## # 1. load all chem by SID from id_list()
    ## do_load(id_list())

    ## # 2. find things not included, see id_list() docs.
    ## print("Looking for missing...", end="")
    ## find_missing()
    ## print("done")

    ## # 3a. load missing chem. by SID
    ## do_load(Path("sids").read_text().split())
    ## # 3b. update missing CIDs list to account for CIDs referenced in 3a. load
    find_missing()
    ## # 3c. load missing chem. by SID
    ## do_cid_load(Path("cids").read_text().split())

    # 4. Load synonyms
    ## do_syn_by_sid()

    smiles_check()
