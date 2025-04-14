"""Prediction data for panel 4, "Run Read-Across"."""
import urllib

from flask_openapi3 import APIBlueprint

from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import DomainResponse, RunReadAcross
from genraweb.routes.api_tags import domain_tag

from .domain_utils import frame_response

domain_read_across_bp = APIBlueprint("domain_read_across_bp", __name__)


@domain_read_across_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "readAcross/"),
    responses={200: DomainResponse},
    summary=RunReadAcross.__doc__,
    tags=[domain_tag],
)
def read_across(query: RunReadAcross):
    """Run GenRA prediction analysis"""
    data = query.model_dump()
    target_chem_id, _ = ChemID.promote_id(query.chem_id)

    # get appropriate Aggregator
    agg = Aggregator.aggregator_for(query.summarise, query.sumrs_by)(
        GenRAState(
            data,
            chem_id=target_chem_id,
            s0=query.s0,
            k0=query.k0,
            fp_id=fp_hybrid_name_from_lists(data),
            sel_by=query.sel_by,
            sumrs_by=query.sumrs_by,
            neg_min=query.minneg,
            pos_min=query.minpos,
            useWidth=query.useWidth,
        ),
    )
    agg.do_prediction()
    return frame_response(agg)
