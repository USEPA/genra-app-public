"""
Reporting physical properties of chem.

NOTE: won't work if properties from different collections have the same in-collection
path.  Can be run as separate queries if that situation arises.
"""
from collections import defaultdict, namedtuple
from itertools import groupby

from rdkit import Chem
from rdkit.Chem import Descriptors

from genraweb.lib.chem_id import ChemID
from genraweb.resources import DB

PhysProp = namedtuple(
    "PhysProp", "id name description collection path units places in_plot"
)
PHYSPROP = [
    PhysProp(
        "mass",
        "Mass",
        "Average Mass",
        "compounds",
        "mol_weight",
        "g/mol",
        2,
        True,
    ),
    PhysProp(
        "MP",
        "Melting",
        "Melting point",
        "physprop",
        "predicted_props.OPERA_MP",
        "°C",
        1,
        True,
    ),
    PhysProp(
        "BP",
        "Boiling",
        "Boiling point",
        "physprop",
        "predicted_props.OPERA_BP",
        "°C",
        1,
        True,
    ),
    # https://comptox.epa.gov/dashboard/calculation-details?model_id=22&search=20182
    # implies OPERA_LogP is log Kow
    PhysProp(
        "logKow",
        "log Kow",
        "Octanol-water partition coefficient",
        "physprop",
        "predicted_props.OPERA_LogP",
        "",
        3,
        True,
    ),
    PhysProp(
        "vapPres",
        "Vap. press.",
        "Vapor pressure",
        "physprop",
        "predicted_props.OPERA_VP",
        "mmHg",
        3,
        True,
    ),
    PhysProp(
        "wtrSol",
        "Water sol.",
        "Water solubility",
        "physprop",
        "predicted_props.OPERA_WS",
        "mol/L",
        3,
        True,
    ),
    PhysProp(
        "HLC",
        "Henry's Law",
        "Henry's Law Constant",
        "physprop",
        "predicted_props.OPERA_HL",
        "atm-m3/mole",
        3,
        True,
    ),
    PhysProp(
        "HBD",
        "Hydrogen Bond Donors",
        "Number of hydrogen bond donors",
        "compounds",
        "HBD",
        "",
        1,
        False,  # because it clutters horizontally
    ),
    PhysProp(
        "HBA",
        "Hydrogen Bond Acceptors",
        "Number of hydrogen bond acceptors",
        "compounds",
        "HBA",
        "",
        1,
        False,  # same as HBD
    ),
]
PATH2PP = {i.path: i for i in PHYSPROP}
ID2PP = {i.id: i for i in PHYSPROP}


def collection_projection(collection):
    """MongoDB projection for an iterable of PhysProps for the same collection
    Something like:
    {  "_id": False, "dsstox_cid": True,
       "predicted_props.OPERA_MP": True, "predicted_props.OPERA_LogP": True"  }
    i.e. id fields plus all paths.
    """
    ans = {
        "$project": {
            k: k != "_id" for k in [i.path for i in collection] + ["_id", "dsstox_cid"]
        }
    }
    return ans


def query_props(cids):
    """Query properties across collections.

    Maybe should have been done with $lookup rather than $unionWith.

    Args:
        cids (list(str)): the DTX CIDs to lookup props for

    Returns:
        collection_0, query: to be run as DB[collection_0].aggregate(query)
    """
    collections = groupby(PHYSPROP, key=lambda x: x.collection)
    # Nothing special about collection_0, also, PHYSPROP guaranteed(*) to be sorted by
    # collection.  Works even when there's only one collection.
    # (*) no longer true but ok
    collection_0, collection = next(collections)
    cids = list(cids)  # in case cids is a set/dict
    query = [
        {"$match": {"dsstox_cid": {"$in": cids}}},
        collection_projection(collection),
    ]
    # union remaining collections with first
    for collection_i, collection in collections:
        query.append(
            {
                "$unionWith": {
                    "coll": collection_i,
                    "pipeline": [
                        {"$match": {"dsstox_cid": {"$in": cids}}},
                        collection_projection(collection),
                    ],
                }
            }
        )

    return collection_0, query


