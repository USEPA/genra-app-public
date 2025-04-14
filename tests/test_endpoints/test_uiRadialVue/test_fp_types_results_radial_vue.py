"""Tests for radial view endpoint and chemNN domain API."""
import logging
import os
from typing import Callable

import pytest
import requests

from genraweb.lib.chem_id import ChemID
from tests.conftest import make_url
from tests.defs import ExpectedTestParams, FP_types
from tests.lib.check_response import check_response_basics
from tests.lib.misc import check_first, print_data

logger = logging.getLogger("genra_top")
ENDPOINT = "uiRadialView"
CHEM_NN_TEST_N = 150  # This many NN to test chemNN with more than fp_info pre-calc.


# FP_types(ENDPOINT) will work with either Vue or View in parametrize() below.
@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_radial_vue(
    expected_test_params: ExpectedTestParams, run_expected_test: Callable
) -> None:
    """More a test that each FP type returns some actual data.

    Than a test of uiRadialVue specifically.
    """
    data = run_expected_test(__file__, ENDPOINT, expected_test_params)

    assert "result" in data
    result = data["result"]
    assert set(("dtxcid", "dtxsid", "chem_id")) & set(result[0])
    assert isinstance(result, list)
    check_first(expected_test_params, result[0]["chem_id"])

    # removed "dtxcid" for simplicity
    keys = ["name", "value", "selected", "weight", "similarity_tag"]
    if os.environ.get("GENRA_DETAILS_LINK", "").strip() and ChemID.id_type(
        expected_test_params.chem_id
    ) in (ChemID.CID, ChemID.SID):
        keys.append("details_link")

    for elem in result:
        assert isinstance(elem, dict)
        assert all(key in elem for key in keys), set(keys) - set(elem)

    check_domain_api(expected_test_params, data)
    # print statements will only execute on failure, may comment/un-comment.
    print_data(data)


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
def test_fp_types_results_chem_nn(run_expected_test: Callable) -> None:
    """Singleton test for more than 100 NN, see defs.h."""
    etp = ExpectedTestParams(
        "chm_mrgn", "DTXCID30182", CHEM_NN_TEST_N, 0.0, minn=10, maxn=10
    )
    data = run_expected_test(__file__, "chemNN", etp)

    assert len(data) >= CHEM_NN_TEST_N
    assert 0.0 + data[-1]["similarity"]  # is a non-zero number


def check_domain_api(etp: ExpectedTestParams, ui_data: dict) -> None:
    """Check domain API matches."""
    url = make_url(etp, "chemNN")
    logger.info(url)
    resp = requests.get(url)  # noqa: S113 no timeout ok for test
    domain_data = check_response_basics(resp)
    # Target should always be first.
    assert ui_data["result"][0]["chem_id"] == domain_data[0]["chem_id"]
    for ui_datum, domain in zip(ui_data["result"], domain_data, strict=False):
        # Have to handle ties the same way to compare chem. IDs, done elsewhere
        # but skip here for now.
        # assert ui_datum["chem_id"] == domain["chem_id"], (ui_datum, domain)
        assert ui_datum["value"] == domain["similarity"], (ui_datum, domain)
