"""generate_fp_cmds.py - Print bash commands for generating FPs.

Just iterates class attributes to print bash commands you can copy/paste.

Terry N. Brown Brown.TerryN@epa.gov Mon 09 Aug 2021 02:00:50 PM UTC
"""
import os
from collections import namedtuple

from genraweb.defs import FILTER
from genraweb.lib.fp.fpclass import FPGen

PORT = os.environ.get("EXT_GENRA_API_PORT", "30001")  # 30001 for example if missing
BASE = f"http://127.0.0.1:{PORT}/genra-api/api/genra/v3/genFP/?chem_ids=ALL"

# translations for irregularities, thought there would be more
TRANS = {
    "chm_mrgn": "chm_mrgn/chm_httr",
    # "": "",
    # "": "",
    # "": "",
    # "": "",
}

FILTERS = [i for i in FILTER if not FILTER[i].get("skip")]


def header(text):
    print(f"\n## {text} " + "#" * (60 - len(text)) + "\n")


header("Generate new collections with fpgen_ prefix")
print(f"{BASE=}")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    fp_id = TRANS.get(fp_class.fp_id, fp_class.fp_id)
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f'curl "$BASE&fp={fp_id}&collection_name=fpgen_{coll_name}"')

header("Generate fp_info data, see also README.md for post-updates")
header("DANGER: modifies fp_info")
print(f"{BASE=}")
for fp_class in FPGen.FPClass.values():
    for sel_by in FILTERS:
        if fp_class.fp_id == "chm_httr":
            continue  # handled by chm_mrgn
        fp_id = TRANS.get(fp_class.fp_id, fp_class.fp_id)
        coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
        print(
            f'# curl "$BASE&fp_or_nn=nn&fp={fp_id}&'
            f'collection_name=fp_info&sel_by={sel_by}"'
        )

# account for ToxRef using two collections for FP
FakeFP = namedtuple("Fake", "fp_id fp_output_basename")
fake_fp = FakeFP("fp_fake", "toxref_tr_fp")
FPGen.FPClass["fp_fake"] = fake_fp

header("Compare counts, active->fpgen_")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f"db.{coll_name}.count()")
    print(f"db.fpgen_{coll_name}.count()")

header("Move active collections to prev_ prefix")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f"db.{coll_name}.renameCollection('prev_{coll_name}', dropTarget=true)")

header("Move fpgen_ collections to active (no prefix)")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f"db.fpgen_{coll_name}.renameCollection('{coll_name}')")

header("Move active collections to fpgen_ prefix")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f"db.{coll_name}.renameCollection('fpgen_{coll_name}', dropTarget=true)")

header("Move prev_ collections to active")
for fp_class in FPGen.FPClass.values():
    if fp_class.fp_id == "chm_httr":
        continue  # handled by chm_mrgn
    coll_name = TRANS.get(fp_class.fp_output_basename, fp_class.fp_output_basename)
    print(f"db.prev_{coll_name}.renameCollection('{coll_name}')")
