"""Endpoint for NN download."""
import urllib

from flask import Response, request
from flask_openapi3 import APIBlueprint

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.misc import check_params
from genraweb.lib.mongofp_NN import searchFP
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import ChemNN, DomainResponse
from genraweb.routes.api_tags import domain_tag

from .domain_utils import frame_response

domain_chem_nn_bp = APIBlueprint("domain_chem_nn_bp", __name__)


@domain_chem_nn_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "chemNN/"),
    responses={200: DomainResponse},
    summary=ChemNN.__doc__,
    tags=[domain_tag],
)
def data_matrix(query: ChemNN) -> Response:
    """Get top ~100 FPs."""
    target_chem_id, _ = ChemID.promote_id(query.chem_id)
    fp = fp_hybrid_name_from_lists(query.model_dump())
    ans = searchFP(
        target_chem_id,
        fp,
        sel_by=query.sel_by,
        s0=-1,
        max_hits=query.k0 or 100,
    )
    return frame_response(ans, extract=False)
