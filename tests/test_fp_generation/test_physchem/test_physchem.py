"""Unlike other FP generation tests which compare calculated Jaccard simliarities with
reference DB data, here we test Euclidian distance simliarities more directly.
"""
from math import sqrt

import numpy as np
import pytest

from genraweb.lib.fp.fputils import physchem_slow
from genraweb.lib.fp.precalc_hpc.fast_jaccard import euclid_calc, fp_query_info
from genraweb.resources import DB


def test_euclid_calc_simple():
    """Basic test"""
    # Random data in different ranges, 10 rows
    fp = np.array(
        [
            np.random.uniform(10, 2000, 10),
            np.random.randint(0, 5, 10),
            np.random.randint(0, 5, 10),
            np.random.uniform(-3, 3, 10),
        ]
    ).T
    # precalc_fp_hpc code normalizes the data before calling euclid_calc so do that
    # here.
    mins = fp.min(axis=0)
    maxs = fp.max(axis=0)
    sc = (fp - mins) / (maxs - mins)
    # Pick a "target chemical", row 6 of 10
    row = 6
    A = sc[row]
    bits = len(A)
    A.shape = (1, bits)
    # Euclidian distance
    sims = 1 - np.sqrt(np.power(sc - A, 2).sum(axis=1)) / sqrt(bits)

    # Check against euclid_calc()
    output = np.zeros(len(sc))
    euclid_calc(sc, None, sc, output, None, row, None)
    # sims[2] = 11  # Confirmed sensible array content with this error 2024-01-03
    assert (sims == output).all()


@pytest.mark.no_smoke  # Failing on one of hundreds of calcs. Don't know why. FIXME
def test_fp_info_physchem():
    """Tests every 10_000th PhysChem FP, but still needs to load all 780k records to get
    comparable answer.
    """
    fpq = fp_query_info("chm_phch")  # MongoDB query/projection for FP lookup
    print(fpq)

    chems: list(str) = []  # every 10_000th chem_id

    for i, rec in enumerate(DB.physchem_fp.find(fpq.query, fpq.proj)):
        if i % 10_000 == 0:  # Grab chem_id for every 10_000 rows
            chems.append(rec["dsstox_cid"])

    phchnn = physchem_slow(DB, chems)

    for chem in chems:  # then simlarity for each 10_000th chem.
        # Get the data from fp_info
        fpi = DB.fp_info.find_one({"dsstox_cid": chem})
        fpi_sims = np.array(fpi["chm_phch"]["no_filter"]["similarities"][:100])
        fpi_nn = np.array(fpi["chm_phch"]["no_filter"]["chem_ids"][:100])
        # fp_info records don't include the initial 1.0 for the target, can't just do
        # [1:101] because if nearest non-self has a sim. of 1., self may not be first.
        nn = phchnn[chem].nn[:100]
        nn_sims = phchnn[chem].sims[:100]
        # Similarity lists can be compared directly
        try:
            assert np.isclose(nn_sims, fpi_sims).all()
        except AssertionError:
            # This debugging info. used during test development, confirmed expected test
            # value contents.
            print("calc", nn_sims[:3], "fp_info", fpi_sims[:3])
            print(
                "target",
                DB.physchem_fp.find_one(fpq.query | {"dsstox_cid": chem}, fpq.proj),
            )
            print(
                "calc",
                DB.physchem_fp.find_one(fpq.query | {"dsstox_cid": nn[0]}, fpq.proj),
            )
            print(
                "fp_info",
                DB.physchem_fp.find_one(
                    fpq.query | {"dsstox_cid": fpi_nn[0]}, fpq.proj
                ),
            )
            raise

        # chem_id ordering is random for matching similarities, so delete ranges of
        # matching similarities.  Initially tried a list / cursor implementation, but
        # that was extremely slow.  np.unique(x, return_counts=True) IDs non-unique
        # values by a count > 1.  An alternative might be sorting lists of tuples
        # (similarity, chem_id) but this works.
        unique, index, count = np.unique(
            fpi_sims, return_index=True, return_counts=True
        )
        unique = index[count == 1][1:]
        # [1:] because could have a block of matching similarities at the end of the
        # data, clipped so it looks like it's unique, so discard least similar obs.
        # [1:] rather than the expected [:-1] because these arrays seem backwards at
        # this point, BUT THAT IS OK
        assert (nn[unique] == fpi_nn[unique]).all()
