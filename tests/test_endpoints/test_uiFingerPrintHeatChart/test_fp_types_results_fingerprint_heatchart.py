"""Tests for heatmap endpoint"""

import pytest

from tests.defs import FP_types
from tests.lib.misc import check_first, check_keys_exist

ENDPOINT = "uiFingerPrintHeatChart"


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_fingerprint_heatchart(
    expected_test_params, run_expected_test
):
    """This is more a test that each FP type returns some actual data than a
    test of uiFingerPrintHeatChart specifically.
    """
    data = run_expected_test(__file__, ENDPOINT, expected_test_params)

    # v4 structural tests
    check_keys_exist(data, ["columns", "data"])
    fp_ids = []
    for column in data["columns"][1:]:
        fp_ids.append(column["field"])
    row_structure = [{fp_id: ["scaled", "value"]} for fp_id in fp_ids]
    row_structure += ["chem_id", "name"]  # not details_link, dropped for SMILES only
    check_first(expected_test_params, data["data"][0]["chem_id"])
