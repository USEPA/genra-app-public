"""Tests for uiAssayList endpoint"""
import pytest

from tests.defs import FP_types
from tests.lib.misc import check_first, check_keys_exist

ENDPOINT = "uiAssayList"


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_assay_list(expected_test_params, run_expected_test):
    """This is more a test that each FP type returns some actual data than a
    test of uiAssayList specifically.
    """
    data = run_expected_test(__file__, ENDPOINT, expected_test_params)

    chem_ids = []
    for column in data["columns"][1:]:
        chem_ids.append(column["field"])
    check_first(expected_test_params, chem_ids[0])
    row_keys = (
        chem_ids + [f"{chem_id}_tip" for chem_id in chem_ids] + ["ep_name", "ep_tip"]
    )
    for row in data["data"]:
        if row.get("ep_name") == "NO_DATA":
            continue
        check_keys_exist(row, row_keys)
