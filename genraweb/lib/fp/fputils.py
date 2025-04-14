"""
fputils.py - Utility methods for dealing with Fingerprints

Terry N. Brown Brown.TerryN@epa.gov Fri 23 Jul 2021 12:03:12 AM UTC
"""
import os
from collections import namedtuple
from math import sqrt

import numpy as np

from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.precalc_hpc.fast_jaccard import fp_query_info
from genraweb.lib.logging import logger

COL = FPGen.fp_collection_names()
DS = FPGen.fp_collection_paths()

# This is a convenient place to import this from
FP_INFO = os.getenv("GENRA_FP_INFO_COLLECTION", "fp_info")
if FP_INFO != "fp_info":  # results can be confusing is set incorrectly
    logger.warning("### GENRA_FP_INFO_COLLECTION is set to '%s' ###", FP_INFO)


def fp_hybrid_name_from_lists(data):
    """Make a hybrid FP name like "chm_mrgn_W2_and_chm_httr_W1_and_tox_txrf_W1" from
    comma separated request params.
    """
    fp = data["fp"].split(",")
    weight = (data.get("fp_weight") or "").split(",")
    if len(fp) == 1:
        return FPGen.allowed_fps(fp[0])
    assert len(fp) == len(weight)
    fp = FPGen.allowed_fps(fp)
    return "_and_".join(f"{f}_W{w}" for f, w in zip(fp, weight))


def is_hybrid_fp(fp):
    """See if fp references a hybrid FP."""
    return "_and_" in fp and "_W" in fp


def parse_fp(fp):
    """Parses an FP key and returns a list of FPs and a list of respective weights.

    Each (fp_key, weight) pair is formatted as: "{fp_key}_W{weight}" , where:
      - <fp_key> is a supported FP key (e.g., "chm_mrgn", "bio_txct")
      - <weight> is any float/int corresponding to relative weight for that FP

    Multiple pairs may be joined with string "_and_", so for example:
      - "chm_mrgn_W2_and_chm_httr_W1_and_tox_txrf_W1" would be
        50% Morgan and 25% Torsion and 25% Toxref
    """

    if fp in ("multitarget", "user-defined"):
        return [fp], [1]
    if not is_hybrid_fp(fp):
        return FPGen.allowed_fps([fp]), [1]

    fp_weight_pairs = fp.split("_and_")
    fps, weights = [], []
    for pair in fp_weight_pairs:
        fp, weight = pair.split("_W")
        fps.append(fp)
        weights.append(float(weight))
    return FPGen.allowed_fps(fps), weights


PhysChemNN = namedtuple("PhysChemNN", "nn sims")


def physchem_slow(DB, chems):
    """A slow physchem NN calc. used for the hybrid case, and in tests.

    Placed here to avoid circular import issues.
    """
    fpq = fp_query_info("chm_phch")  # MongoDB query/projection for FP lookup

    recs: list((float, int, int, float)) = []  # all ds data
    all_chems: list(str) = []  # all chem_ids for lookup

    for i, rec in enumerate(DB.physchem_fp.find(fpq.query, fpq.proj)):
        recs.append(list(rec["phch"]["ds"].values()))
        # For NN lookup, building 780k list by repeated .append() - speed acceptable
        all_chems.append(rec["dsstox_cid"])
    # Convert to arrays for indexing
    all_chems = np.array(all_chems)
    fp = np.array(recs)
    # Calc. normalized Euclidian similarity, first normalize
    mins = fp.min(axis=0)
    maxs = fp.max(axis=0)
    sc = (fp - mins) / (maxs - mins)

    results = {}
    for chem in chems:  # then simlarity for each 10_000th chem.
        row = np.where(all_chems == chem)[0][0]
        A = sc[row]
        bits = len(A)
        A.shape = (1, bits)
        sims = 1 - np.sqrt(np.power(sc - A, 2).sum(axis=1)) / sqrt(bits)
        order = np.flip(np.argsort(sims))
        results[chem] = PhysChemNN(
            nn=all_chems[order][all_chems[order] != chem],
            sims=sims[order][all_chems[order] != chem],
        )
    return results
