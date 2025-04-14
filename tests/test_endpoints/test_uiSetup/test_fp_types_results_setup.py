"""Tests for uiSetup.py"""

import dataclasses

import pytest
import requests

from tests.defs import FP_types
from tests.lib.check_response import check_response_basics
from tests.lib.misc import print_data

ENDPOINT = "uiSetup"

ERRORS = [
    {"search": "Cedarwood oil", "expects": ["Cedarwood oil", "DTXSID8030978"]},
    {"search": "no such chem", "expects": ["no such chem"]},
    {"search": "DTXSID0034695", "expects": []},  # bio. FP exist for this SID only chem.
    {"search": "DTXCID401324493", "expects": ["Markush", "DTXCID401324493"]},
]


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_setup(expected_test_params, run_expected_test, calibrate):
    """tests/conftest.py limits this to two cases specific to uiSetup.py"""
    etp = dataclasses.replace(
        expected_test_params,
        # extra=f"&chem_id={expected_test_params.chem_id}",
        api_version="v4",
    )
    data = run_expected_test(__file__, ENDPOINT, etp)

    if calibrate:
        return

    for key in "neighbor_by", "filter_by":
        assert key in data, key
    # check data_exists makes sense
    data_exists = len([i for i in data["neighbor_by"] if i["data_exists"]])
    if expected_test_params.chem_id == "DTXCID30182":  # BPA
        # all but bio_htpp_* and bio_pest
        assert data_exists == len(data["neighbor_by"]) - 3
    elif expected_test_params.chem_id == "DTXCID90150942":  # FOOF
        data_exists == 4  # chem. FP only
    # print statements will only execute on failure, may comment/un-comment.
    print_data(data)


@pytest.mark.parametrize("error", ERRORS, ids=[str(i["search"]) for i in ERRORS])
def test_ui_setup_error_messages(error, api_url):
    url = api_url + f"/api/genra/v4/uiSetup?chem_id={error['search']}"
    resp = requests.get(url)
    data = check_response_basics(resp)
    for expect in error["expects"]:
        assert expect in data["error_msg"], (expect, data["error_msg"])
