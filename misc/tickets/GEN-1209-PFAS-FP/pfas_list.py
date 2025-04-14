"""Build collections to support PFAS lists."""
import os

import openpyxl
import pymongo
import requests

from genraweb.lib.chem_id import ChemID
from genraweb.resources import DB

PFAS_LIST = "PFAS8a7v3"
PFAS_COLL = f"{PFAS_LIST}_list"
REF_XLSX = "/genra/SuppInfo_TablesS1-S5_23Jan2023.xlsx"


def read_ref_data():
    """Read reference FPs from supplementary data from a paper for different PFAS
    list."""
    # read_only is much faster for this data, skips other sheets
    wb = openpyxl.load_workbook(REF_XLSX, read_only=True)
    sheet = wb["S2.PFASSTRUCTV5-TxP_PFAS FP"]
    rows = sheet.rows  # iterator from sheet.rows property, not a sheet.rows alias
    field = {i.value: n for n, i in enumerate(next(rows))}
    data = {}
    attribs = list(field.items())
    del attribs[0]  # DTXSID
    for row in rows:
        data[row[field["DTXSID"]].value] = [
            value for value, column in attribs if row[column].value
        ]
    return data


def make_collection():
    """Basically a filtered version of "compounds" for this FP."""
    if PFAS_COLL in DB.list_collection_names():
        print(f"{PFAS_COLL} exists, skipping creation.")
    else:
        print(f"{PFAS_COLL} missing, creating.")
        resp = requests.get(
            f"https://api-ccte.epa.gov/chemical/list/search/by-name/{PFAS_LIST}"
            "?projection=chemicallistwithdtxsids",
            headers={"x-api-key": os.environ["CCTE_PUBLIC_API_KEY"]},
        )
        ref_data = read_ref_data()
        sids = resp.json()["dtxsids"].split(",")
        chems = [ChemID.promote_id(i)[1] for i in sids]
        inserts = [
            pymongo.InsertOne(
                {
                    "dsstox_cid": i["dsstox_cid"],
                    "dsstox_sid": i["dsstox_sid"],
                    "name": i["name"],
                    "smiles": i["smiles"],
                    "reference": ref_data.get(i["dsstox_sid"]),
                }
            )
            for i in chems
        ]
        DB[PFAS_COLL].bulk_write(inserts)


if __name__ == "__main__":
    make_collection()
