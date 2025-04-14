"""test_swagger.py - tests for checking swagger doc."""
import os

import requests
from openapi_spec_validator import validate

from genraweb.defs import EXTRA_FP_IDS
from genraweb.lib.fp.fpclass import FPGen
from tests.lib.check_response import check_response_basics


def test_swagger_up(api_url):
    """Check that we can access the swagger interface."""
    api_url = api_url.replace("/genra-api", "/openapi")
    resp = requests.get(f"{api_url}/swagger")
    # Don't use check_response_basics() because that tests response is JSON.
    resp.raise_for_status()
    # Knowing the expected endpoints are listed would be more informative, but
    # would require JS page rendering.
    assert b"swagger/css" in resp.content


def test_api_spec_content(api_url):
    """Check API spec. contains expected content."""
    api_url = api_url.replace("/genra-api", "/openapi")
    resp = requests.get(f"{api_url}/openapi.json")
    check_response_basics(resp)
    spec = resp.json()
    ui_endpoints = (  # Doesn't need to be comprehensive.
        "uiRadialView",
        "uiFingerPrintHeatChart",
        "uiAssayList",
        "uiGenerateReadAcross",
        "uiFastNN",
        "uiDownload",
        "uiRunReadAcross",
    )
    # Check expected endpoints present.
    prefix = os.environ.get("GENRA_API_PREFIX", "")
    for endpoint in ui_endpoints:
        path = f"{prefix}/api/genra/v4/{endpoint}/"
        # startswith because some are /genra-api/api/genra/v4/uiDownload/{ftype} etc.
        assert any(k.startswith(path) for k in spec["paths"]), path
    # Check correct list of FP options
    allowed_fps = set(FPGen.FPClass) | EXTRA_FP_IDS
    assert set(spec["components"]["schemas"]["FPIDs"]["enum"]) == allowed_fps


def test_openapi_spec(api_url: str) -> None:
    """Test compliance with OpenAPI spec. 3.0."""
    api_url = api_url.replace("/genra-api", "/openapi")
    resp = requests.get(f"{api_url}/openapi.json")  # noqa: S113 no timeout
    check_response_basics(resp)
    spec = resp.json()
    # If no exception is raised by validate(), the spec is valid.
    validate(spec)
