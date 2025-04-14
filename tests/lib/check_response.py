import os

import pytest


def is_notfound_error(response_dict):
    """(DEPRECATED) checks if the dictionary object (a response JSON) is the genra default
    Notfound error"""
    return "error" in response_dict and response_dict["error"] == "Notfound"


def skip_if_not_local_dev():
    genra_deployment_type = os.environ.get("GENRA_DEPLOYMENT_TYPE", "")
    if genra_deployment_type == "LOCAL_DEV":
        return
    else:
        pytest.skip("GENRA_DEPLOYMENT_TYPE is not set to LOCAL_DEV")


def check_response_basics(response):
    """checks some basic desired traits in an API response with assertion statements:
    - HTTP 200 status
    - valid json response
    - not a custom error not found JSON object

    Args:
      response: requests.Reponse object
    """

    # check 200 ok
    assert response.ok

    # check that it's a json response
    assert "application/json" in response.headers["Content-Type"]
    data = response.json()

    return data
