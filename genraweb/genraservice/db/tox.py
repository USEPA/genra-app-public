from datetime import datetime

import pandas as pd

from genraweb.lib.logging import logger

from .toxrefdb import (calc_study_pods, get_effects_pos_neg, get_rows, skipNones,
                       sql_study_level_effects)

# def mkToxRefEffects(dtxsid: str,
#                    dbt_tr: sqlalchemy.engine.base.Engine=None,
#                    dbc_tref: pymongo.collection.Collection=None,
#                    calc_pods: bool = False,
#                    dbg: bool = False):


def mkToxRefEffects(dtxsid, dbt_tr=None, dbc_tref=None, calc_pods=False, dbg=False):
    """
    Make the toxref related collections in the genra_dev database for one
    chemical

    Parameters
    ----------

    dtxsid: the dsstox substance id of the chemical
    dbt_tr: the MySQLdb connection (e.g. created by sqlalchemy.create_engine)
    dbc_tref: the MongoDB collection pointer for toxref_effects to which
              effects will be written
    calc_pods: should the pods be included?
    Returns
    -------

    If the MongoDB collections are not provided then a DataFrame containing
     - effects
    """

    # Load Toxrefdb data for chemical
    E = get_rows(sql_study_level_effects(dtxsid=dtxsid), dbt_tr)
    if calc_pods:
        E = calc_study_pods(E, dbg=dbg)

    if E.shape[0] == 0:
        raise (ValueError("No effects for {}".format(dtxsid)))

    # Effects
    if dbc_tref:
        dbc_tref.insert_many(map(skipNones, E.to_dict("records")))
    else:
        return E


# def getToxRefEffects(dtxsid: str,
#                     study_type: str = None,
#                     effect_target: str = None,
#                     effect_critical: int = None,
#                     effect_trt_related: int = None,
#                     study_species: str = None,
#                     pod: str = None,
#                     dbc_tref: pymongo.collection.Collection=None,
#                     dbg: bool = False) -> pd.DataFrame:


def getToxRefEffects(
    dtxsid,
    study_type=None,
    effect_target=None,
    effect_critical=None,
    effect_trt_related=None,
    study_species=None,
    pod=None,
    dbc_tref=None,
    dbg=False,
):
    """
    Get the effects for each chemical

    Parameters
    ----------
    dtxsid: the dsstox substance id of the chemical
    ...
    pods: None or one of LOAEL,NOAEL,LEL,NEL
    dbc_tref: the MongoDB collection pointer for toxref_effects to which
              effects will be written
    Returns
    -------

    A DataFrame containing effects
    """

    Q = dict(dsstox_sid=dtxsid, study_guideline_id={"$ne": None})
    if study_type:
        Q.update(dict(study_type=study_type))
    if effect_target:
        Q.update(dict(effect_target=effect_target))
    if effect_critical:
        Q.update(dict(effect_critical=effect_critical))
    if effect_trt_related:
        Q.update(dict(effect_trt_related=effect_trt_related))
    if study_species:
        Q.update(dict(study_species=study_species))
    if pod in ["LOAEL", "NOAEL", "LEL", "LOAEL"]:
        Q.update({pod: True})

    F = dict(_id=0)

    E = pd.DataFrame(dbc_tref.find(Q, F))

    return E


# def mkPosNegEffects(dtxsid: str,
#                    eff_trt_or_crit: str='trt_related',
#                    dbt_tr: sqlalchemy.engine.base.Engine=None,
#                    dbc_tref: pymongo.collection.Collection=None,
#                    req_guide: pd.DataFrame=pd.DataFrame(),
#                    dbg: bool = False)->pd.DataFrame:


def mkPosNegEffects(
    dtxsid,
    eff_trt_or_crit="trt_related",
    dbt_tr=None,
    dbc_tref=None,
    req_guide=pd.DataFrame(),
    dbg=False,
):
    """
    Generate the complete set of positive (recorded) and negative (unrecorded
    but inferred) effects for an input chemical

    Parameters
    ----------
    dtxsid: the dsstox substance id of the chemical
    dbt_tr: the MySQLdb connection (e.g. created by sqlalchemy.create_engine)
    dbc_tref: the MongoDB collection pointer for toxref_effects to which
              effects will be written
    req_guide: a dataframe describing the effects required for each study type

    Returns
    -------
    a DataFrame containing all effect where positive (1) and negative (0)
    effects are in column effect_class
    """
    E = getToxRefEffects(dtxsid, dbc_tref=dbc_tref)

    if E.shape[0] == 0:
        raise (ValueError("No effects for {}".format(dtxsid)))

    if eff_trt_or_crit == "critical":
        E_pos = E[E["effect_critical"] == 1]
        X1 = E[E["effect_critical"] == 0]
    elif eff_trt_or_crit == "trt_related":
        E_pos = E[E["effect_trt_related"] == 1]
        X1 = E[E["effect_trt_related"] == 0]

    # These are the positive effect and required negative effects
    Pos, Neg = get_effects_pos_neg(E, req_guide, db=dbt_tr)

    C1 = list(E.columns[E.columns.str.contains("^effect_")])
    C1 += ["effect_critical", "effect_trt_related"]

    X2 = (
        E_pos.drop(C1, axis=1)
        .drop_duplicates()
        .merge(
            Neg.join(
                pd.DataFrame(
                    dict(effect_critical=0, effect_trt_related=0), index=Neg.index
                )
            ),
            on="study_guideline_id",
            how="outer",
        )
    )
    E_neg = pd.concat((X1.drop(X1.columns.difference(X2.columns), axis=1), X2))

    E_pos.insert(E_pos.shape[1], "effect_class", 1)
    E_neg.insert(E_neg.shape[1], "effect_class", 0)

    I = E_pos.columns.intersection(E_neg.columns)

    E_pn = pd.concat((E_pos[I], E_neg[I]))

    return E_pn


