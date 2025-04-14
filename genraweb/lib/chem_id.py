"""
chem_id.py - Chem. ID utils.
"""
import enum
import re
from collections import defaultdict
from functools import reduce
from itertools import chain

import numpy as np
from rdkit import Chem
from rdkit.Chem.Descriptors import ExactMolWt

from genraweb.lib.logging import logger
from genraweb.resources import DB, redis_cache

CASRN_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

UNNAMED = "Unnamed chemical"
NOTNAMES = (None, False, "", 0, 0.0, np.nan, [], {})


class ChemIDType(enum.Enum):
    """Known chem. ID types.  Client code should use ChemID, not ChemIDType.  ChemID has
    the same members, they're added after ChemID is defined (see below).
    """

    CID = enum.auto()  # DSSTOX / ChemReg DB Compound ID
    SID = enum.auto()  # DSSTOX / ChemReg DB Substance ID
    CASRN = enum.auto()  # American Chemical Soc. code
    SMILES = enum.auto()  # Simplified Molecular-Input Line-Entry System
    NAME = enum.auto()  # everything else


class ChemID_Class:
    """Chem. ID utils.

    This class is really just a namespace to collect functions, but some features
    benefit from a singleton instance.  For client-code convenience instantiate that
    instance in this module after this class def., hence _Class.
    """

    # Field *usually* used for IDs, mostly for use in chem_id_search().
    # Support a list of one or more alternate field names.  dtx* forms are mostly used
    # in the FP collections which we could change, but a collection we can't
    # conveniently change will likely crop up.
    # Order is used for preference / promotion.
    # NOTE: `chem_id_search(..., index=True)` relies on ordering of CID/SID field names
    id_field = {
        ChemIDType.CID: ["dsstox_cid", "dtxcid"],
        ChemIDType.SID: ["dsstox_sid", "dtxsid"],
        ChemIDType.CASRN: ["casrn"],
        ChemIDType.SMILES: ["smiles"],
        ChemIDType.NAME: ["name"],
    }

    def __init__(self):
        # ordered preference for promoting IDs, CID > SID > CASRN > SMILES > name
        # sum(, start=[]) to flatten iterable of lists
        self.ordered_fields = sum(self.id_field.values(), start=[])

        # For client code convenience, make ChemID.CID == ChemIDType.CID etc.
        # Allows `from chem_id import ChemID` to be a one stop import, and avoids
        # ChemID.type.CID etc.
        for chem_id_type in ChemIDType:
            setattr(self, chem_id_type.name, chem_id_type)

    def chem_id(self, chem):
        """Pick the best ID field from chem (dict).
        Preference order defined by ordering of all values in self.ordered_fields.
        """
        for field in self.ordered_fields:
            chem_id = chem.get(field)
            if chem_id:
                return chem_id

    @staticmethod
    def id_type(text):
        """Work out chem. ID type.  NOTE: ChemIDType.NAME is a catch all."""

        if text is None:
            return ChemIDType.NAME
        elif text[:6].upper() == "DTXCID":
            return ChemIDType.CID
        elif text[:6].upper() == "DTXSID":
            return ChemIDType.SID
        elif CASRN_RE.match(text):
            return ChemIDType.CASRN
        elif " " not in text.strip() and Chem.MolFromSmiles(text):
            # MolFromSmiles("C 15") returns non-None, so we need to check for space
            return ChemIDType.SMILES

        return ChemIDType.NAME

    def canonical_smile(self, smile):
        return Chem.MolToSmiles(Chem.MolFromSmiles(smile), kekuleSmiles=True)

    def chem_id_search(self, chem_ids, index=None):
        """Make mongo search filter for chem or list of chem. IDs

        index: None => ignored, True => fail on unindexed fields,
               False => warn on unindexed fields and remove them from search
        """
        if isinstance(chem_ids, str):
            chem_ids = [chem_ids]
        lists = defaultdict(list)  # map each ID type found to its own list of values
        for chem_id in chem_ids:
            id_type = self.id_type(chem_id)
            if id_type in self.id_field:
                if id_type in (ChemIDType.SID, ChemIDType.CID):
                    chem_id = chem_id.upper()
                else:
                    # unindexed fields
                    if index is not None:
                        logger.warning("This ID type isn't indexed: %s", chem_id)
                        if index is True:
                            return None
                        else:
                            # remove from search
                            continue
                if id_type == ChemIDType.SMILES:
                    canonical_smile = self.canonical_smile(chem_id)
                else:
                    canonical_smile = None
                # some ID types have multiple fields, e.g. dtxcid and dsstox_cid
                for field in self.id_field[id_type]:
                    lists[field].append(chem_id)
                    if canonical_smile and canonical_smile != chem_id:
                        lists[field].append(canonical_smile)
                    if index is not None:
                        break  # we ignore "dtxcid"/"dtxsid", only "dsstox_*"
                if id_type == ChemIDType.NAME:
                    # Could be a SMILES that is in the DB that RDKit didn't parse
                    for field in self.id_field[ChemID.SMILES]:
                        lists[field].append(chem_id)

            else:
                logger.warning("No DB field for %s", id_type)
        search = {
            "$or": [
                # {"aField": {"$in": aList}} or {"aField": aValue} if only one
                {key: ({"$in": values} if len(values) > 1 else values[0])}
                for key, values in lists.items()
            ]
        }
        if len(search["$or"]) == 0:  # index is not None, but no indexed chem_id
            return None
        if len(search["$or"]) == 1:  # drop $or if only one ID type
            search = search["$or"][0]
        return search

    @redis_cache
    def promote_id(self, chem_id):
        """Return a "promoted" chem_id.  There are cases (cacheing images in a DB for
        example) where you want to use the same ID for a chem so if it's queried via
        SMILES and name and SID, better if you use CID for storing the cached copy.

        Returns promoted_chem_id, chem

        where chem is the compounds collection dict for this chem_id, or None.
        promoted_chem_id will be chem_id if no promotion found / needed.

        This method relies on the compounds collection, although a SMILES not present
        in the collection will be returned unchanged.

        ASSUMPTION: All compounds entries have CID OR SID
        """
        # search even if it's a CID, so we can return chem
        chem = self.compounds_chem(chem_id)
        if chem:
            return self.chem_id(chem), chem
        return chem_id, None

    @redis_cache
    def compounds_chem(self, chem_id):
        """Query compounds for chem_id, with cacheing"""
        search = self.chem_id_search(chem_id, index=True)
        if search is None:
            # case: unindexed chem_id type, will take longer
            search = self.chem_id_search(chem_id)
        return DB.compounds.find_one(search, self.core_fields())

    def core_fields(self):
        """Core fields for a chemical, as a MongoDB projection, so includes _id"""
        core = [*self.ordered_fields, "is_markush", "mol_weight"]
        # could add InChlKey etc.
        core = {i: True for i in core}
        core["_id"] = False
        return core

    @redis_cache
    def chem_ids_in_collection(self, collection_name):
        """Return one chem_id for each record in collection, in descending preference
        order.

        For 1.4M chem in compounds, takes about 2 secs, plus the 5.4 secs for the query.
        For the 1006 chem in toxrefdb_fp it's < 0.01 secs.
        """
        projection = {i: True for i in self.ordered_fields}
        projection["_id"] = False
        result = []
        for chem in DB[collection_name].find({}, projection):
            if not chem:  # none of the fields are present
                continue
            if (chem_id := self.chem_id(chem)) is not None and chem_id not in result:
                result.append(chem_id)

        # logger.info("Filtering by %s, %s", collection_name, len(result))
        return result

    def chem_from_smiles(self, smiles):
        """Make a chemical from SMILES"""
        return {
            "chem_id": smiles,
            "mol_weight": ExactMolWt(Chem.MolFromSmiles(smiles)),
            "name": "Unnamed chemical",
            "smiles": smiles,
        }

    def chem_id_proj(self, include_core_fields=False):
        """Returns a pymongo projection (nested dicts) that gives field 'chem_id' that
        uses the promoted id field according to rank defined in this class.

        Currently returns something like:
        {
            "_id": false,
            "chem_id": {
                "$ifNull": [
                    "$dsstox_cid",
                    {
                        "$ifNull": [
                            "$dtxcid",
                            {
                                "$ifNull": [
                                    "$dsstox_sid",
                                    {
                                        "$ifNull": [
                                            "$dtxsid",
                                            {
                                                "$ifNull": [
                                                    "$casrn",
                                                    {
                                                        "$ifNull": [
                                                            "$smiles",
                                                            "$name"
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
        """

        fields = list(chain.from_iterable(self.id_field.values()))
        # assumes >= 3 items in fields
        proj = {
            "chem_id": {
                "$ifNull": reduce(
                    lambda proj, field: [f"${field}", {"$ifNull": proj}],
                    reversed(fields[:-2]),
                    [f"${field}" for field in fields[-2:]],
                )
            },
            "_id": False,
        }
        if include_core_fields:
            proj.update(self.core_fields())
        return proj


# See docstring for ChemID_Class, this (ChemID) is primary export of this file.
ChemID = ChemID_Class()


def main():
    """Test speed - using eval to write ChemID.chem_id is marginally faster, but not
    enough to justify using eval - 7% at most.

    This is just speed evaluation code, not used.
    """

    import timeit  # noqa

    def dicts():
        for i in range(1_000_000):
            yield {"casrn": "2-222-2"}

    # first() is slightly faster with external fields calc. which eliminates the `if`.
    # fields = sum(ChemID.id_field.values(), start=[])

    def first(d, __fields=[]):
        if not __fields:
            __fields[:] = sum(ChemID.id_field.values(), start=[])
        for field in __fields:
            if field in d:
                return d[field]

    chem_id = eval(
        "lambda x: "
        + " or ".join(f"x.get('{i}')" for i in sum(ChemID.id_field.values(), start=[]))
    )

    eval_ = timeit.timeit(lambda: list(map(chem_id, dicts())), number=10)
    for_ = timeit.timeit(lambda: list(map(first, dicts())), number=10)
    print(eval_)
    print(for_)
    print((for_ - eval_) / eval_)


if __name__ == "__main__":
    main()
