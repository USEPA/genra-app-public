from datetime import datetime

import pandas as pd

from genraweb.lib.logging import logger

from .chm import skipNulls

"""
def mkBioFp(dtxsid,save=False,replace=True,
            i=None,
            src='invitrodb_vXX',
            dbt_ivt=None,
            dbc_assays=None,
            dbc_fp=None):

    F = dict(_id=0,aeid=1, assay_source_name=1, assay_component_name=1,
             assay_component_endpoint_name=1)
    AI = pd.DataFrame(dbc_assays.find({},F))
    q = sql_assay_result(dtxsid=dtxsid,hits=True)
    H = pd.read_sql(q,dbt_ivt).merge(AI,on='aeid')
    H1= H[['assay_source_name', 'assay_component_name',
           'assay_component_endpoint_name','hitc','modl','modl_tp','modl_ga',
           'modl_ac10']]
    FPND = dict(all=dict(ds=list(H.assay_component_name.unique()),
                        n =len(H.assay_component_name.unique())) )

"""


def mkBioFp(
    dtxsid,
    dtxcid,
    name,
    save=False,
    replace=True,
    i=None,
    src="invitrodb_vXX",
    H=None,
    dbc_assay=None,
    dbc_fp=None,
):

    F = dict(
        _id=0,
        aeid=1,
        assay_source_name=1,
        assay_component_name=1,
        assay_component_endpoint_name=1,
    )
    AI = pd.DataFrame(dbc_assay.find({}, F))
    # q = sql_assay_result(dtxsid=dtxsid,hits=True)#out
    # H = pd.read_sql(q,dbt_ivt).merge(AI,on='aeid')#out
    # hits = dbt_ivt.find({'dsstox_sid':dtxsid})#in
    # if hits is None: return#in

    pd.set_option("display.max_columns", 500)

    if "modl_tp" not in H:
        logger.info("no modl_tp data, dropping id: " + dtxsid)
        return

    H.dropna(subset=["modl_tp"], inplace=True)

    H = H.merge(AI, on="aeid")

    H1 = H[
        [
            "assay_source_name",
            "assay_component_name",
            "assay_component_endpoint_name",
            "hitc",
            "modl",
            "modl_tp",
            "modl_ga",
            "modl_ac10",
        ]
    ]
    FPND = dict(
        all=dict(
            ds=list(H.assay_component_name.unique()),
            n=len(H.assay_component_name.unique()),
        )
    )

    logger.info("processing " + dtxsid)

    if FPND["all"]["n"] == 0:
        return

    for asy_src, H_i in H.groupby("assay_source_name"):
        h = list(H_i.assay_component_name.unique())
        FPND[asy_src] = dict(ds=h, n=len(h))

    Res = dict(
        dsstox_sid=dtxsid,
        dsstox_cid=dtxcid,
        name=name,
        src=src,
        updated=[datetime.utcnow().replace(microsecond=0)],
        hits=H1.to_dict("records"),
        bioq=skipNulls(
            dict(
                zip(
                    H.assay_component_name.str.replace(r"[.\s]", "_"),  # noqa Pandas
                    H.modl_ga,
                )
            )
        ),
        fpnd=FPND,
    )

    if dbc_fp:
        if dbc_fp.find({"dsstox_sid": dtxsid}).count() != 0:
            logger.info(f"{dtxsid} already in {dbc_fp.name}: deleting.")
            dbc_fp.delete_many({"dsstox_sid": dtxsid})

        logger.info("inserting into toxcast_fp " + dtxsid)
        dbc_fp.insert_one(Res)
    else:
        return Res
