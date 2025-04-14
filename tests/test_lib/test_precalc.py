from collections import defaultdict

import numpy as np
import pytest

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import FP_INFO, is_hybrid_fp
from genraweb.lib.mongofp_NN import searchFP
from genraweb.resources import DB
from tests.defs import FP_types


@pytest.mark.very_slow
@pytest.mark.parametrize(
    "expected_test_params", FP_types("precalc"), ids=map(str, FP_types("precalc"))
)
def test_fp_types_precalc(expected_test_params):
    """Tests that the nearest neighbors precalculated in fp_info are consistent with
    what's being calculated by existing mongo infrastructure (searchFP).

    Doesn't cover PhysChem because that uses Euclid distance and is tested elsewhere.

    For the toxcast/toxref filters, tiebreakers are determined by the chemical's
    availability of the filter data (e.g., number of toxcast assays that this chemical
    has positives for.) However, with no_filter, we can't guarantee mongo and scikit
    will return the same ordering.  Therefore, for each of precalc and searchFP, buckets
    are constructed, where, for each similarity, all equidistant chemicals are placed
    into the same bucket. For a given similarity, precalc's bucket is compared with
    searchFP's bucket. This is done for all similarities except for the lowest
    similarity value, as they may have different chemicals - e.g., 102nd chem for mongo,
    99th for scikit.
    """
    target_chem_id = expected_test_params.chem_id
    target_chem_id, _ = ChemID.promote_id(target_chem_id)
    fp_id = expected_test_params.fp_id
    sel_by = expected_test_params.sel_by

    # how many nearest neighbors to compare; 100 is current max on precalc
    num = 100
    # what decimal place to check similarities on
    decimal_place = 10

    precalc_chem = DB[FP_INFO].find_one(
        ChemID.chem_id_search(target_chem_id),
        {"_id": False, "precalc": f"${fp_id}.{sel_by}"},
    )

    if precalc_chem is None or is_hybrid_fp(fp_id) or "," in fp_id:
        # custom SMILE and custom hybrid don't have precalc
        # TODO: could 100 be sufficient?
        return

    precalc_chem_ids = precalc_chem["precalc"]["chem_ids"][:num]
    precalc_similaritys = precalc_chem["precalc"]["similarities"][:num]

    nns = searchFP(
        chem_id_in=target_chem_id,
        fp=fp_id,
        sel_by=sel_by,
        simple=False,  # so it calculates instead of looking up precalc
        max_hits=num + 1,  # because target chem gets included
    )
    assert nns[0]["chem_id"] == target_chem_id
    assert nns[0]["similarity"] >= 1
    # nns_chem_ids = [chem["chem_id"] for chem in nns][1:]
    # nns_jaccards = [chem["jaccard"] for chem in nns][1:]

    # create buckets
    precalc_buckets = defaultdict(set)
    nns_buckets = defaultdict(set)
    for precalc, nn in zip(
        zip(precalc_chem_ids, precalc_similaritys),
        nns[1:],  # first chem is target chem
    ):
        precalc_chem_id, precalc_similarity = precalc
        nn_chem_id, nn_similarity = nn["chem_id"], nn["similarity"]

        precalc_buckets[round(precalc_similarity, decimal_place)].add(precalc_chem_id)
        nns_buckets[round(nn_similarity, decimal_place)].add(nn_chem_id)

    # compare buckets
    # Check similarities match up - they differ when rounded to ~4 decimal places,
    # partly because values are truncated to speed up insertion into mongo.
    precalc_values = np.array(list(precalc_buckets.keys()))
    nns_values = np.array(list(nns_buckets.keys()))
    assert np.allclose(precalc_values, nns_values, atol=1e-3)
    # assert set(precalc_buckets.keys()) == set(nns_buckets.keys())

    # Compare buckets in sorted order, since keys aren't comparable.
    precalc_keys = sorted(list(precalc_buckets.keys()))
    nns_keys = sorted(list(nns_buckets.keys()))
    for idx in range(len(precalc_keys)):
        if idx == 0:
            # case: lowest similarity, they may not match up
            # could uncomment below and see if they at least have something in common
            # assert precalc_buckets[jaccard] & nns_buckets[jaccard]
            continue
        else:
            # check same equidistant set of chemicals
            assert precalc_buckets[precalc_keys[idx]] == nns_buckets[nns_keys[idx]]

    # print(f"{target_chem_id} passed the test on {len(precalc_buckets)} buckets...")
