import numpy as np
import pandas as pd

from genraweb.lib.logging import logger

databases_2021_q1 = {
    "dsstox": "ro_prod_dsstox",
    "invitrodb": "prod_internal_invitrodb_v3_3",
    "toxrefdb": "dev_toxrefdb_2_1",
}


# def get_effects_pos_neg(Effects: pd.DataFrame,ReqEffects: pd.DataFrame=pd.DataFrame(), db: sqlalchemy.engine.base.Engine=None):
def get_effects_pos_neg(Effects, ReqEffects=pd.DataFrame(), db=None):
    """
    Figure out the positive and negative effects for a chemical based on what
    each guideline testing study requires

    Parameters
    ----------
    Effects: A dataframe containing *ALL* rows from sql_study_level_effects. Do not filter these result else the negatives will be inferred incorrectly.

    ReqEffects: A dataframe containing rows from get_required_by_guideline
    db: MySQLdb connection

    Returns
    -------
    Positive and Negative effects as pd.DataFrames
    """
    if ReqEffects.shape[0] == 0:
        ReqEffects = get_required_by_guideline(db)

    try:
        X1 = Effects[ReqEffects.columns].drop_duplicates().reset_index(drop=True)
    except:
        return pd.DataFrame(), pd.DataFrame()

    E1 = Effects.set_index(list(ReqEffects.columns))
    #     X2 = Effects[['study_type','study_guideline_id', 'effect_category',
    #                   'effect_type','effect_target']]\
    #             .drop_duplicates().reset_index(drop=True)

    # What effects are required for these studies?
    R1 = ReqEffects[ReqEffects.study_guideline_id.isin(X1.study_guideline_id)]

    # What effects are required but not reported? These are the negatives (Neg)
    Neg = (
        X1.merge(R1, how="outer", indicator="required")
        .loc[lambda x: x["required"] == "right_only"]
        .drop("required", axis=1)
    )
    Pos = (
        X1.merge(R1, how="outer", indicator="required")
        .loc[lambda x: x["required"] != "right_only"]
        .drop("required", axis=1)
    )

    return Pos, Neg


def get_rows(q, eng):
    return pd.read_sql(q, eng)


def skipNones(X):
    return {k: v for k, v in X.items() if v == v and not v in ["None", None, "NULL"]}


def get_required_by_guideline(db):  # engine):
    C0 = [
        "study_guideline_id",
        "effect_category",
        "effect_type",
        "effect_target",
        "effect_desc",
        "effect_ep_id",
    ]
    # Guideline = get_rows(sql_guideline_whats_tested(effect=True),engine)
    Guideline = pd.DataFrame(db.find())
    ReqEffects = Guideline[Guideline.obs_status == "required"][C0].drop_duplicates()

    return ReqEffects


def sql_guideline_whats_tested(dbs=databases_2021_q1, effect=False):
    """
    Figure out what is tested in guideline study types
    """

    q = """SELECT
        guideline.guideline_id as study_guideline_id,
        guideline.guideline_number as study_guideline_number,
        guideline.name as study_guideline_name,
        guideline.profile_name as study_guideline_profile_name,
        guideline.description as study_guideline_description,
        guideline_profile.guideline_profile_id,
        guideline_profile.obs_status,
        guideline_profile.description,
        endpoint.endpoint_id,
        endpoint.endpoint_category as effect_category,
        endpoint.endpoint_type as effect_type,
        endpoint.endpoint_target as effect_target"""

    if effect:
        q += """, effect.effect_desc as effect_desc,
            effect.endpoint_id as effect_ep_id
    """
    q += """ FROM
        guideline
          INNER JOIN guideline_profile
            ON guideline.guideline_id=guideline_profile.guideline_id
          INNER JOIN endpoint
            ON endpoint.endpoint_id=guideline_profile.endpoint_id
        """
    if effect:
        q += """ INNER JOIN effect
            ON endpoint.endpoint_id=effect.endpoint_id"""
    return q


