import pandas as pd

from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.chem_id import ChemID

COL = FPGen.fp_collection_names()
DS = FPGen.fp_collection_paths()


def getFP(CID, fp="chm_mrgn", FP=None, DB=None, fill=None):

    col = COL.get(fp)
    ds = DS.get(fp)
    if not (ds and col):
        return

    proj = ChemID.chem_id_proj()

    Agg = [
        # Match chemicals in cluster
        {"$match": ChemID.chem_id_search(CID, index=False)},  # False because could include custom SMILE
        # need to add the min of either pos or neg effect here
        # {"$match": {"dsstox_cid": {"$in": CID}, n : {"$gt": p_n_min}}},
        # Include these fields
        {
            "$project": {**proj, "name": 1, "_id": 0, "fp": "$%s.ds" % ds},
        },
        # Unwind the fp
        {"$unwind": "$fp"},
    ]
    if FP:
        Agg.append({"$match": {"fp": {"$in": FP}}})

    X = DB[col].aggregate(Agg, allowDiskUse=True)
    
    if not X:
        return
    
    R = pd.DataFrame(list(X))

    if R.shape[0] == 0 or R.shape[1] == 0:
        return pd.DataFrame()

    return pd.pivot_table(
        R,
        index=["chem_id"],
        columns="fp",
        values="name",
        aggfunc=len,
        fill_value=fill,
    )
