from itertools import groupby

import numpy as np
import pandas as pd
import pymongo

from genraweb.deploy_types import DeployType
from genraweb.genraservice.db.tox import mkToxRefFp
from genraweb.genraservice.db.toxrefdb import skipNones
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger
from genraweb.lib.misc import normalize_dosage_unit


class FPToxref(FPGen):
    """ToxRef fingerprint

    We know on_the_fly is False, so don't bother with fp_coll_name is None test.
    """

    batch_size = 50  # 1000 records final output, but mkToxRefFp is slow, so 50 for now.
    description = (
        "ToxRef fingerprint. This is a fingerprint representation of treatment-related "
        "chemical effects derived from ToxRefDB v2. The fingerprint representation is "
        "defined by concatenating study type with effect target."
    )
    fp_fields = [
        # FPGen.FP_fields("toxref_tr_fp", "tox_fp1.fp_pos"),
        # FPGen.FP_fields("toxref_tr_fp", "tox_fp1.fp_neg"),
        FPGen.FP_fields("toxref_tr_fp", "tox_fp2.fp_pos"),
        FPGen.FP_fields(
            "toxref_tr_fp", "tox_fp2.fp_neg"
        ),  # needed here for 2nd panel count
    ]
    # In Toxref's case, fingerprint equivalent to positives in prediction data,
    # so we copy here. OTOH, in FPToxcast, fp_fields and pred_fields are different.
    pred_fields = fp_fields.copy()
    fp_id = "tox_txrf"
    fp_output_stage1 = "toxrefdb_v2"
    fp_output_basename = "toxref_tr_fp"
    input_collection_name = "toxref_effects"
    maxDepType = DeployType.PROD
    name = "Toxicity: ToxRef data"
    similarity_tag = "t"
    testForSmile = False
    on_the_fly = False

    def __init__(self, DB, fp_coll_name):
        super().__init__(DB, fp_coll_name)
        if fp_coll_name:  # if not, probably NN not FP calc.
            other = fp_coll_name.replace(
                FPToxref.fp_output_basename, FPToxref.fp_output_stage1
            )

            if other == fp_coll_name:
                # handling FPToxref's two output collections is ad hoc, only works if
                # fp_coll_name starts with fp_output_basename, so when it # doesn't:
                other += "_stg1"
            self.stage_1_name = other

    def all_chem_ids(self):
        """Iterator of all potential chem. ids for this FP"""
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        return self.DB[self.input_collection_name].distinct("dsstox_sid")

    def delete_fps(self, chem_ids):
        """This FP has two collections, so drop the other as well."""
        super().delete_fps(chem_ids)
        if chem_ids == "ALL":
            self.DB[self.stage_1_name].drop()
            logger.info("Dropping %s", self.stage_1_name)
        else:
            self.DB[self.stage_1_name].delete_many(ChemID.chem_id_search(chem_ids))

    def generate_fps(self, chem_ids):
        """Generate and store FPs."""
        from genraweb.resources import DB  # avoid import before worker forked

        chem_in = self.fp_core_fields(chem_ids)
        chem_in = {i["dsstox_sid"]: i for i in chem_in}

        stage_1 = []
        sids_with_effects = []

        # requires
        # db.toxref_effects.createIndex({dsstox_sid: 1})
        # to avoid memory error in sort()
        records_in = (
            self.DB[self.input_collection_name]
            .find({"dsstox_sid": {"$in": chem_ids}})
            .sort([("dsstox_sid", pymongo.ASCENDING)])
        )
        logger.info("ToxRef stage 1 for %s chem.", len(chem_ids))
        for sid, chem_records in groupby(records_in, lambda x: x["dsstox_sid"]):
            chem_records = list(chem_records)
            chem_df = pd.DataFrame(chem_records)
            try:
                EP = self.calc_study_pods(chem_df, dbg=False)
            except IndexError:
                logger.info("calc_study_pods() IndexError for %s", sid)
                continue
            if EP.shape[0] == 0:
                continue
            stage_1.extend(map(skipNones, EP.to_dict("records")))
            sids_with_effects.append(sid)

        if stage_1:
            self.DB[self.stage_1_name].insert_many(stage_1)

        stage_2 = []
        for sid in sids_with_effects:
            result = chem_in[sid]
            try:
                toxref_fp = mkToxRefFp(
                    sid,
                    result.get("dsstox_cid") or "N/A",
                    result["name"],
                    eff_trt_or_crit="trt_related",
                    dbc_trfp=None,  # force return of FP
                    dbc_tref=DB[self.stage_1_name],  # updated in stage_1
                    dbt_tr=DB.toxref_guideline,
                )
                assert result["dsstox_sid"] == toxref_fp["dsstox_sid"]
                if toxref_fp.get("dsstox_cid") == "N/A":
                    del toxref_fp["dsstox_cid"]
                result.update(toxref_fp)
                if "chemical_name" in result:  # chem_in has "name"
                    del result["chemical_name"]
                stage_2.append(result)
            except ValueError as value_error:
                logger.info("mkToxRefFp ValueError %s %s", sid, value_error)
            except KeyError as key_error:
                logger.info("mkToxRefFp KeyError %s %s", sid, key_error)

        if stage_2:

            # check for duplicates in this batch
            sids = [i["dsstox_sid"] for i in stage_2 if "dsstox_sid" in i]
            assert len(sids) == len(set(sids))
            cids = [i["dsstox_cid"] for i in stage_2 if "dsstox_cid" in i]
            assert len(cids) == len(set(cids))

            DB[self.fp_coll_name].insert_many(stage_2)

    def calc_study_pods(self, E, dbg=False):
        """
        FIXME: This is still buggy and needs work
        Use the effects from sql_study_level_effects and determine PODs using the
        following rules:

        - LEL Lowest effect level
            - if effect_trt_related exists
              then it is the minimum dose at which effect_trt_related==1
              corresponding dose level (dl_lel)
            - else LEL>max tested dose

        - NEL No-effect level
            - if dl_lel > 1
              then it is the dose corresponding to the dl_lel-1
            - else NEL < min tested dose

        - LOAEL Lowest-observed-adverse-effect level
            - if effect_critical exists
              then it is the minimum dose at which critical effect = 1
              corresponding dose level (dl_loael)
            - else LOAEL > max tested dose

        - NOAEL No-observed-adverse-effect-level (also NEL, NOEL)
          In a series of dose levels tested, it is the highest level at which no effect
          is observed
            - if LOAEL exists
                - if dl_loael>1
                  then it is the dose corresponding to the dl_loael-1
                - else NOAEL< min tested dose
            - else NOAEL = max tested dose (double check)
        """
        Res = []
        for (chem, study_id, study_type, species), Xi in E.groupby(
            ["chemical_name", "study_id", "study_type", "study_species"]
        ):
            if dbg:
                print("\n", chem, study_id, study_type, species, Xi.shape[0])

            Xi["trt_grp_dose_adjusted"] = Xi.apply(
                lambda row: normalize_dosage_unit(
                    row["trt_grp_dose_adjusted"], row["trt_grp_dose_adjusted_unit"]
                ),
                axis="columns",
            )
            # trt_grp_dose_adjusted is NaN if not convertable, so this "correct".
            Xi["trt_grp_dose_adjusted_unit"] = "mg/kg/day"

            DL = (
                Xi[["trt_grp_dose_level", "trt_grp_dose_adjusted"]]
                .drop_duplicates()
                .reset_index(drop=True)
            )
            dl_nel = dl_lel = dl_loael = dl_noael = None
            nel = lel = noael = loael = None

            # LEL & NEL
            X_trt = Xi[Xi["effect_trt_related"] == 1]
            if X_trt.shape[0] == 0:
                if dbg:
                    print("\t NO treatment related effects!")

            dl_lel = X_trt.trt_grp_dose_level.min()
            lel = X_trt.trt_grp_dose_adjusted.min()
            dl_nel = dl_lel - 1 if dl_lel > 1 else None

            if dl_nel:
                nel = DL[DL["trt_grp_dose_level"] == dl_nel].trt_grp_dose_adjusted.iloc[
                    0
                ]
            if dbg:
                print("\tLEL={} NEL={}".format(lel, nel))

            # LOAEL & NOAEL
            X_cef = Xi[Xi["effect_critical"] == 1]
            if X_cef.shape[0] == 0:
                if dbg:
                    print("\t NO critical effects!")

            dl_loael = X_cef.trt_grp_dose_level.min()
            loael = X_cef.trt_grp_dose_adjusted.min()
            dl_noael = dl_loael - 1 if dl_loael > 1 else None

            if dl_noael:
                noael = DL[
                    DL["trt_grp_dose_level"] == dl_noael
                ].trt_grp_dose_adjusted.iloc[0]
            if dbg:
                print("\tLOAEL={} NOAEL={}".format(loael, noael))
                print(
                    "\n\tCritical Effects:\n\t ",
                    "\n\t  ".join(
                        X_cef[["effect_target", "effect_desc"]]
                        .drop_duplicates()
                        .apply(lambda x: ":".join(x), axis=1)
                        .to_list()
                    ),
                )
                print(
                    "\n\tTreatment Effects:\n\t ",
                    "\n\t  ".join(
                        X_trt[["effect_target", "effect_desc"]]
                        .drop_duplicates()
                        .apply(lambda x: ":".join(x), axis=1)
                        .to_list()
                    ),
                )

            Xi["NEL"] = np.where(
                (Xi.trt_grp_dose_adjusted == nel)
                & (Xi.effect_trt_related == 0)
                & (Xi.trt_grp_dose_level > 0),
                True,
                False,
            )
            Xi["LEL"] = np.where(
                (Xi.trt_grp_dose_adjusted == lel)
                & (Xi.effect_trt_related == 0)
                & (Xi.trt_grp_dose_level > 0),
                True,
                False,
            )

            Xi["NOAEL"] = np.where(
                (Xi.trt_grp_dose_adjusted == noael)
                & (Xi.effect_critical == 0)
                & (Xi.trt_grp_dose_level > 0),
                True,
                False,
            )

            Xi["LOAEL"] = np.where(
                (Xi.trt_grp_dose_adjusted == loael)
                & (Xi.effect_critical == 1)
                & (Xi.trt_grp_dose_level > 0),
                True,
                False,
            )

            Res.append(Xi)
            # effects_lel = X_lel[X_lel['trt_grp_dose_adjusted']==lel]
        if len(Res) > 0:
            return pd.concat(Res)
        else:
            return pd.DataFrame()
