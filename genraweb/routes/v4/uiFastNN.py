"""Endpoint to retrieve pre-calculated NN data.

NOTE: chem_id must be a SID / CID, an assumption for pre-calc.
"""

import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.nn_explore.nn_explore import nn_graph
from genraweb.lib.misc import echo_flags
from genraweb.lib.state import GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import FastNN, FastNNResponse
from genraweb.routes.api_tags import uiv4_tag

uiFastNN_bp = APIBlueprint("uiFastNN_bp", __name__)


@uiFastNN_bp.get(urllib.parse.urljoin(V4_URL_PREFIX, "uiFastNN/"),
    responses={200: FastNNResponse},
    summary=FastNN.__doc__,
    tags=[uiv4_tag],)
def uiFastNN(query: FastNN):
    """Nearest neighbors from fp_info if present.

    NOTE: chem_id must be a SID / CID, an assumption for pre-calc.

    Returns
    -------
    { "edges": [
        {
            "from": "DTXCID0012502",
            "similarity": 0.398,
            "step": 2,  # steps away from target `chem_id`
            "to": "DTXCID7014868",
            "type": "tox_txrf"  # link type (FP id etc.)
        }, ...
    ], "nodes": [
        "DTXCID0012502": {
            "dsstox_cid": "DTXCID0012502",
            "dsstox_sid": "DTXSID2032502",
            "expanded": true,  # all neighbors (up to k0) listed in response
            "mol_weight": 492.43,
            "name": "Triflusulfuron-methyl"
        }, ...
    ] }
    """
    state = GenRAState(query.model_dump(), steps=3, graph_type="out_only")
    state.steps = int(state.steps)
    state.chem_id, _ = ChemID.promote_id(state.chem_id)
    # filter for FP types allowed by deployment type
    state.fp_ids = FPGen.allowed_fps(state.fp.split(","))

    return jsonify(echo_flags(request, nn_graph(state)))
