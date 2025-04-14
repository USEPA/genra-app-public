"""
Test random selection of chem. against responses scraped from NCD.
Doesn't work when running pytest in parallel mode.
Requires old DB, so historical interest only.
"""
############################################################
#                                                          #
#     Obsolete test disabled with notest_ below            #
#     Also side effect set up code commented out           #
#                                                          #
############################################################

import json
import urllib

import data_comparison
import pathlib2
import pytest
import requests
import setup


def make_request(api_url, item):
    endpoint = item["endpoint"]

    if endpoint == "runGenRAPerfPred":
        url = urllib.parse.urljoin(api_url, "api/genra/v3/runGenRAPerfPred")
        return requests.post(
            url,
            data=json.dumps(item["data"]["request_body"]),
            headers={"Content-type": "application/json", "Accept": "*/*"},
        )

    else:
        url = urllib.parse.urljoin(
            api_url,
            "api/genra/v3/" + endpoint + "/?dsstox_cid=" + item["chemical"] + "&",
        ) + urllib.parse.urlencode(
            {
                "k0": "10",
                "fp": "chm_mrgn",
                "sel_by": "tox_txrf",
                "summarise": "tox_txrf",
                "sumrs_by": "tox_fp",
                "s0": "0.1",
                "neg0": "1",
                "pos0": "1",
            }
        )
        return requests.get(url)


# controls_json_full_path = (pathlib2.Path(__file__).parent).joinpath("controls.json")
# pytest_setup = setup.SetUp(str(controls_json_full_path))
# items, ids = pytest_setup.run()


# @pytest.mark.slow_api
# @pytest.mark.io
# @pytest.mark.compare_with_ncd
# @pytest.mark.parametrize("item", items, ids=ids)
def notest_test_endpoint(api_url, item):
    """
    Compare endpoint response for each substance-endpoint combination, as defined in controls `controls.json`.
    If the controls are left alone, currently, it will randomly select one chemical and test them against NCD endpoints.
    You should be able to test a specific chemical (or chemical in a specific file).
    You should be able to test a specific endpoint too.
    See DESELECT_ to remove items from test consideration.

    Documentation is a bit skimpy, but this will be updated later as these tests get upgraded/refactored in a PR next sprint.

    The goal is to keep using this structure and expand the endpoints being tested to include the ui endpoints.
    """

    response = make_request(api_url, item)

    assert response.status_code == item["data"]["status_code"]
    if response.ok:
        # response should be json if everything was good
        assert "application/json" in response.headers["Content-Type"]
        data_comparison.compare_data(
            expected_data=item["data"]["response_body"],
            got_data=response.json(),
            endpoint=item["endpoint"],
        )
