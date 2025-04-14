import urllib

from flask import request
from flask_openapi3 import APIBlueprint

from genraweb.coverage import cov

# from genraweb.resources import MISC_URL_PREFIX, cov
from genraweb.resources import MISC_URL_PREFIX
from genraweb.routes.api_models import ManageCoverage

manage_coverage_bp = APIBlueprint("manage_coverage_bp", __name__)


@manage_coverage_bp.get(
    urllib.parse.urljoin(MISC_URL_PREFIX, "manage_coverage/"),
    summary="An endpoint to commit coverage results to disk and HTML.",
    responses={200:{}}
)
def manage_coverage(query: ManageCoverage):
    """An endpoint to commit coverage results to disk and HTML.

    Don't use multi-threading in API container (GUNICORN_CMD_ARGS) while calculating
    coverage.
    ---
    tags:
      - Container_Data_Admin

    Parameters
    ----------
      - $ref: "#/components/parameters/stop"

    responses:
      200:
        description: success
    """

    if query.stop == "stop":
        cov.stop()

    return {}
