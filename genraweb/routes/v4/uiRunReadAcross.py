"""Prediction data for panel 4, "Run Read-Across"."""
import json
import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint

from genraweb.lib import multitarget
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.api_spec.load_api_spec import api_spec_path
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.misc import check_params, echo_flags
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import uiRunReadAcross, uiRunReadAcrossResponse
from genraweb.routes.api_tags import uiv4_tag

uiRunReadAcross_bp = APIBlueprint("uiRunReadAcross_bp_v4", __name__)


@uiRunReadAcross_bp.post(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiRunReadAcross/"),
    responses={200: uiRunReadAcrossResponse},
    summary=uiRunReadAcross.__doc__,
    tags=[uiv4_tag],
)
def uiRunReadAcross(body: uiRunReadAcross):
    """Run GenRA performance analysis and prediction."""
    data = body.model_dump()
    target_chem_id = multitarget.clean_id(body.chem_id)
    fp_id = fp_hybrid_name_from_lists(data)

    # get appropriate Aggregator
    agg = Aggregator.aggregator_for(body.summarise, body.sumrs_by)(
        GenRAState(
            data,
            chem_id=target_chem_id,
            s0=body.s0,
            k0=body.k0,
            fp_id=fp_id,
            sel_by=body.sel_by,
            sumrs_by=body.sumrs_by,
            neg_min=body.neg0,
            pos_min=body.pos0,
            useWidth=body.useWidth,
            flags=body.flags,
        ),
    )
    agg.do_prediction()
    response = jsonify(echo_flags(request, agg.ag_grid_rra()))
    response.headers.set("Cache-Control", "no-cache")
    return response
