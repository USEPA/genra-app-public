from datetime import datetime
from itertools import groupby

import pandas as pd
import pymongo

from genraweb.deploy_types import DeployType
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger


class FPToxcast(FPGen):
    """class responsible for building the Toxcast (bio) fingerprint info for given
    chemicals overwrite both the get_next_chem and chem_gen so they can work with
    multiple documents and perform additional sorting implements its own chem_proc as
    required by the model

    We know on_the_fly is False, so don't bother with fp_coll_name is None test.
    """

    batch_size = 1000  # 8641 records final output
    description = (
        "ToxCast fingerprints are a non-directional fingerprint representation of "
        "assay hit calls represented by the assay component name of the associated "
        "platform.  Hit calls are taken from Level 5 of the associated invitrodb. This "
        "fingerprint collection comprises both ToxCast and Tox21 assay outcomes."
    )
    fp_fields = [
        FPGen.FP_fields("toxcast_fp", "fpnd.all"),
    ]
    pred_fields = [
        FPGen.FP_fields("toxcast_fp", "fpnd.biop_txct"),
        FPGen.FP_fields("toxcast_fp", "fpnd.bion_txct"),
    ]
    fp_id = "bio_txct"
    fp_output_basename = "toxcast_fp"
    input_collection_name = "invitrodb_assay_rslt"
    maxDepType = DeployType.PROD
    name = "Biology: ToxCast data"
    similarity_tag = "b"
    testForSmile = False
    on_the_fly = False
    vendor = None  # used for vendor specific sub-classes

    def __init__(self, DB, fp_coll_name):
        super().__init__(DB, fp_coll_name)
        self.dbc_assay = DB.toxcast_assays
        self.src = "invitrodb_v2"

    def _vendor_query(self):
        """Search for vendor <VEN>_ at start of assay_component_endpoint_name in
        toxcast_assays.
        """
        if self.vendor:
            return {"assay_component_endpoint_name": {"$regex": f"^{self.vendor}_.*"}}
        return {}

    def all_chem_ids(self):
        """Iterator of all chem. id candidates for this FP"""
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        if self.vendor:
            allowed_aeid = list(
                set(
                    i["aeid"]
                    for i in self.dbc_assay.find(
                        self._vendor_query(), {"_id": False, "aeid": True}
                    )
                )
            )
            return list(
                set(
                    i["dsstox_sid"]
                    for i in self.DB[self.input_collection_name].find(
                        {"aeid": {"$in": allowed_aeid}},
                        {"_id": False, "dsstox_sid": True},
                    )
                )
            )
        return self.DB[self.input_collection_name].distinct("dsstox_sid")

    def generate_fps(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.
        Assumes existing values already deleted from collection.
        """
        chem_in = self.fp_core_fields(chem_ids)
        chem_in = {i["dsstox_sid"]: i for i in chem_in}

        results = []  # for bulk mongo insert
        F = dict(
            _id=0,
            aeid=1,
            assay_source_name=1,
            assay_component_name=1,
            assay_component_desc=1,
            assay_component_endpoint_name=1,
        )
        AI = pd.DataFrame(self.dbc_assay.find(self._vendor_query(), F))
        # may require
        # db.invitrodb_assay_rslt.createIndex({dsstox_sid: 1})
        # to avoid memory error in sort()
        records_in = (
            self.DB[self.input_collection_name]
            .find({"dsstox_sid": {"$in": chem_ids}})
            .sort([("dsstox_sid", pymongo.ASCENDING)])
        )

        for dtxsid, chem_records in groupby(records_in, lambda x: x["dsstox_sid"]):
            chem_records = list(chem_records)
            chem_df = pd.DataFrame(chem_records)

            H = chem_df

            if "modl" not in H:
                logger.info("no modl data, dropping id: %s", dtxsid)
                continue

            H = H.dropna(subset=["modl"])
            H = H.merge(AI, on="aeid")

            # prediction data
            # Note since we encode at assay component level, a given component may
            # show up both in pos_components and neg_components it has an endpoint
            # with hitc==1 and another endpoint with hitc==0
            # prediction
            pos_components = list(H[H["hitc"] == 1].assay_component_name.unique())
            neg_components = list(H[H["hitc"] == 0].assay_component_name.unique())

            FPND = dict(
                all=dict(
                    ds=list(H.assay_component_name.unique()),
                    n=len(H.assay_component_name.unique()),
                ),
                biop_txct=dict(
                    ds=pos_components,
                    n=len(pos_components),
                ),
                bion_txct=dict(
                    ds=neg_components,
                    n=len(neg_components),
                ),
            )

            cols = [
                "assay_source_name",
                "assay_component_name",
                "assay_component_desc",
                "assay_component_endpoint_name",
                "hitc",
                "modl",
            ]
            cols += [i for i in ["modl_tp", "modl_ga", "modl_ac10"] if i in H.index]
            H1 = H[cols]

            if FPND["all"]["n"] == 0:
                continue

            for asy_src, H_i in H.groupby("assay_source_name"):
                h = list(H_i.assay_component_name.unique())
                FPND[asy_src] = dict(ds=h, n=len(h))

            results.append(
                dict(
                    **chem_in[dtxsid],
                    src=self.src,
                    updated=[datetime.utcnow().replace(microsecond=0)],
                    hits=H1.to_dict("records"),
                    bioq=self.skip_nulls(
                        dict(
                            zip(
                                H.assay_component_name.str.replace(
                                    r"[.\s]", "_", regex=True
                                ),
                                H.modl_ga if "modl_ga" in H.index else [None] * len(H),
                            )
                        )
                    ),
                    fpnd=FPND,
                )
            )

        if results:
            self.DB[self.fp_coll_name].insert_many(results)


class FPToxcastVendorATG(FPToxcast):
    fp_id = "bio_txct_ATG"
    fp_fields = [FPGen.FP_fields("toxcast_atg_fp", "fpnd.all")]
    fp_output_basename = "toxcast_atg_fp"
    maxDepType = DeployType.PROD
    name = "Biology: ToxCast data, ATG"
    vendor = "ATG"  # OT? ACEA?

    description = "This ToxCast ATG FP is a subset based on assays from the Attagene vendor."


class FPToxcastVendorBSK(FPToxcast):
    fp_id = "bio_txct_BSK"
    fp_fields = [FPGen.FP_fields("toxcast_bsk_fp", "fpnd.all")]
    fp_output_basename = "toxcast_bsk_fp"
    maxDepType = DeployType.PROD
    name = "Biology: ToxCast data, BSK"
    vendor = "BSK"

    description = "This ToxCast BSK FP is a subset based on assays from the BioSeek vendor."


class FPToxcastVendorNVS(FPToxcast):
    fp_id = "bio_txct_NVS"
    fp_fields = [FPGen.FP_fields("toxcast_nvs_fp", "fpnd.all")]
    fp_output_basename = "toxcast_nvs_fp"
    maxDepType = DeployType.PROD
    name = "Biology: ToxCast data, NVS"
    vendor = "NVS"

    description = "This ToxCast NVS FP is a subset based on assays from the NovaScreen vendor."
