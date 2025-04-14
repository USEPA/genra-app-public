from functools import cache
from itertools import groupby

import pymongo

from genraweb.deploy_types import DeployType
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger


class FPPesticide(FPGen):
    """Pesticide mode of action / classification FP"""

    batch_size = 1000
    description = (
        "MOA/classification information taken from Resistance Action "
        "Committees for fungicides, insecticides and herbicides"
    )
    fp_fields = [FPGen.FP_fields("pest_fp", "fp")]
    fp_id = "bio_pest"
    fp_output_basename = "pest_fp"
    input_collection_name = "pesticideRAC"
    maxDepType = DeployType.PROD
    name = "Biology: Pesticide RAC"
    similarity_tag = "b"
    testForSmile = False
    on_the_fly = False

    def __init__(self, DB, fp_coll_name):
        super().__init__(DB, fp_coll_name)
        self.dbc_assay = DB.toxcast_assays
        self.src = "invitrodb_v2"

    def all_chem_ids(self):
        """Iterator of all chem. id candidates for this FP"""
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        return self.DB[self.input_collection_name].distinct("dsstox_sid")

    @staticmethod
    def _is_unknown(attr: str) -> bool:
        """Filter 'unknown' and 'uncertain' out of bit names list."""
        return "unknown" in attr.lower() or "uncertain" in attr.lower()

    @classmethod
    @cache
    def bit_names(cls):
        """Names for the bits in the FP."""
        return [i for i in super().bit_names() if not cls._is_unknown(i)]

    def generate_fps(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.
        Assumes existing values already deleted from collection.
        """
        chem_in = self.fp_core_fields(chem_ids)
        chem_in = {i["dsstox_sid"]: i for i in chem_in}

        results = []  # for bulk mongo insert
        records_in = (
            self.DB[self.input_collection_name]
            .find({"dsstox_sid": {"$in": chem_ids}})
            .sort([("dsstox_sid", pymongo.ASCENDING)])
        )

        for dtxsid, chem_records in groupby(records_in, lambda x: x["dsstox_sid"]):
            chem_records = list(chem_records)
            bits = set()
            for attr in (
                ("mc", "moa_class"),
                ("sc", "structure_class"),
                ("pc", "pesticide_class"),
            ):
                bits |= {
                    attr[0]
                    + "_"
                    # 'Host Plant Defence Induction' -> 'Host_Plant_Defence_Induction'
                    + "_".join(i[attr[1]].split())
                    # Add SID to bitname if unknown so unknown for x doesn't match
                    # unknown for y making them appear too similar
                    + (f"_{i['dsstox_sid']}" if self._is_unknown(i[attr[1]]) else "")
                    for i in chem_records
                    if isinstance(i[attr[1]], str)
                }
            results.append(chem_in[dtxsid] | {"fp": {"ds": list(bits), "n": len(bits)}})

        if results:
            self.DB[self.fp_coll_name].insert_many(results)
