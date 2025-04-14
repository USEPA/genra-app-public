"""Initial, pre-prediction, data for panel 4, "Generate Read-Across"."""
import urllib

from flask_openapi3 import APIBlueprint

from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import DataMatrix, DomainResponse
from genraweb.routes.api_tags import domain_tag

from .domain_utils import frame_response

domain_data_matrix_bp = APIBlueprint("domain_data_matrix_bp", __name__)


@domain_data_matrix_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "dataMatrix/"),
    responses={200: DomainResponse},
    summary=DataMatrix.__doc__,
    tags=[domain_tag],
)
def data_matrix(query: DataMatrix):
    """Get tox information for chemical nearest neighbours for RA
    """
    data = query.model_dump()
    fp_id = fp_hybrid_name_from_lists(data)
    target_chem_id, _ = ChemID.promote_id(query.chem_id)

    data = Aggregator.aggregator_for(query.summarise, query.sumrs_by)(
        GenRAState(
            data,
            chem_id=target_chem_id,
            s0=query.s0,
            k0=query.k0,
            fp_id=fp_id,
            sel_by=query.sel_by,
            summarise=query.summarise,
            sumrs_by=query.sumrs_by,
        ),
    )

    return frame_response(data)
