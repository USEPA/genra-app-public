"""Data availability endpoint.

NOTE: at domain level, no different to data_matrix endpoint.
"""
import os
import urllib

from flask import request
from flask_openapi3 import APIBlueprint

from genraweb.deploy_types import DeployType
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.misc import check_params
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import DataAvailability, DomainResponse
from genraweb.routes.api_tags import domain_tag

from .domain_utils import frame_response

deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]
domain_data_avail_bp = APIBlueprint("domain_data_avail_bp", __name__)


@domain_data_avail_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "dataAvailability/"),
    responses={200: DomainResponse},
    summary=DataAvailability.__doc__,
    tags=[domain_tag],
)
def data_availability(query: DataAvailability):
    """Summarize data availability for a given chemical."""
    target_chem_id = query.chem_id or query.dsstox_cid
    target_chem_id, _ = ChemID.promote_id(target_chem_id)

    data = Aggregator.aggregator_for(query.summarise, query.sumrs_by)(
        GenRAState(
            chem_id=target_chem_id,
            s0=query.s0,
            k0=query.k0,
            fp_id=fp_hybrid_name_from_lists(query.model_dump()),
            sel_by=query.sel_by,
            sumrs_by=query.sumrs_by,
        ),
    )

    return frame_response(data)
