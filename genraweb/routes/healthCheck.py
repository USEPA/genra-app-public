"""Container health check used for Docker HEALTHCHECK etc."""
import time
import urllib

import redis
from flask import jsonify, make_response
from flask_openapi3 import APIBlueprint

from genraweb.resources import DB, MISC_URL_PREFIX
from genraweb.routes.api_models import HealthCheckResponse
from genraweb.routes.api_tags import data_admin_tag

healthCheck_bp = APIBlueprint("healthCheck_bp", __name__)


def add_check_obj(healthcheck_response, check_type, check_and_get_info_obj_function):
    """Calls check_and_get_info_obj_function() to make the check for a given check_type,
    and puts its returned info_object into a dictionary that contains healthcheck
    status.  If failure, it adds a "error" key with string literal of exception raised.
    """
    check_obj = {}
    try:
        # check_obj.update(check_and_get_info_obj_function())
        check_and_get_info_obj_function()
        check_obj["status"] = f"{check_type} healthcheck PASSED"
    except Exception:
        # check_obj["error"] = str(e)
        check_obj["status"] = f"{check_type} healthcheck FAILED"
        healthcheck_response["status"] = "UNHEALTHY"

    healthcheck_response.update({check_type: check_obj})


@healthCheck_bp.get(
    urllib.parse.urljoin(MISC_URL_PREFIX, "healthCheck/"),
    summary="A healthcheck endpoint. Currently checks the DB and cache connections.",
    tags=[data_admin_tag],
    responses={200:HealthCheckResponse}
)
def healthCheck():
    """A healthcheck endpoint. Currently checks the DB and cache connections.
    ---
    tags:
      - Container_Data_Admin
    responses:
      200:
        description: health check successfully run and healthy
      500:
        description: unhealthy, something failed, see body for details
    """
    # more check types can be added as needed

    healthcheck_response = {
        "status": "HEALTHY",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S-UTC"),
    }

    def get_mongo_collections():
        # calls server_info(), then returns list of collections
        DB.client.server_info()
        return {"mongodb_collections": DB.list_collection_names()}

    add_check_obj(healthcheck_response, "DB", get_mongo_collections)

    def get_redis_keys():
        # gets list of redis keys
        r = redis.StrictRedis(host="redis")
        redis_keys = [key.decode("utf-8") for key in r.keys()]
        return {"redis_keys": redis_keys}

    add_check_obj(healthcheck_response, "CACHE", get_redis_keys)

    response = jsonify(healthcheck_response)
    code = 200 if healthcheck_response["status"] == "HEALTHY" else 500
    return make_response(response, code)
