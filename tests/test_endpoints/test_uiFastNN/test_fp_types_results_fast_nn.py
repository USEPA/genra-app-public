"""Tests for fast NN endpoint"""

import pytest

from genraweb.lib.mongofp_NN import searchFP
from tests.defs import FP_types

ENDPOINT = "uiFastNN"


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_fast_nn(expected_test_params, run_expected_test):
    """This is more a test that each FP type returns some actual data than a
    test of uiRadialVue specifically.
    """
    data = run_expected_test(__file__, ENDPOINT, expected_test_params)

    assert "edges" in data
    assert "nodes" in data
    for edge in data["edges"]:
        assert edge["from"] is not None
        assert edge["to"] is not None

    # uiFastNN handles "," lists differently
    if data["edges"] and "," not in expected_test_params.fp_id:
        neighbors = searchFP(
            chem_id_in=expected_test_params.chem_id,
            fp=expected_test_params.fp_id,
            sel_by=expected_test_params.sel_by,
            s0=expected_test_params.s0,
            max_hits=expected_test_params.k0,
            simple=False,
        )
        assert len(data["edges"]) >= len(neighbors) - 1  # - 1 if one step, no target
        immediate_neighbors = [
            edge["to"] for edge in data["edges"] if edge["step"] == 0
        ]
        cids = [chem.get("dsstox_cid") for chem in neighbors]
        sids = [chem.get("dsstox_sid") for chem in neighbors]
        set(immediate_neighbors).issubset(set(cids) & set(sids))
