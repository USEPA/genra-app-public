"""Functions to *READ* from fp_info."""
from collections import defaultdict

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO
from genraweb.lib.logging import logger
from genraweb.resources import DB, redis_cache

COL = FPGen.fp_collection_names()
DS = FPGen.fp_collection_paths()


def _sum_of_n(fp_hits, min_s0=None):
    """Sum of all {"n": x} recursively in dict fp_hits, used to get total FP in mongo
    search results.  For some FP n is split between pos. effect and neg. effect, hence
    need for this, should also work on cross collection searches if that approach was
    used.
    """
    total = 0
    if "n" in fp_hits:
        if min_s0 is None or fp_hits.get("max_s0", 1) >= min_s0:
            total += fp_hits["n"]
    for key, value in fp_hits.items():
        if isinstance(value, dict):
            total += _sum_of_n(value, min_s0=min_s0)
    return total


@redis_cache(to_tuple_keys=["chem_ids"])
def fp_n_for_chems(*, chem_ids, min_s0=None):
    """Return FP n (len(ds)) for chems in chem_ids

    E.g. {
        "id0": {'chm_mrgn': 24, 'chm_httr': 21, 'chm_ct': 21, 'bio_txct': 476},
        "id1": {'chm_mrgn': 42, 'chm_httr': 12, 'chm_ct': 12, 'bio_txct': 746}
    }

    Used for /api/genra/v4/uiSetup (which FP are available for chem.) and
    /api/genra/v4/uiFingerPrintHeatChart

    Too slow to call repeatedly with single chems (ok for uiSetup), but calling with
    list of chems fast enough.  Makes one query per FP type.

    Could be made faster by using mongo DB `$lookup` or building a collection of pre-
    calculated values.
    """
    if not chem_ids:  # avoid mongodb error on {dsstox_cid: {$in: []}}
        logger.warning("fp_n_for_chems called with empty list")
        return {}

    fp_n = {i: {} for i in chem_ids}
    # Accumulate results spread across collections - toxref has FP in tox_fp1 and
    # tox_fp2, although we only actually count FP in tox_fp2, but this code handles FP
    # split across mulitple collections.
    # Use index because target chem_id is promoted and neighbor chem_id should also be
    # SID or CID.
    search = ChemID.chem_id_search(chem_ids, index=False)  # mongo search term
    if search is None:
        # custom SMILE, no data to return
        return fp_n
    for fp_class in FPGen.FPClass.values():
        for chem_id in chem_ids:
            fp_n[chem_id][fp_class.fp_id] = 0
        collections = defaultdict(list)
        for fp_field in fp_class.fp_fields if hasattr(fp_class, "fp_fields") else []:
            # Get all paths to FPs by collection for this FP, e.g. pos and neg paths to
            # {n: x} in toxref, tox_fp2.fp_[pos|neg]
            collections[fp_field.collection].append(fp_field.path)
        for collection, paths in collections.items():
            projection = {f"{path}.n": True for path in paths}
            projection.update({"_id": False, "dsstox_cid": True, "dsstox_sid": True})
            hits = DB[collection].find(search, projection)
            for hit in hits:
                for hit_id in hit.get("dsstox_cid"), hit.get("dsstox_sid"):
                    # If more than one ID refers to the same record, update all.  I.e.
                    # the chem_ids list had more than one ID for the same chemical, just
                    # return the same result for the redundant IDs.
                    if hit_id in chem_ids:
                        fp_n[hit_id][fp_class.fp_id] += _sum_of_n(hit, min_s0=min_s0)

    return fp_n


def chem_nn(
    chem_id: str,  # chem. ID
    fp_id: str,  # FP ID
    sel_by: str = "no_filter",  # filter (select) by presence of data
    min_similarity: float = 0.1,  # aka s0
    max_nghbrs: int = 10,  # aka k0
    index_only: bool = False,  # if True, will only search on index ID types
) -> list:
    """Try and find nearest neighbors in fp_info."""
    if max_nghbrs > 100:
        # Currently 100 nearest neighbors are only supported
        # NOTE: target chem is not included (i.e., up to 101 in size including target)
        return None

    search_index_mode = True  # indexed fields only

    query = ChemID.chem_id_search(chem_id, index=search_index_mode)
    if query is None and index_only:
        # if there isn't an index for IDs, don't perform a long search
        return None
    elif query is None:
        # may take a while
        search_index_mode = None  # ignore field indexing
        query = ChemID.chem_id_search(chem_id, index=search_index_mode)
    key = FPGen.fp_info_key(fp_id=fp_id, sel_by=sel_by)
    query[key] = {"$exists": True}
    fps = DB[FP_INFO].find_one(query)
    if fps is None:
        return None
    result = {chem_id: {"similarity": 1.0}}
    for nn_id, nn_similarity in zip(
        fps[fp_id][sel_by]["chem_ids"], fps[fp_id][sel_by]["similarities"]
    ):
        if (
            len(result) == max_nghbrs + 1
            or nn_similarity < min_similarity
            or nn_similarity <= 0  # filter bad data in fp_info
        ):
            break
        result[nn_id] = {"similarity": nn_similarity}

    # Fill in name etc. etc. ASSUMES no SID -> CID promotion to mess things up
    # ALSO - searching fp_info because compounds is so slow by comparison - NO, see *
    proj = ChemID.chem_id_proj(include_core_fields=True)
    proj["fpds"] = f"${DS.get(fp_id)}.ds"
    found = 0
    for chem in DB[COL.get(fp_id)].find(
        # (*) NOT searching fp_info, searching FP's collection.  Changing to fp_info or
        # compounds fails, presumably because these records are treated as FP records,
        # i.e. .fp_fields is applied, downstream, somewhere.  Matters because 'name' is
        # coming from the FP's collection therefore out of sync. names possible.
        # See misc/collections_comparison/sid_cid_unification.py for name unification
        ChemID.chem_id_search(result, index=search_index_mode),
        proj,
    ):
        found += 1
        result[chem["chem_id"]].update(chem)
    if found != len(result):
        logger.error("ERROR: *** fp_info out of date? ***")
        return None

    return list(result.values())
