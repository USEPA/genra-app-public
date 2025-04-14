"""Main Flask app entry point, collect all endpoints and configure Flask app."""
import json
import os
import subprocess
import sys
from pathlib import Path

# before rest of imports for coverage
from genraweb.coverage import cov

code_coverage = os.environ.get("GENRA_CODE_COVERAGE")
if code_coverage in ["y", "Y", "Yes", "YES"]:
    print(
        "starting code coverage based on GENRA_CODE_COVERAGE env variable", flush=True
    )
    cov.start()

import numpy as np
from flask import jsonify, make_response, request
from flask.json.provider import JSONProvider
from flask_cors import CORS
from flask_openapi3 import APIBlueprint, Info, OpenAPI

if os.environ.get("GENRA_SENTRY_USE"):
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=os.environ.get("GENRA_SENTRY_URL"),
        integrations=[FlaskIntegration()],
    )

from genraweb.commands import commands_bp
from genraweb.deploy_types import DeployType
from genraweb.lib.logging import logger
from genraweb.routes.appBuildInfo import appBuildInfo_bp
from genraweb.routes.domain.chem_nn import domain_chem_nn_bp
from genraweb.routes.domain.data_matrix import domain_data_matrix_bp
from genraweb.routes.domain.read_across import domain_read_across_bp
from genraweb.routes.healthCheck import healthCheck_bp
from genraweb.routes.manage_coverage import manage_coverage_bp
from genraweb.routes.searchChem_grouped import searchChem_grouped_bp
from genraweb.routes.uiClearCache import uiClearCache_bp
from genraweb.routes.uiGenFP import genFP_bp
from genraweb.routes.v4.uiAssayList import uiAssayList_bp
from genraweb.routes.v4.uiDownload import uiDownload_bp
from genraweb.routes.v4.uiFastNN import uiFastNN_bp
from genraweb.routes.v4.uiFingerPrintHeatChart import uiFingerPrintHeatChart_bp
from genraweb.routes.v4.uiGenerateReadAcross import uiGenerateReadAcross_bp
from genraweb.routes.v4.uiJupyter import uiJupyter_bp
from genraweb.routes.v4.uiPhyschemPlot import uiPhyschemPlot_bp
from genraweb.routes.v4.uiRadialView import uiRadialView_bp
from genraweb.routes.v4.uiRunReadAcross import uiRunReadAcross_bp
from genraweb.routes.v4.uiSetup import uiSetup_bp
from genraweb.routes.viewChem import viewChem_bp

DIR = os.getcwd()
sys.path.append(DIR)

info = Info(title="GenRA API", version="1.0.0")
app = OpenAPI(__name__, info=info, security_schemes={})

GENRA_FLASK_LOG_FMT = os.environ.get(
    "GENRA_FLASK_LOG_FMT", "{request.method}: {request.url}"
)


@app.before_request
def log_request_info():
    """Log HTTP requests"""
    if "healthCheck" in request.url:
        return
    logger.info(GENRA_FLASK_LOG_FMT.format(request=request))


CORS(app)
# avoid redirect for trailing slash on OPTIONS HTTP request for CORS preflight
app.url_map.strict_slashes = False


class NpEncoder(json.JSONEncoder):
    """TypeError: Object of type int64 is not JSON serializable
    https://stackoverflow.com/a/57915246/1072212
    """

    def default(self, obj):
        """Encode numpy types in JSON"""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return super().encode(bool(obj))

        return super().default(obj)


class CustomJSONProvider(JSONProvider):
    """Custom JSON provider to handle numpy types."""

    def dumps(self, obj, **kwargs):
        """Dump numpy types."""
        kwargs |= {"cls": NpEncoder}
        return json.dumps(obj, **kwargs)

    def loads(self, obj, **kwargs):
        """Use default library for loads."""
        return json.loads(obj, **kwargs)


app.json = CustomJSONProvider(app)


# registered to app so that command can be run directly, instead of through
# the context of `app_bp`
app.register_api(commands_bp)


@app.errorhandler(404)
def notFound(error):
    """Return 404 error."""
    response = jsonify({"error": "Notfound"})
    return make_response(response, 404)


app_bp = APIBlueprint("app_bp", __name__)

deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]

app_bp.register_api(healthCheck_bp)
app_bp.register_api(searchChem_grouped_bp)
app_bp.register_api(viewChem_bp)

if deployment_type <= DeployType.STG or os.environ.get("GENRA_FORCE_SWAGGER"):
    # enable Swagger interface on /apidocs/
    if deployment_type == DeployType.LOCAL_DEV and not os.environ.get(
        "GENRA_FORCE_SWAGGER"
    ):
        # don't show http with GENRA_FORCE_SWAGGER as that implies exporting spec.
        schemes = ["http", "https"]
    else:
        schemes = ["https"]
    host = os.environ.get("GENRA_SWAGGER_HOST", "")
    # app.config["SWAGGER"] = {
    #     "ui_params": {"tagsSorter": "alpha", "docExpansion": "none"},
    #     "openapi": "3.0.3",
    # }
    # Swagger(
    #     app,
    #     template={
    #         "info": {
    #             "title": "GenRA API",
    #             "version": "0.4",
    #         },
    #         "servers": [{"url": f"{scheme}://{host}"} for scheme in schemes],
    #         "components": api_spec_components(),
    #     },
    # )

app_bp.register_api(domain_chem_nn_bp)
app_bp.register_api(domain_data_matrix_bp)
app_bp.register_api(domain_read_across_bp)
app_bp.register_api(uiRadialView_bp)
app_bp.register_api(uiFastNN_bp)
app_bp.register_api(uiAssayList_bp)
app_bp.register_api(uiFingerPrintHeatChart_bp)
app_bp.register_api(uiGenerateReadAcross_bp)
app_bp.register_api(uiRunReadAcross_bp)
app_bp.register_api(uiSetup_bp)
app_bp.register_api(uiDownload_bp)
app_bp.register_api(uiPhyschemPlot_bp)


url_prefix = os.environ.get("GENRA_API_PREFIX", "/")


def version_txt_git():
    """Return version.

    tags:
      - Container_Data_Admin

    responses:
      200:
        description: success
    """
    # not used because including .git in a docker image can make it hard to avoid
    # including access tokens for remotes etc.
    version = subprocess.run(
        "/usr/bin/git -C /genra describe --match '[0-9]*' --dirty".split(),  # noqa:S603
        check=True,
        capture_output=True,
        encoding="utf8",
    )
    version = version.stdout.replace("_dev", "").replace("-dirty", "+edits")
    return version


def version_txt_file() -> str:
    """Return version from file
    ---
    tags:
      - Container_Data_Admin

    responses:
      200:
        description: success
    """
    path = Path(__file__).parent.parent / "version.txt"
    return path.read_text().strip()


app.route(f"{url_prefix}/version.txt", methods=["GET"])(version_txt_file)

if deployment_type < DeployType.PROD:
    # routes not to be included in prod
    app_bp.register_api(appBuildInfo_bp)
    app_bp.register_api(uiClearCache_bp)

    if deployment_type == DeployType.LOCAL_DEV:
        app_bp.register_api(uiJupyter_bp)

        # FP generation route
        app_bp.register_api(genFP_bp)

        # coverage data generation
        app_bp.register_api(manage_coverage_bp)

app.register_api(app_bp)
