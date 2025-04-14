"""Initial, pre-prediction, data for panel 4, "Generate Read-Across"."""
import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint

from genraweb.lib import multitarget
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.misc import echo_flags
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import GenerateReadAcross, GenerateReadAcrossResponse
from genraweb.routes.api_tags import uiv4_tag

uiGenerateReadAcross_bp = APIBlueprint("uiGenerateReadAcross_bp_v4", __name__)


@uiGenerateReadAcross_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiGenerateReadAcross/"),
    responses={200: GenerateReadAcrossResponse},
    summary=GenerateReadAcross.__doc__,
    tags=[uiv4_tag],
)
def uiGenerateReadAcross(query: GenerateReadAcross):
    """Get tox information for chemical nearest neighbours for RA."""
    summarise = query.summarise
    sumrs_by = query.sumrs_by
    fp_id = fp_hybrid_name_from_lists(query.model_dump())
    target_chem_id = query.chem_id

    agg = Aggregator.aggregator_for(summarise, sumrs_by)(
        GenRAState(
            query.model_dump(),
            chem_id=target_chem_id,
            s0=query.s0,
            k0=query.k0,
            fp_id=fp_id,
            sel_by=query.sel_by,
            summarise=summarise,
            sumrs_by=sumrs_by,
        ),
    )

    return jsonify(echo_flags(request, agg.ag_grid_gra()))
