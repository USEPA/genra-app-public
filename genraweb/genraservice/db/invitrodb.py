import os
import re
import sys

import matplotlib.text as text
import numpy as np
import pandas as pd
import pylab as pl
import rpy2
import rpy2.robjects.packages as rpackages
import scipy as sp
import seaborn as sns
import xlwt
from matplotlib import gridspec
# import MySQLdb
from rpy2.robjects import pandas2ri
from scipy import stats
from scipy.interpolate import splev, splrep
from statsmodels import robust

pandas2ri.activate()


def skipNAKV(X):
    return {k.lower(): v for k, v in X.items() if v == v and v != "NA"}


tcpl = rpackages.importr("tcpl")


def initTcpl(
    user,
    passwd,
    db="prod_internal_invitrodb_v3",
    host="ccte-mysql-res.epa.gov",
):
    r = tcpl.tcplConf("MySQL", user, passwd, host=host, db=db)


def getTcplChem(fld=None, val=None):
    kw = {}
    if fld:
        kw["field"] = fld
    if val:
        kw["value"] = val

    try:
        X = tcpl.tcplLoadChem(**kw)
    except:
        # Oops - failed
        pass
    else:
        return pandas2ri.ri2py_dataframe(X).drop_duplicates()


def getTcplData(fld=None, val=None, level=None):
    kw = {"type": "mc"}
    if fld:
        kw["fld"] = fld
    if val:
        kw["val"] = val
    if not level:
        return
    else:
        kw["lvl"] = level

    try:
        x = tcpl.tcplLoadData(**kw)
        y = tcpl.tcplPrepOtpt(x)
    except:
        pass
    else:
        z = pandas2ri.ri2py_dataframe(y)
        return fixDFInts(z)


def fixDFInts(X):
    C = X.columns[X.dtypes == np.int32]
    if len(C) == 0:
        return X
    for c in C:
        X[c] = X[c].astype(np.integer)
    return X


def storeSampleResults(spid, dbc_assay_results=None):
    # spid = sample id

    # QUAL L6 = level 6 Fit quality data
    # FITS L5 = level 5 Fit data
    # CNCR L3 = level 3 conc response data

    CNCR = getTcplData(fld="spid", val=spid, level=3)
    FITS = getTcplData(fld="spid", val=spid, level=5)
    QUAL = getTcplData(fld="spid", val=spid, level=6)

    RES = []
    for (spid, aeid), Fit in FITS.groupby(["spid", "aeid"]):
        CR = CNCR[(CNCR.spid == spid) & (CNCR.aeid == aeid)]
        QL = QUAL[(QUAL.spid == spid) & (QUAL.aeid == aeid)]

        RES.append(getSampleAssayResult(Fit.iloc[0].dropna(), CR, QL))

    if dbc_assay_results:
        dbc_assay_results.insert_many(RES)
    else:
        return RES


def getSampleAssayResult(Fit, CR, QL=None):
    # Fit = level 5 data (one assay/aeid and one sample/spid)
    # CR  = Conc Resp level 3 data
    # QL  = QuaLity of CR level 6 data

    spid = Fit.spid
    aeid = Fit.aeid

    C_ft1 = ["m4id", "m5id", "nmed_gtbl"]
    C_ft = [
        "resp_max",
        "resp_min",
        "bmad",
        "max_mean",
        "actp",
        "fitc",
        "gcov",
        "coff",
        "max_mean_conc",
        "hcov",
        "logc_min",
        "nrep",
        "max_med_conc",
        "nconc",
        "max_med",
        "hitc",
        "logc_max",
        "resp_unit",
        "npts",
    ]
    C_cr = [u"apid", u"cndx", u"coli", u"rowi", u"wllt", u"logc", u"repi", u"resp"]
    C_ql = [u"flag", u"fval", u"fval_unit"]

    C_ft = list(Fit.index.intersection(C_ft))

    F0 = []
    BF0 = None
    for m in ["cnst", "hill", "gnls", "modl"]:
        if not m in Fit.index:
            continue
        fit = Fit.pop(m)
        K = [i for i in Fit.index if i.startswith(m)]
        Y2 = Fit[K]
        Y2.index = [re.sub("%s_?" % m, "", i) for i in K]
        Y2["model"] = m
        if m == "modl":
            Y2["model"] = fit
            BF0 = Y2.to_dict()
        elif len(Y2) > 1:
            F0.append(Y2.to_dict())
        Fit = Fit.drop(K)

    AR = Fit.drop(C_ft + C_ft1).to_dict()
    AR["fits"] = F0
    AR["cr_info"] = Fit[C_ft].to_dict()
    AR["cr_info"]["resp_unit"] = CR.resp_unit.iloc[0]
    if BF0:
        AR["best_fit"] = BF0
    AR["cr_data"] = list(map(skipNAKV, CR[C_cr].drop_duplicates().to_dict("records")))
    if QL.shape[0] > 0:
        AR["cr_qual"] = list(
            map(skipNAKV, QL[C_ql].drop_duplicates().to_dict("records"))
        )

    return AR


def buildCRDict(Fit, CR=None):
    spid = Fit.get("spid")
    aeid = Fit.get("aeid")
    Fit = skipNAKV(Fit)
    C_ft = [
        "resp_max",
        "resp_min",
        "bmad",
        "max_mean",
        "actp",
        "fitc",
        "gcov",
        "coff",
        "max_mean_conc",
        "hcov",
        "logc_min",
        "nrep",
        "max_med_conc",
        "nconc",
        "max_med",
        "hitc",
        "logc_max",
        "resp_unit",
        "npts",
    ]
    C_cr = [u"apid", u"cndx", u"coli", u"rowi", u"wllt", u"logc", u"repi", u"resp"]
    C_ft = list(set(C_ft).intersection(Fit))

    if not CR:
        CR = getTcplData(["spid", "aeid"], [spid, aeid], level=3)
    Rec = {}

    Y1 = pd.Series(Fit)
    F0 = []
    BF0 = None
    for m in ["cnst", "hill", "gnls", "modl"]:
        if m not in Fit:
            continue
        fit = Y1.pop(m)
        K = [i for i in Y1.index if i.startswith(m)]
        Y2 = Y1[K]
        Y2.index = [re.sub("%s_?" % m, "", i) for i in K]
        Y2["model"] = m
        if fit == fit:
            if m == "modl":
                BF0 = Y2.to_dict()
            else:
                F0.append(Y2.to_dict())
        Y1 = Y1.drop(K)

    R0 = Y1.drop(C_ft).to_dict()
    R0["fits"] = F0
    R0["cr_info"] = Y1[C_ft].to_dict()
    R0["cr_info"]["resp_unit"] = CR.resp_unit.iloc[0]
    if BF0:
        R0["best_fit"] = BF0
    R0["cr_data"] = CR[C_cr].drop_duplicates().to_dict("records")

    # FIgure out best fit
    # R0['best_fit']=next([i for i in F0 if i['model']=='modl'])

    return R0


def storeCR(Fit, dbc=None):
    try:
        CR = buildCRDict(Fit)
    except:
        pass
    else:
        if CR:
            dbc.insert_one(CR)
