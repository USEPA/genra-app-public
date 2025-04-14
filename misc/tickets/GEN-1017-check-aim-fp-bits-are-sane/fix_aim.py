"""One off code to check / fix aim_fp results.

Four "MODE"s:

(1) check the the ";" in bit labels that messed up the
aim_fp ds lists don't occur in the ToxPring Corina input - they don't.

(2) find a fix dupes in the aim_fp collection, not sure why there were dupes.

(3) re-calc "ds" lists from bitstring for aim_fp/

(4) re-calc "ds" lists from bitstring from PO's reference .tsv and create
collection for regular run_fp_generation_test() test.
"""
import csv
# import shelve
from collections import defaultdict
from itertools import compress
from pathlib import Path

from lxml import etree

import genraweb
from genraweb.lib.chem_id import ChemID
from genraweb.resources import DB

# MODE = "check toxprint"
# MODE = "find and fix dupes"
# MODE = "fix and check aim_fp"
MODE = "back-calc test data"

COL = DB.aim_fp

if MODE == "check toxprint":
    source = "toxprint_V2.0_r711.xml"
else:
    source = "AIM_V1.1_Sep_07_22.xml"  # needed for "back-calc test data" too

source = Path(genraweb.resources.__file__).parent / "lib" / "fp" / source
dom = etree.parse(open(source))
namespace = "http://www.molecular-networks.com/schema/csrml"

bits = dom.xpath("//ns:subgraph", namespaces={"ns": namespace})
names = []
for bit in bits:
    name = bit.xpath(".//ns:label/text()", namespaces={"ns": namespace})[0]
    name = (
        name.strip('"')
        .replace("\u2010", "-")
        .replace("\n", " ")
        .replace("  ", " ")
        .strip()
    )
    if True:  # prepend_subgraph_id:  # Labels are not unique
        name = bit.get("id") + ": " + name
    names.append(name)
bits = names

if MODE == "check toxprint":
    assert not any(";" in i for i in bits)
    exit()

if MODE == "find and fix dupes":
    # Tried collecting dupe IDs, then individually querying dupes to see if they're
    # identical, but far too slow so cache all data.
    count = defaultdict(list)
    read = 0
    seen = 0
    for fp_i, fp in enumerate(COL.find()):
        seen += 1
        if "chemotypes" not in fp:
            if "characteristics" not in fp:
                print(fp)
            continue
        count[(fp.get("dsstox_sid"), fp.get("dsstox_cid"))].append(fp)
        read += 1
    print(f"{seen=}")
    print(f"{read=}")
    counts = defaultdict(int)
    for x in count.values():
        counts[len(x)] += 1
    print(counts)
    culls = []
    for key, value in count.items():
        if len(value) < 2:
            continue
        comp = [dict(i) for i in value]
        # check all dupes are the same
        for i in comp:
            del i["_id"]
        assert all(i == comp[0] for i in comp[1:])
        culls += [i["_id"] for i in value[1:]]
        if len(culls) >= 1000:
            print(len(culls))
            COL.delete_many({"_id": {"$in": culls}})
            culls = []

    print(len(culls))
    COL.delete_many({"_id": {"$in": culls}})


if MODE == "fix and check aim_fp":
    for fp_i, fp in enumerate(COL.find()):
        if fp_i % 1000 == 0:
            print(fp_i)
        if "chemotypes" not in fp:
            # print("Skipping")
            continue
        assert "bitstring" in fp
        assert len(fp["bitstring"]) == len(bits)
        # if not any('"' in i for i in fp["chemotypes"]["ds"]):
        #     # print("OK")
        #     continue
        fp["chemotypes"]["ds"] = list(compress(bits, map(int, fp["bitstring"])))
        COL.update_one(
            {"_id": fp["_id"]},
            {"$set": {"chemotypes.ds": fp["chemotypes"]["ds"]}},
            upsert=False,
        )

if MODE == "back-calc test data":

    # Load the reference FP file from PO
    path = (
        Path(genraweb.resources.__file__).parent.parent
        / "tests"
        / "test_fp_generation"
        / "test_chemotypes"
        / "AIM_V1_vs_TB_tests.tsv"
    )
    reader = csv.reader(path.open(), delimiter="\t")
    fields = next(reader)
    rows = list(reader)
    # # IDs in this file are CASRNs without dashes
    # casrns = [i[0] for i in rows]
    # # Make CASRN to CID lookup
    # with shelve.open("spam") as db:
    #     if "all_cas" in db:
    #         all_cas = db["all_cas"]
    #     else:
    #         print("Making lookup table")
    #         all_cas = {
    #             x.get("casrn", "").replace("-", ""): x
    #             for x in DB.compounds.find(
    #                 {"casrn": {"$ne": None}, "dsstox_cid": {"$ne": None}},
    #                 {"casrn": 1, "dsstox_cid": 1, "_id": 0},
    #             )
    #         }
    #         db["all_cas"] = all_cas
    # print(len(all_cas))
    # print(list(all_cas.keys())[:10])
    # print(sum(1 for i in casrns if i in all_cas))
    # # Next is slow but confirms no ambiguity, same 4585 matches.
    # # print(sum(1 for i in all_cas if i in casrns))

    # Confirm order of bits same in XML (= chm_aim) and reference data
    del fields[0]  # First column is "M_CASRN"
    for tsv, xml in zip(fields, bits):
        xml = xml.replace("\u2010", "-")  # XML version has hyphens not dashes
        xml = xml.replace("\n", " ").replace("  ", " ")  # And some \n
        assert tsv.strip() == xml.split(": ", maxsplit=1)[-1], (
            tsv,
            xml,
        )  # i.e. without subgraph ID

    skipped = 0
    reference = []
    for row in rows:
        # if row[0] in all_cas:
        #     cid = all_cas[row[0]]
        # else:
        #     skipped += 1
        #     continue
        ref = {"dsstox_sid": row[0]}
        chem = ChemID.compounds_chem(row[0])
        ref["dsstox_cid"] = chem["dsstox_cid"]

        reference.append(ref)
        ref["chemotypes"] = {"ds": list(compress(bits, map(int, row[1:])))}
        ref["bitstring"] = "".join(row[1:])

    print(f"{skipped} not found")
    DB.aim_fp_reference.drop()
    DB.aim_fp_reference.insert_many(reference)
