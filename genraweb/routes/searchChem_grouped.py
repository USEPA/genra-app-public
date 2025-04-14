import re
import time
import urllib
from difflib import SequenceMatcher
from os.path import commonprefix

from flask import jsonify, request
from flask_openapi3 import APIBlueprint
from pydantic import ValidationError

from genraweb.lib.chem_id import ChemID
from genraweb.lib.logging import logger
from genraweb.resources import DB, NCD_URL_PREFIX, redis_cache
from genraweb.routes.api_models import SearchChems, SearchChemsResponse
from genraweb.routes.api_tags import uiv3_tag, uiv4_tag

searchChem_grouped_bp = APIBlueprint("searchChem_grouped_bp", __name__)

MAX_HITS = 100


def sort_str_cmp(value, target, tlen):
    """Return three level sort keys, (A, B, C)

    A - major level, 0, 1, 2, 3
    B - finer level, usually length of target unmatched (lower is better)
    C - the search string, so tied results are sorted

    Args:
    ----
        value (str): value for this hit
        target (str): target, guaranteed (a) a str and (b) lower case
        tlen (int): length of target

    Returns:
    -------
        tuple: see above
    """
    value = str(value).lower()
    if value == target:
        return (0, 0, value)  # best match
    if target[:2] == value[:2]:  # for speed
        common = commonprefix([target, value])
        if common:
            return (1, tlen - len(common), value)  # starts with match of length B
    if target in value:  # for speed
        # https://stackoverflow.com/a/39404777/1072212
        match = SequenceMatcher(None, target, value).find_longest_match(
            0, tlen, 0, len(value)
        )
        return (2, tlen - match.size, value)  # max substring match of length B

    return (3, 0, value)  # no match (chem. matched on a different synonym or name)


def sort_key_factory(target):
    """Return a sort key function that prioritizes more exact matches of the target
    string.
    """

    def sort_key(hit, target=str(target).lower(), tlen=len(target)):
        # sort key based on name
        best = sort_str_cmp(hit.get("name", "zzz"), target, tlen)
        # or synonyms
        for value in hit.get("synonyms", []):
            score = sort_str_cmp(value, target, tlen)
            if score < best:
                best = score
        return best

    return sort_key


@redis_cache
def search_chems(txt):
    """Assumes len(txt)>=3 as filtered in endpoint defined below"""
    id_type = ChemID.id_type(txt)
    if id_type == ChemID.NAME:
        query = {
            "synonyms": {"$elemMatch": {"$regex": re.escape(txt), "$options": "i"}},
        }
        # Could be a SMILES that is in the DB that RDKit didn't parse
        for field in ChemID.id_field[ChemID.SMILES]:
            query[field] = txt
        query = {"$or": [{k: v} for k, v in query.items()]}
    else:
        query = ChemID.chem_id_search(txt)

    Q = {"$or": [query]}
    ret = dict(_id=0, name=1, casrn=1, dsstox_cid=1, dsstox_sid=1, synonyms=1, smiles=1)
    start = time.time()
    if id_type == ChemID.NAME:
        # Query by name first, as this seems not to be in the first 10,000 sometimes,
        # i.e. ordering in the `queries` list above doesn't ensure name is searched
        # ahead of synonyms.
        #
        # Also note that case *in*sensitive searches cannot use indexes:
        # https://docs.mongodb.com/manual/reference/operator/query/regex/#index-use
        R = list(
            DB.compounds.find(
                {"name": {"$regex": "^" + re.escape(txt), "$options": "i"}}, ret
            ).limit(5000)
        )
    else:
        R = []
    R.extend(DB.compounds.find(Q, ret).limit(10000))
    logger.info("Query %s (%s search) in %.3f", txt, id_type, time.time() - start)
    if not R:
        return dict(
            hits=[ChemID.chem_from_smiles(txt)] if id_type == ChemID.SMILES else []
        )

    start = time.time()
    R.sort(key=sort_key_factory(txt))
    logger.info("Sort %s in %.3f", txt, time.time() - start)
    R = R[:MAX_HITS]
    seen = set()
    hits = []
    # Some chemicals have their name in their synonyms list, so uniquify here to avoid
    # returning the same hit twice.
    for hit in R:
        if "synonyms" in hit:
            del hit["synonyms"]
        hashable = tuple(hit.items())
        if hashable not in seen:
            hits.append(hit)
            hit["chem_id"] = ChemID.chem_id(hit)
            seen.add(hashable)

    # Prioritize hits with a dsstox_sid
    hits.sort(key=lambda hit: bool(hit.get("dsstox_sid")), reverse=True)

    return dict(hits=hits)


@searchChem_grouped_bp.get(
    urllib.parse.urljoin(NCD_URL_PREFIX, "searchChems/"),
    responses={200: SearchChemsResponse},
    tags=[uiv3_tag, uiv4_tag]
)
def searchChems(query: SearchChems, txt=None):
    """Search chemicals
    Specify one of: name, casrn, smiles, cid, sid
    ---
    tags:
      - UI_support_v4
      - UI_support_v3
    parameters:
      - $ref: "#/components/parameters/search_text"
    responses:
      200:
        description: A list of chemical hits
    """
    txt = str(request.args.get("txt")).strip() if txt is None else txt
    if len(txt) < 3:
        return jsonify(dict(hits=[]))
    search_result = search_chems(txt)
    try:
        return jsonify(SearchChemsResponse.model_validate(search_result).dict())
    except ValidationError:
        print("ERROR SERIALIZING:", search_result)
        raise
