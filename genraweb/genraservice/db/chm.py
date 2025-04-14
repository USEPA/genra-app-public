import copy

import numpy as np
import pymongo
from rdkit import Chem
from rdkit.Chem import AllChem

bulk_op = []


def makeChmFPs(
    C,
    save=False,
    replace=True,
    i=None,
    col_comp=None,
    col_chm_fp=None,
    useBulk=True,
):
    # if not col_comp: return

    global bulk_op

    M = Chem.MolFromSmiles(str(C["smiles"]))
    if not M:
        return

    FPT = dict(
        httr=lambda i: AllChem.GetHashedTopologicalTorsionFingerprintAsBitVect(i),
        mrgn=lambda i: AllChem.GetMorganFingerprintAsBitVect(i, 3, 2048),
    )

    dtxsid = C["dsstox_sid"] if "dsstox_sid" in C else None
    dtxcid = C["dsstox_cid"] if "dsstox_cid" in C else None
    name = C["name"] if "name" in C else None
    casrn = C["casrn"] if "casrn" in C else None
    mol_weight = C["mol_weight"] if "mol_weight" in C else None

    # logger.info("makeChmFPs for " + str(dtxcid))

    if "dsstox_sid" in C:
        FP = col_chm_fp.find_one({"dsstox_sid": dtxsid})
        if FP and not replace:
            return
        if FP:
            if useBulk:
                bulk_op.append(pymongo.DeleteOne({"dsstox_sid": dtxsid}))
            else:
                col_chm_fp.delete_one({"dsstox_sid": dtxsid})
    else:
        FP = col_chm_fp.find_one({"dsstox_cid": dtxcid})
        if FP and not replace:
            return
        if FP:
            if useBulk:
                bulk_op.append(pymongo.DeleteOne({"dsstox_sid": dtxsid}))
            else:
                col_chm_fp.delete_one({"dsstox_cid": dtxcid})

    FP = {
        "dsstox_sid": dtxsid,
        "name": name,
        "dsstox_cid": dtxcid,
        "casrn": casrn,
        "mol_weight": mol_weight,
    }

    if i:
        FP["i"] = i

    for fpn, fp_func in FPT.items():
        Y = {}
        V = fp_func(M)
        if V:
            Y["ds"] = list(
                np.core.defchararray.add(fpn + "_", np.where(V)[0].astype(np.str_))
            )
            Y["n"] = len(Y["ds"])
            FP[fpn] = copy.copy(Y)

    if save:
        if useBulk:
            bulk_op.append(pymongo.InsertOne(FP))
        else:
            col_chm_fp.insert_one(FP)
    else:
        return FP


def getChemIDsIter(col_comp=None):
    i = 0

    for C in col_comp.find(
        {},
        dict(dsstox_sid=1, dsstox_cid=1, name=1, casrn=1, smiles=1, mol_weight=1),
    ):
        # if i == 10000: break
        if "smiles" in C and ("dsstox_sid" in C or "dsstox_cid" in C):
            i += 1

            yield i, C


"""
def getChemIDsIter(col_comp=None):
    i=0
    with open('debug_',"a") as d:
        d.write("getChemIDsIter---- ")
    for C in col_comp.find({},dict(dsstox_sid=1)):
        i+=1
        with open(os.path.join(os.path.dirname(__file__), 'debug_'),"a") as d:
            d.write("getChemIDsIter2 on %s" %C['dsstox_sid'])

        yield i,C['dsstox_sid']
"""


def storeFPsForChems(CID, remove=True, DB_col=None):
    FP = makeFPsForChems(CID)
    if remove:
        # DB.chem_fp.remove({'dsstox_cid':{'$in':CID}})
        DB_col.insert_many([i for i in FP if i])
    else:
        for fp in FP:
            DB_col.update({"dsstox_cid": fp["dsstox_cid"]}, fp, dict(upsert=1))


def skipNulls(X):
    return {k: v for k, v in X.items() if v and v == v}


"""
def makeChmFPs(dtxsid,save=False,replace=True,
               i=None,
               col_comp=None,col_chm_fp=None):
    if not col_comp: return

    with open(os.path.join(os.path.dirname(__file__), 'debug_'),"a") as d:
        d.write("makeChmFPs2 on %s" %dtxsid)


    C = col_comp.find_one(dict(dsstox_sid=dtxsid),dict(_id=0))

    with open(os.path.join(os.path.dirname(__file__), 'debug_'),"a") as d:
        d.write("makeChmFPs2 smile is %s" %C['smiles'])

    M = Chem.MolFromSmiles(str(C['smiles']))
    if not (dtxsid and M): return

    FPT = dict(httr=lambda i:
               AllChem.GetHashedTopologicalTorsionFingerprintAsBitVect(i),
               mrgn=lambda i: AllChem.GetMorganFingerprintAsBitVect(i,3,2048))


    FP = col_chm_fp.find_one({'dsstox_sid':dtxsid})
    if FP and not replace: return
    if FP: col_chm_fp.delete_one({'dsstox_sid':dtxsid})

    FP = {'dsstox_sid':dtxsid,
          'name':C['name'],
          'dsstox_cid':C['dsstox_cid'],
          'casrn':C['casrn']}
    if i: FP['i'] = i

    for fpn,fp_func in FPT.items():
        Y = {}
        V = fp_func(M)
        if V:
            Y['ds']= list(np.core.defchararray
                .add(fpn+'_',np.where(V)[0].astype(np.str_)))
            Y['n'] = len(Y['ds'])
            FP[fpn]=copy.copy(Y)

    if save:
        col_chm_fp.insert_one(FP)
    else:
        return FP
"""


def makeChmFPi(
    dtxsid, save=False, replace=True, i=None, col_comp=None, col_chm_fp=None
):
    if not col_comp:
        return
    C = col_comp.find_one(dict(dsstox_sid=dtxsid), dict(_id=0))
    M = Chem.MolFromSmiles(str(C["smiles"]))
    if not (dtxsid and M):
        return

    FPT = dict(
        httr=lambda i: AllChem.GetHashedTopologicalTorsionFingerprintAsBitVect(i),
        mrgn=lambda i: AllChem.GetMorganFingerprintAsBitVect(i, 3, 2048),
    )

    FP = col_chm_fp.find_one({"dsstox_sid": dtxsid})
    if FP and not replace:
        return
    if FP:
        col_chm_fp.delete_one({"dsstox_sid": dtxsid})

    FP = {
        "dsstox_sid": dtxsid,
        "name": C["name"],
        "dsstox_cid": C["dsstox_cid"],
        "casrn": C["casrn"],
    }

    if i:
        FP["i"] = i

    for fpn, fp_func in FPT.items():
        Y = {}
        V = fp_func(M)
        if V:
            Y["ds"] = list(np.where(V)[0])
            Y["n"] = len(Y["ds"])
            FP[fpn] = Y

    if save:
        col_chm_fp.insert_one(FP)
    else:
        return FP