# def mkToxRefFp(dtxsid: str,
#               dbc_trfp: pymongo.collection.Collection=None,
#               src: str = 'toxrefdb_vXX',
#               **kwargs)->dict:


def mkToxRefFp(dtxsid, dtxcid, name, dbc_trfp=None, src="toxrefdb_vXX", **kwargs):
    """
    Make the toxref fingerprint the genra_dev database for one
    chemical

    Parameters
    ----------
    dtxsid: the dsstox substance id of the chemical
    eff_trt_or_crit: None, critical or trt_related
    dbt_tr: the MySQLdb connection (e.g. created by sqlalchemy.create_engine)
    dbc_tref: the MongoDB collection pointer for toxref_effects to which
              effects will be written
    dbc_trfp: the MongoDB collection pointer for toxref_fp to which the
              fingerprints will be written
    req_guide: a dataframe describing the effects required for each study type

    Returns
    -------
    If the MongoDB collections are not provided then a dictionary containing
     - fingerprints

    """
    # These are the chemical effects
    C_fp1 = ["study_type", "effect_target", "effect_desc"]
    C_fp2 = ["study_type", "effect_target"]
    C0 = [
        "chemical_name",
        "dsstox_sid",
        "study_type",
        "study_species",
        "study_admin_method",
        "trt_grp_sex",
        "trt_grp_generation",
        "effect_category",
        "effect_type",
        "effect_target",
        "trt_grp_dose_adjusted",
        "trt_grp_dose_adjusted_unit",
        "trt_grp_dur",
        "trt_grp_dur_unit",
        "fp1",
        "fp2",
    ]

    C2N = dict(
        trt_grp_sex="sex",
        trt_grp_generation="generation",
        trt_grp_dose_adjusted="dose",
        trt_grp_dose_adjusted_unit="dose_unit",
        trt_grp_dur="dur",
        trt_grp_dur_unit="dur_unit",
    )

    eff_trt_or_crit = kwargs.get("eff_trt_or_crit")
    # dbt_tr = kwargs.get("dbt_tr")

    logger.info("mkToxRefFp: %s %s %s", dtxsid, dtxcid, name)
    E = mkPosNegEffects(dtxsid, **kwargs)

    E.insert(E.shape[1], "fp1", E[C_fp1].apply(lambda x: ":".join(map(str, x)), axis=1))
    E.insert(E.shape[1], "fp2", E[C_fp2].apply(lambda x: ":".join(map(str, x)), axis=1))

    if eff_trt_or_crit == "critical":
        E_pos = E[(E["effect_critical"] == 1) & (E["effect_class"] == 1)][C0]
    elif eff_trt_or_crit == "trt_related":
        E_pos = E[(E["effect_trt_related"] == 1) & (E["effect_class"] == 1)][C0]

    # Effects to store
    E_pos = E_pos.drop_duplicates().reset_index(drop=True).rename(columns=C2N)

    # FP1
    FP = dict(
        dsstox_sid=dtxsid,
        dsstox_cid=dtxcid,
        name=name,
        chemical_name=E_pos.chemical_name[0],
        src=src,  # dbt_tr.url.database if dbt_tr else src,
        updated=[datetime.utcnow().replace(microsecond=0)],
        tox_q=list(map(skipNones, E_pos.to_dict("records"))),
    )

    for fp in ["fp1", "fp2"]:
        DS_pos = list(E[(E["effect_class"] == 1)][fp].unique())
        DS_neg = list(E[(E["effect_class"] == 0)][fp].unique())
        DS_neg = list(set(DS_neg).difference(DS_pos))
        FP["tox_" + fp] = dict(
            fp_pos=dict(ds=DS_pos, n=len(DS_pos)),
            fp_neg=dict(ds=DS_neg, n=len(DS_neg)),
        )

    if dbc_trfp:
        if dbc_trfp.find({"dsstox_sid": dtxsid}).count() != 0:
            logger.info(f"{dtxsid} already in {dbc_trfp.name}: deleting.")
            dbc_trfp.delete_many({"dsstox_sid": dtxsid})

        dbc_trfp.insert_one(FP)
    else:
        return FP
