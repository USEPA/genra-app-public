import time
import urllib

from flask import jsonify
from flask_openapi3 import APIBlueprint

from genraweb.resources import UI_URL_PREFIX, redis_cache
from genraweb.routes.api_models import ClearCacheResponse

uiClearCache_bp = APIBlueprint("uiClearCache_bp", __name__)


@uiClearCache_bp.get(
    urllib.parse.urljoin(UI_URL_PREFIX, "uiClearCache/"),
    summary="Clear Redis LRU cache.",
    responses={200: ClearCacheResponse}
)
def uiClearCache():
    """Clear Redis LRU cache, based on
    https://github.com/leohowell/redis-lru/blob/master/redis_lru/lru.py
    ---
    tags:
      - Container_Data_Admin
    responses:
      200:
        description: Reports keys clears
    """
    client = redis_cache.client
    key_prefix = redis_cache.key_prefix

    def delete_keys(items):
        pipeline = client.pipeline()
        ans["keys_cleared"] += len(items)
        ans["keys"].extend(i.decode("utf8") for i in items)
        for item in items:
            pipeline.delete(item)
        pipeline.execute()

    match = "{}*".format(key_prefix)
    ans = {"keys_cleared": 0, "match": match, "time": time.asctime(), "keys": []}
    keys = []

    for key in client.scan_iter(match=match, count=100):
        keys.append(key)
        if len(keys) >= 100:
            delete_keys(keys)
            keys = []
            time.sleep(0.01)
    else:
        delete_keys(keys)

    return jsonify(ans)