def sql_study_level_effects(dtxsid=None, dbs=databases_2021_q1):
    """
    Get all treatment group level effects for a study
    Adapted from KPF 2021/01/27
    """
    q = """SELECT distinct
                chemical.dsstox_substance_id as dsstox_sid,
                chemical.casrn as chemical_casrn,
                chemical.chemical_id,
                preferred_name as chemical_name,

                study.study_id,
                study.processed as study_processed,
                study.study_type,
                study.study_year,
                study.study_source,
                study.study_citation,
                study.species as study_species,
                study.strain_group as study_strain_group,
                study.admin_route as study_admin_group,
                study.admin_method as study_admin_method,
                study.substance_purity as study_substance_purity,
                study.dose_start as study_chem_dose_start,
                study.dose_start_unit as study_chem_dose_start_unit,
                study.dose_end as study_chem_dose_end,
                study.dose_end_unit as study_chem_dose_end_unit,
                study.guideline_id as study_guideline_id,

                tg_effect.life_stage as effect_life_stage,
                tg_effect.tg_effect_id as effect_tg_id,
                effect.effect_id,
                effect.effect_desc,
                effect.cancer_related as effect_cancer_related,
                tg.sex as trt_grp_sex,
                tg.generation as trt_grp_generation,
                dose.dose_level as trt_grp_dose_level,
                dtg.dose_adjusted as trt_grp_dose_adjusted,
                dtg.dose_adjusted_unit as trt_grp_dose_adjusted_unit,
                dtg_effect.time as trt_grp_dur,
                dtg_effect.time_unit as trt_grp_dur_unit,

                endpoint.endpoint_category as effect_category,
                endpoint.endpoint_type as effect_type,
                endpoint.endpoint_target as effect_target,
                endpoint.endpoint_id as effect_ep_id,
                tg_effect.target_site as effect_target_loc,
                tg_effect.direction as effect_dir,
                dtg_effect.dtg_effect_id,
                dtg_effect.treatment_related as effect_trt_related,
                dtg_effect.critical_effect as effect_critical,
                dtg_effect.sample_size as effect_sample_size,
                dtg_effect.effect_val,
                dtg_effect.effect_val_unit,
                dtg_effect.effect_var,
                dtg_effect.effect_var_type,
                dtg_effect.dtg_effect_comment as effect_comment,
                tg_effect.direction as effect_dir
           FROM
           ((((((((({toxrefdb}.chemical INNER JOIN {toxrefdb}.study ON chemical.chemical_id=study.chemical_id)
           INNER JOIN {toxrefdb}.dose ON dose.study_id=study.study_id)
           INNER JOIN {toxrefdb}.tg ON tg.study_id=study.study_id)
           INNER JOIN {toxrefdb}.dtg ON tg.tg_id=dtg.tg_id AND dose.dose_id=dtg.dose_id)
           INNER JOIN {toxrefdb}.tg_effect ON tg.tg_id=tg_effect.tg_id)
           INNER JOIN {toxrefdb}.dtg_effect ON tg_effect.tg_effect_id=dtg_effect.tg_effect_id AND dtg.dtg_id=dtg_effect.dtg_id)
           INNER JOIN {toxrefdb}.effect ON effect.effect_id=tg_effect.effect_id)
           INNER JOIN {toxrefdb}.endpoint ON endpoint.endpoint_id=effect.endpoint_id)
           INNER JOIN {toxrefdb}.obs ON obs.study_id=study.study_id AND obs.endpoint_id=endpoint.endpoint_id) """.format(
        **dbs
    )
    if dtxsid:
        q += " where dsstox_substance_id='{}'".format(dtxsid)
    return q


def calc_study_pods(E, dbg=False):
    """
    This is still buggy and needs work
    Use the effects from sql_study_level_effects and determine PODs using the following rules:
    - LEL
        - if effect_trt_related exists
          then it is the minimum dose at which effect_trt_related==1
          corresponding dose level (dl_lel)
        - else LEL>max tested dose
    - NEL
        - if dl_lel > 1
          then it is the dose corresponding to the dl_lel-1
        - else NEL < min tested dose

     - LOAEL
         - if effect_critical exists
             then it is the minimum dose at which critical effect = 1
             corresponding dose level (dl_loael)
         - else LOAEL > max tested dose

     - NOAEL
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
            logger.info(("\n", chem, study_id, study_type, species, Xi.shape[0]))

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
                logger.info("\t NO treatment related effects!")

        dl_lel = X_trt.trt_grp_dose_level.min()
        lel = X_trt.trt_grp_dose_adjusted.min()
        dl_nel = dl_lel - 1 if dl_lel > 1 else None

        if dl_nel:
            nel = DL[DL["trt_grp_dose_level"] == dl_nel].trt_grp_dose_adjusted.iloc[0]
        if dbg:
            logger.info("\tLEL={} NEL={}".format(lel, nel))

        # LOAEL & NOAEL
        X_cef = Xi[Xi["effect_critical"] == 1]
        if X_cef.shape[0] == 0:
            if dbg:
                logger.info("\t NO critical effects!")

        dl_loael = X_cef.trt_grp_dose_level.min()
        loael = X_cef.trt_grp_dose_adjusted.min()
        dl_noael = dl_loael - 1 if dl_loael > 1 else None

        if dl_noael:
            noael = DL[DL["trt_grp_dose_level"] == dl_noael].trt_grp_dose_adjusted.iloc[
                0
            ]
        if dbg:
            logger.info("\tLOAEL={} NOAEL={}".format(loael, noael))
            logger.info(
                "\n\tCritical Effects:\n\t "
                + "\n\t  ".join(
                    X_cef[["effect_target", "effect_desc"]]
                    .drop_duplicates()
                    .apply(lambda x: ":".join(x), axis=1)
                    .to_list()
                )
            )
            logger.info(
                "\n\tTreatment Effects:\n\t "
                + "\n\t  ".join(
                    X_trt[["effect_target", "effect_desc"]]
                    .drop_duplicates()
                    .apply(lambda x: ":".join(x), axis=1)
                    .to_list()
                )
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
