import copy
import sys

import numpy as np
import pandas as pd
import pymongo

databases_2021_q1 = {
    "dsstox": "ro_prod_dsstox",
    "invitrodb": "prod_internal_invitrodb_v3_3",
}


def sql_assay(dbs=databases_2021_q1):
    q = """
    SELECT 
        * mkToxEffects
    FROM
        {invitrodb}.assay_component 
        INNER JOIN {invitrodb}.assay_component_endpoint 
            ON assay_component.acid = assay_component_endpoint.acid
        INNER JOIN {invitrodb}.intended_target ON intended_target.aeid=assay_component_endpoint.aeid
        INNER JOIN {invitrodb}.gene ON intended_target.target_id=gene.gene_id
    UNION ALL
    SELECT 
        acid,aid,assay_component_name,assay_component_desc,assay_component_target_desc,parameter_readout_type,assay_design_type,assay_design_type_sub,biological_process_target,detection_technology_type,detection_technology_type_sub,detection_technology,signal_direction_type,key_assay_reagent_type,key_assay_reagent,technological_target_type,technological_target_type_sub,aeid,assay_component_endpoint_name,export_ready,internal_ready,assay_component_endpoint_desc,assay_function_type,normalized_data_type,analysis_direction,burst_assay,key_positive_control,signal_direction,intended_target_type,intended_target_type_sub,intended_target_family,intended_target_family_sub,fit_all,cell_viability_assay,data_usability '' as description,'' as entrez_gene_id,'' as gene_id,'' as gene_name,'' as gene_symbol,'' as official_full_name,'' as official_symbol,'' as organism_id,'' as source,'' as target_id,'' as track_status,'' as uniprot_accession_number
        
    FROM
        {invitrodb}.assay_component 
        INNER JOIN {invitrodb}.assay_component_endpoint 
            ON assay_component.acid = assay_component_endpoint.acid            
    """
    return q.format(**dbs)


def sql_assay1(dbs=databases_2021_q1):
    q = """
    SELECT * FROM
        {invitrodb}.assay 
        INNER JOIN {invitrodb}.assay_source 
            ON assay.asid = assay_source.asid        
        INNER JOIN {invitrodb}.assay_component 
            ON assay.aid = assay_component.aid
        INNER JOIN {invitrodb}.assay_component_endpoint 
            ON assay_component.acid = assay_component_endpoint.acid    
    """
    return q.format(**dbs)


def sql_assay2(dbs=databases_2021_q1):
    q = """
    SELECT * FROM
        {invitrodb}.assay 
        INNER JOIN {invitrodb}.assay_source 
            ON assay.asid = assay_source.asid                
        INNER JOIN {invitrodb}.assay_component 
            ON assay.aid = assay_component.aid
        INNER JOIN {invitrodb}.assay_component_endpoint 
            ON assay_component.acid = assay_component_endpoint.acid
        INNER JOIN {invitrodb}.intended_target ON intended_target.aeid=assay_component_endpoint.aeid
        INNER JOIN {invitrodb}.gene ON intended_target.target_id=gene.gene_id
    """
    return q.format(**dbs)


def sql_assay_result(dbs=databases_2021_q1, spid=None, hits=True, dtxsid=None):
    q = """SELECT 
        dsstox_substance_id AS dsstox_sid, 
        chnm AS name, 
        {invitrodb}.mc5.aeid,
        modl, hitc, fitc, coff, actp, 
        modl_er, modl_tp, modl_ga, modl_gw, modl_la, modl_lw, modl_prob, modl_rmse,
        modl_acc, modl_acb, modl_ac10, bmad, resp_max, resp_min, max_mean, max_mean_conc,
        max_med, max_med_conc, logc_max, logc_min,nconc, npts, nrep
    FROM {invitrodb}.mc5
         INNER JOIN {invitrodb}.mc4 ON mc4.m4id=mc5.m4id
         INNER JOIN {invitrodb}.sample ON mc4.spid=sample.spid
         INNER JOIN {invitrodb}.chemical ON chemical.chid=sample.chid"""

    q = q.format(**dbs)
    Q = []
    if spid:
        Q.append(" sample.spid='{}'".format(spid))

    if dtxsid:
        Q.append(" chemical.dsstox_substance_id='{}'".format(dtxsid))

    if hits:
        Q.append("  modl <> 'cnst' ")

    if len(Q) > 0:
        q += "\n WHERE " + " and ".join(Q)

    return q


def sql_assay_result_0(dbs=databases_2021_q1, spid=None, dtxsid=None):
    #     q = """SELECT
    #         dsstox_substance_id AS dsstox_sid,
    #         chnm AS name,
    #         {invitrodb}.mc5.aeid,
    #         modl, hitc, fitc, coff, actp,
    #         modl_er, modl_tp, modl_ga, modl_gw, modl_la, modl_lw, modl_prob, modl_rmse,
    #         modl_acc, modl_acb, modl_ac10, bmad, resp_max, resp_min, max_mean, max_mean_conc,
    #         max_med, max_med_conc, logc_max, logc_min,nconc, npts, nrep,
    #         cnst, hill, hcov, gnls, gcov, cnst_er,
    #         cnst_aic, cnst_rmse, cnst_prob, hill_tp, hill_tp_sd, hill_ga, hill_ga_sd, hill_gw,
    #         hill_gw_sd, hill_er, hill_er_sd, hill_aic, hill_rmse, hill_prob, gnls_tp,
    #         gnls_tp_sd, gnls_ga, gnls_ga_sd, gnls_gw, gnls_gw_sd, gnls_la, gnls_la_sd, gnls_lw,
    #         gnls_lw_sd, gnls_er,gnls_er_sd, gnls_aic, gnls_rmse, gnls_prob,
    #         nmed_gtbl, tmpi
    #     FROM {invitrodb}.mc5
    #          INNER JOIN {invitrodb}.mc4 ON mc4.m4id=mc5.m4id
    #          INNER JOIN {invitrodb}.sample ON mc4.spid=sample.spid
    #          INNER JOIN {invitrodb}.chemical ON chemical.chid=sample.chid"""
    q = """SELECT 
        dsstox_substance_id AS dsstox_sid, 
        chnm AS name, 
        {invitrodb}.mc5.aeid,
        modl, hitc, fitc, coff, actp, 
        modl_er, modl_tp, modl_ga, modl_gw, modl_la, modl_lw, modl_prob, modl_rmse,
        modl_acc, modl_acb, modl_ac10, bmad, resp_max, resp_min, max_mean, max_mean_conc,
        max_med, max_med_conc, logc_max, logc_min,nconc, npts, nrep
    FROM {invitrodb}.mc5
         INNER JOIN {invitrodb}.mc4 ON mc4.m4id=mc5.m4id
         INNER JOIN {invitrodb}.sample ON mc4.spid=sample.spid
         INNER JOIN {invitrodb}.chemical ON chemical.chid=sample.chid"""

    q = q.format(**dbs)

    if spid:
        q = q + " where sample.spid='{}'".format(spid)

    if dtxsid:
        q = q + " where chemical.dsstox_substance_id='{}'".format(dtxsid)

    return q
