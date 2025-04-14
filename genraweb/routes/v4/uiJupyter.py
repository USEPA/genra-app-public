import subprocess
import urllib

from flask import current_app, json
from flask_openapi3 import APIBlueprint

from genraweb.resources import V4_URL_PREFIX

uiJupyter_bp = APIBlueprint("uiJupyter_bp", __name__)


@uiJupyter_bp.route(urllib.parse.urljoin(V4_URL_PREFIX, "uiJupyter/"), methods=["GET"])
def uiJupyter():
    """Jupyter connection info.
    ---
    tags:
      - UI_support_v4
    responses:
      200:
        description: List of urls / tokens.
    """
    # Response is on stderr and starts with [SomeKey] {...
    servers = subprocess.run(
        ["jupyter", "server", "list", "--jsonlist"], capture_output=True
    ).stderr
    servers = json.loads(servers.split(b" ", 1)[1])

    directions = [
        " To reach the Jupyter Lab environment, go to the port listed in            ",
        " docker-compose-local.yml in the ports: section for local port 8888.       ",
        " For example, if docker-compose-local.yml lists `- 30008:8888` and you     ",
        " are viewing this page at http://example.com:30000/api/genra/v4/uiJupyter, ",
        " visit http://example.com:30008/lab?token=xxxxxxxxxxxxxxxxx                ",
    ]
    response = dict(directions=directions, servers=servers)
    if not servers:
        response["directions"] = ["No Jupyter servers found"]
    else:
        response["directions"] += [
            " " * len(directions[0]),
            " Use one of the following tokens to log in to "
            "the server:                  ",
            " " * len(directions[0]),
        ]
        response["directions"] += [
            f" {i['token']}                           " for i in servers
        ]
    # like jsonify, but with indent
    return current_app.response_class(
        json.dumps(response, indent=4), mimetype="application/json"
    )
