"""Test healthCheck endpoint"""
import requests

from tests.lib.check_response import check_response_basics


def test_healthCheck_mongodb(api_url, get_env_var):
    """Tests that the structure of healthCheck endpoint response has the necessary
    components/fields - including if the healtcheck failed."""

    resp = requests.get("%s/api/genra/v3/healthCheck" % api_url)
    healthcheck_response = check_response_basics(resp)

    assert "generated" in healthcheck_response

    check_keys = {"DB": ["status"], "CACHE": ["status"]}

    for check_type, data_keys in check_keys.items():
        assert check_type in healthcheck_response
        check_obj = healthcheck_response[check_type]
        assert "status" in check_obj
        if "error" in check_obj:
            assert "FAILED" in check_obj["status"]
        else:
            assert all((data_key in check_obj for data_key in data_keys))
            assert "PASSED" in check_obj["status"]
