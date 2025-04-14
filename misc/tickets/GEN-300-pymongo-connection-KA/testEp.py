'''Here as part of work for GEN-300, just in case.
Just a simple test endpoint that returns id(DB).
This file would need to be moved to `genra/routes`, and
its blueprint imported & registered in `genra/genra_flask.py`'''

import time

from flask import Blueprint, jsonify

from genraweb.resources import DB

testEp_bp = Blueprint("testEp_bp", __name__)


@testEp_bp.route(
    "/testEp/", methods=["GET"]
)
def testEp():
    data = {'dbid': id(DB)}
    time.sleep(10)
    return jsonify(data)