def flatten(dict_, parent_key="", sep="."):
    """Flatten dict, modified from https://stackoverflow.com/a/6027615/1072212
    {"a": {"b": {"c": 42}}} becomes {"a.b.c": 42}
    """
    items = []
    for key, value in dict_.items():
        new_key = parent_key + sep + key if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))
    return dict(items)


def props_to_dict(props):
    """Convert output from a query using query_props() to a chem -> props mapping
    Given a bunch of results like:
        {'dsstox_cid': 'DTXCID30182',
        'predicted_props': {'OPERA_BP': [343.191],
                            'OPERA_LogP': [3.32044],
                            'OPERA_MP': [152.696]}}
    de-list list results (some aren't), flatten paths to predicted_props.OPERA_MP etc.,
    then convert to IDs from PHYSPROP, and aggregate results for chems., so final result
    is something like:
        {"DTXCID30182": { "BP": 343.191,
                          "MP": 152.696,
                          "mass": 123.45,
                          "logKow": 3.32044 },
         "DTXCID1234": ...
    Note there are separate results for each collection so OPERA_* come in one result
    and mass (from compounds) in another.
    """
    chem = defaultdict(dict)
    for res in props:
        cid = res.pop("dsstox_cid")
        res = flatten(res)
        chem[cid].update(
            {PATH2PP[k].id: v[0] if isinstance(v, list) else v for k, v in res.items()}
        )
    return dict(chem)  # remove defaultdict, cleaner for callers


def gen_local_physprop(chem_ids):
    """Helper for edge cases where we can locally generate pysprop data, currently only
    used for Mass (mol_weight). Only includes/returns generated fields."""
    props = defaultdict(dict)

    if smiles := [
        chem_id for chem_id in chem_ids if ChemID.id_type(chem_id) == ChemID.SMILES
    ]:
        # case: generate mass for custom SMILEs on-the-fly
        for smile in smiles:
            mol = Chem.MolFromSmiles(smile)
            if mol:
                props[smile]["mass"] = Chem.Descriptors.ExactMolWt(mol)
                props[smile]["HBD"] = Descriptors.NumHDonors(mol)
                props[smile]["HBA"] = Descriptors.NumHAcceptors(mol)

    return props


def chem_props(chems):
    """Get props for a list of chem BY CID"""

    coll, query = query_props(chems)
    props = props_to_dict(DB[coll].aggregate(query))

    # NOTE: this removes any (previously) obtained props for each chem_id
    if dne := set(chems) - set(props.keys()):
        # case: there exist(s) non-CID(s) in `chems`
        props.update(gen_local_physprop(dne))

    return props


def _fmt_value(prop_id, value):
    """Use sci. notation if rounding rounds non-zero to zero."""
    text = f"{value:.{ID2PP[prop_id].places}f}"
    if value != 0 and abs(float(text)) <= 0.1:
        return f"{value:.3g}"
    return text


def prop_data(chem_ids):
    """AG Grid flavored data for UI"""
    chem_prop = chem_props(chem_ids)
    prop_ids = set()
    order = [i.id for i in PHYSPROP]
    for props in chem_prop.values():
        prop_ids.update(props)
    # list of all properties found, same order as PHYSPROP
    prop_ids = sorted(prop_ids, key=lambda x: order.index(x))
    data = []
    for prop_id in prop_ids:
        row = {}
        data.append(row)
        row["physchem"] = "Properties"
        row["isPhysProp"] = True
        units = f" ({ID2PP[prop_id].units})" if ID2PP[prop_id].units else ""
        row["ep_name"] = f"{ID2PP[prop_id].name}{units}"
        row["ep_tip"] = f"{ID2PP[prop_id].description}{units}"
        for chem_id in chem_ids:
            value = chem_prop.get(chem_id, {}).get(prop_id, "N/A")
            if isinstance(value, float):
                value = _fmt_value(prop_id, value)
            units = ID2PP[prop_id].units
            row[chem_id] = {"value": value, "cellRenderer": "PlainText"}
            row[chem_id + "_tip"] = f"{value} {units}".strip()

    return data
