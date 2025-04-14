"""Mongo query for HTTP FP, from https://github.com/i-shah/genra-service/ fd3e9d0

Formatted with `black`, otherwise unchanged.  getChemHtppFp() is unused in genra-service
and by (CCTE) GenRA.
"""


def getChemHtppFp(Q=None, hitcall=0.5, col=None, limit=-1, Info={}):
    Ag = [
        {"$match": {"dtxsid": {"$exists": 1}}},
        {
            "$group": {
                "_id": {
                    "dtxsid": "$dtxsid",
                    "chem_name": "$chem_name",
                    "stype": "$stype",
                },
                "hits": {"$push": "$hits"},
            }
        },
        {
            "$addFields": {
                "ds_2": {
                    "$filter": {
                        "input": "$hits",
                        "as": "item",
                        "cond": {"$ne": ["$$item", "NA"]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "dtxsid": "$_id.dtxsid",
                "chem_name": "$_id.chem_name",
                "hitcall0": {"$literal": hitcall},
                "hits": 1,
                "fp": {
                    "fp_ft": {
                        "ds": "$ds_2",
                        "n": {"$size": {"$ifNull": ["$ds_2", []]}},
                    },
                },
            }
        },
        {
            "$project": {
                "chem_info": 0,
                "bottle_id": 0,
                "_id": 0,
                "aliquot_date": 0,
                "ds_all": 0,
                "ds_ft": 0,
                "ds_ct": 0,
            }
        },
    ]

    if limit > 0:
        Ag += [{"$limit": limit}]

    for x in col.aggregate(Ag, allowDiskUse=True):
        yield x


def getChemHtppHits(Q=None, hitcall=0.5, col=None, limit=-1, Info={}):
    Hit_Dict = {
        "pg_id": "$pg_id",
        "stype": "$stype",
        "chem_id": "$chem_id",
        "min_conc": "$min_conc",
        "max_conc": "$max_conc",
        "n_conc": "$n_conc",
        "ctr_median": "$ctr_median",
        "ctr_nmad": "$ctr_nmad",
        "approach": "$approach",
        "endpoint": "$endpoint",
        "n_gt_cutoff": "$n_gt_cutoff",
        "cutoff": "$cutoff",
        "fit_method": "$fit_method",
        "top_over_cutoff": "$top_over_cutoff",
        "rmse": "$rmse",
        "tp": "$tp",
        "ga": "$ga",
        "er": "$er",
        "bmr": "$bmr",
        "bmdu": "$bmdu",
        "hitcall": "$hitcall",
        "ac50": "$ac50",
        "top": "$top",
        "ac5": "$ac5",
        "ac10": "$ac10",
        "ac20": "$ac20",
        "acc": "$acc",
        "ac1sd": "$ac1sd",
        "bmd": "$bmd",
        "conc": "$conc",
        "resp": "$resp",
    }

    Match = dict(hitcall={"$gte": hitcall})
    if Q:
        Match.update(Q)

    Ag = [
        {"$match": Match},
        {
            "$group": {
                "_id": {"chem_id": "$chem_id", "stype": "$stype", "pg_id": "$pg_id"},
                "ds_ft": {
                    "$addToSet": {
                        "$cond": {
                            "if": {"$eq": ["$approach", "feature"]},
                            "then": "$endpoint",
                            "else": "NA",
                        }
                    }
                },
                "hits": {"$push": Hit_Dict},
            }
        },
        {
            "$addFields": {
                "ds_2": {
                    "$filter": {
                        "input": "$ds_ft",
                        "as": "item",
                        "cond": {"$ne": ["$$item", "NA"]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "chem_id": "$_id.chem_id",
                "pg_id": "$_id.pg_id",
                "stype": "$_id.stype",
                "hitcall0": {"$literal": hitcall},
                "hits": 1,
                "fp": {
                    "fp_ft": {
                        "ds": "$ds_2",
                        "n": {"$size": {"$ifNull": ["$ds_2", []]}},
                    },
                },
            }
        },
        {
            "$lookup": {
                "from": "htpp_chem",
                "localField": "chem_id",
                "foreignField": "chem_id",
                "as": "chem_info",
            }
        },
        {
            "$replaceRoot": {
                "newRoot": {
                    "$mergeObjects": [{"$arrayElemAt": ["$chem_info", 0]}, "$$ROOT"]
                }
            }
        },
        {
            "$project": {
                "chem_info": 0,
                "bottle_id": 0,
                "_id": 0,
                "aliquot_date": 0,
                "ds_all": 0,
                "ds_ft": 0,
                "ds_ct": 0,
            }
        },
    ]

    if limit > 0:
        Ag += [{"$limit": limit}]

    for x in col.aggregate(Ag, allowDiskUse=True):
        yield x
