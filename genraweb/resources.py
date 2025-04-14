"""resources to be shared across routes/helpers for the app"""

import json
import os
from pathlib import Path

import redis

from genraweb.lib.cache import GenRARedisLRU, no_cache
from genraweb.lib.db_connection import open_mongo_db
from genraweb.reloader import Reloader


class DB_Reloader(Reloader):
    def _get_resource(self):
        return open_mongo_db()


# mongo database, Note: default uses GENRA_DB_<FIELD>
DB = DB_Reloader(seconds=600)
TOXREF_SIZE = DB.toxref_tr_fp.estimated_document_count()  # used by mongofp_NN

# url prefix
# note: URL_PREFIX is parameter `base` urllib.parse.urljoin
url_prefix = os.environ.get("GENRA_API_PREFIX", "/")
NCD_URL_PREFIX = url_prefix + "/api/genra/v3/"
UI_URL_PREFIX = NCD_URL_PREFIX
FP_URL_PREFIX = NCD_URL_PREFIX
MISC_URL_PREFIX = NCD_URL_PREFIX
V4_URL_PREFIX = url_prefix + "/api/genra/v4/"

# redis caching
if os.environ.get("GENRA_NO_LRU_CACHE"):
    redis_cache = no_cache
else:
    # note: cache 5,000 results for 50 days
    redis_cache = GenRARedisLRU(
        redis.StrictRedis("redis"), max_size=5000, default_ttl=50 * 24 * 60 * 60
    )

# for panel 4 row labeling (assay endpoint/component)
with (Path(__file__).parent.parent / "misc/toxref_notes.json").open() as f:
    ENDPOINT_DETAILS = {i["ds"]: i for i in json.load(f)}
ENDPOINT_DETAILS_TOXCAST = {
    i["assay_component_name"]: i
    for i in DB["toxcast_assays"].find(
        {"assay_component_name": {"$ne": None}},
        {"assay_component_name": 1, "assay_component_desc": 1},
    )
}

# ui endpoint pop-up messages, paired with "error_msg" key in JSON response
MESSAGE = dict(
    markush="GenRA can only operate on chemicals with fully defined structures. "
    "The chemical you searched appears to be a Markush structure that does not "
    "have a definite structure.",
    sid_only="GenRA can only operate on chemicals with defined structures. "
    "The chemical you searched appears in the database, but without a defined "
    "structure.",
    not_found="The chemical you searched was not found in the database.",
    unknown="The chemical you searched for can not be processed by GenRA.",
    weightless="One or more chemicals in neighborhood don't have molecular "
    "weight associated, so has been removed from calculating predictions.",
)
