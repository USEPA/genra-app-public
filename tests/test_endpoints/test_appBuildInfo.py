"""Tests appBuildInfo"""
import pytest
import requests

from tests.lib.check_response import check_response_basics  # noqa: PLE0401


@pytest.mark.slow_api
def test_app_build_info(api_url):
    """Tests the /appBuildInfo/ endpoint.
    Calls on the endpoint with num_files=3, checks response JSON structure"""

    resp = requests.get(f"{api_url}/api/genra/v3/appBuildInfo/?num_files=3")
    info = check_response_basics(resp)

    # check python version
    assert "python_version" in info

    # check mongodb
    assert "mongodb" in info
    sub_keys = ["host", "port", "database", "collections"]
    for sub_key in sub_keys:
        assert sub_key in info["mongodb"]

    # check git log
    assert "git_log" in info
    assert len(info["git_log"]) == 5

    # check build & start times
    assert "time_image_built" in info
    assert "time_app_start" in info

    # recent files
    assert "recent_files" in info
    assert len(info["recent_files"]) == 3
