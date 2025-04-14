import os
import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint

from genraweb.deploy_types import DeployType
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.api_spec.load_api_spec import api_spec_path
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.misc import echo_flags
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import AssayList, AssayListResponse
from genraweb.routes.api_tags import uiv4_tag

deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]
uiAssayList_bp = APIBlueprint("uiAssayList_bp_v4", __name__)


@uiAssayList_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiAssayList/"),
    responses={200: AssayListResponse},
    summary=AssayList.__doc__,
    tags=[uiv4_tag],
)
def uiAssayList(query: AssayList):
    """Summarize ct,bio,tox information for chemical."""
    # TODO: Is this properly captured by target_chem_id = query.chem_id
    # target_chem_id = request.args.get("chem_id") or request.args.get("dsstox_cid")
    target_chem_id = query.chem_id
    summarise = query.summarise
    sumrs_by = query.sumrs_by

    data = Aggregator.aggregator_for(summarise, sumrs_by)(
        GenRAState(
            chem_id=target_chem_id,
            s0=query.s0,
            k0=query.k0,
            fp_id=fp_hybrid_name_from_lists(query.model_dump()),
            sel_by=query.sel_by,
            sumrs_by=sumrs_by,
        ),
    )

    return jsonify(echo_flags(request, data.ag_grid_al()))
