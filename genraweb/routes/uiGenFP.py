import urllib

from flask import jsonify
from flask_openapi3 import APIBlueprint

from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.genfputils import GenerateFPs
from genraweb.lib.fp.nn_calc import CountNNs
from genraweb.resources import DB, FP_URL_PREFIX
from genraweb.routes.api_models import GenFP
from genraweb.routes.api_tags import data_admin_tag

genFP_bp = APIBlueprint("genFP_bp", __name__)

getNextCompoundit = 0


@genFP_bp.get(urllib.parse.urljoin(FP_URL_PREFIX, "genFP/"),
    summary=GenFP.__doc__,
    tags=[data_admin_tag],
    responses={200: {}}
    )
def gen_FP(query: GenFP):
    """Generate all FP fingerprints for candidate chemicals."""
    # chm_mrgn/chm_httr -> chm_mrgn, mrgn class handles FP gen. for httr as well
    fp_id = query.fp.split("/")[0]

    try:
        FPGen.FPClass[fp_id]  # (possibly) generate KeyError used by test
        if query.fp_or_nn == "nn":
            batcher = CountNNs(DB, query.chem_ids, fp_id, query.sel_by)
        else:
            batcher = GenerateFPs(DB, query.chem_ids, fp_id, query.collection_name)
        batcher.queue_batches()
    except KeyError:
        return jsonify(
            {
                "error": "Unsupported fingerprint",
                "message": "Please check the request arguments",
            }
        )

    return jsonify({})
