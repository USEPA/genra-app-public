"""Endpoint to support radial view."""

import os
import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint
from pydantic import ValidationError

from genraweb.defs import FILTER
from genraweb.lib import multitarget
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO, fp_hybrid_name_from_lists, is_hybrid_fp
from genraweb.lib.misc import echo_flags, nan_to_none
from genraweb.lib.mongofp_NN import searchFP
from genraweb.resources import DB, V4_URL_PREFIX
from genraweb.routes.api_models import RadialView, RadialViewResponse
from genraweb.routes.api_tags import uiv4_tag

uiRadialView_bp = APIBlueprint("uiRadialView_bp", __name__, doc_ui=True)


def _update_structure(neighbors):
    """Bang on the result to make it match historical version."""
    columns = [
        "chem_id",
        "dtxcid",
        "dtxsid",
        "name",
        "selected",
        "similarity_tag",
        "value",
        "weight",
    ]
    renames = {
        "dsstox_cid": "dtxcid",
        "jaccard": "value",
        "similarity": "value",
        "dsstox_sid": "dtxsid",
        "mol_weight": "weight",
    }
    for chem in neighbors:
        chem["selected"] = True
        for key in list(chem):
            if key in renames:
                chem[renames[key]] = chem.get(key)
            if key not in columns:
                del chem[key]
        # unsure about this, added 2021-9-23
        for key in "weight", "dtxsid":
            if key not in chem:
                chem[key] = None
        if not chem.get("chem_id"):
            chem["chem_id"] = ChemID.chem_id(chem)
    return neighbors


def filter_check(
    chem_id: str,  # chemical ID
    fp_id: str,  # FP class ID
    sel_by: str,  # filter ID
    s0: float = None,  # similarity threshold
) -> str:  # possibly updated filter ID
    """Check neighbors exist with filter `sel_by`, switch filters if needed.

    Trys to be conservative, only switches if > 0 neighbors known to exist.
    """
    key = FPGen.fp_info_key(fp_id=fp_id, sel_by=sel_by) + ".n"
    # Rely on index as chem_id will be promoted from uiSetup endpoint
    query = ChemID.chem_id_search([chem_id], index=True)
    if query is None:
        # custom SMILE, this data won't exist to begin with
        return None
    query[key] = {"$exists": True}
    info = DB[FP_INFO].find_one(query)
    if not info or ( # if sel_by is a non-fp filter, info will be None
        info[fp_id][sel_by]["n"] > 0
        and (s0 is None or info[fp_id][sel_by].get("max_s0", 1) >= s0)
    ):
        return sel_by  # at least some neighbors with that filter, or non-fp filter

    alt_filter = "no_filter"
    del query[key]  # remove the *old* one before adding new
    key = f"{fp_id}.{alt_filter}.n"
    query[key] = {"$exists": True}
    info = DB[FP_INFO].find_one(query)
    if not info or info[fp_id][alt_filter]["n"] == 0:
        return sel_by  # no reason to switch
    return alt_filter


@uiRadialView_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiRadialView/"),
    responses={200: RadialViewResponse},
    summary=RadialView.__doc__,
    tags=[uiv4_tag],
)
def uiRadialView(query: RadialView):
    """Nearest neighbor list with similarities, for radial plot."""
    fp = fp_hybrid_name_from_lists(query.model_dump())
    k0 = query.k0 + 1

    chem_id, _ = ChemID.promote_id(query.chem_id)

    user_msg = None
    # No sense in filtering something the user selected.
    if fp in ("multitarget", "user-defined"):
        sel_by = fp
    else:
        sel_by = query.sel_by
        new_sel_by = filter_check(chem_id, fp, sel_by, s0=query.s0)
        if new_sel_by is not None and new_sel_by != sel_by:
            user_msg = {
                "type": "warning",
                "text": f"NOTE: '{chem_id}' has no sufficiently similar "
                f"{fp} neighbors with the "
                f"'{FILTER[sel_by]['description']}' ({FILTER[sel_by]['name']}) "
                f"filter, so the filter was changed to the "
                f"'{FILTER[new_sel_by]['description']}' ({FILTER[new_sel_by]['name']}) "
                "filter.",
            }
            sel_by = new_sel_by

    neighbors = searchFP(chem_id, fp=fp, sel_by=sel_by, s0=query.s0, max_hits=k0)

    if not neighbors:
        return jsonify(dict())

    # bang on the result to make it match historical version
    _update_structure(neighbors)

    # This route def'n might not be the best place, but that applies to
    # other logic here too.
    if is_hybrid_fp(fp):
        similarity_tag = "x"
    elif multitarget.is_multi(chem_id):
        similarity_tag = "m"
    else:
        similarity_tag = FPGen.FPClass[fp].similarity_tag
    details_link = os.environ.get("GENRA_DETAILS_LINK") or ""

    for chem in neighbors:
        chem["similarity_tag"] = similarity_tag
        chem_id = chem.get("dtxsid") or chem.get("dtxcid")
        if details_link.strip() and ChemID.id_type(chem_id) in (ChemID.SID, ChemID.CID):
            chem["details_link"] = details_link.format(chem_id=chem_id)
            # Update template.env if more keywords beyond chem_id are
            # added.  Also keep in sync. with ./uiFingerPrintHeatChart.py

    neighbors = {"result": neighbors}
    neighbors["sel_by"] = sel_by
    if user_msg:
        neighbors["userMsg"] = user_msg

    nan_to_none(neighbors)
    neighbors["report_db"] = [
        {
            "data_exists": True,
            "key": db_key,
            "description": db.description,
            "name": db.name,
            "subFields": [
                {
                    "data_exists": True,
                    "key": fld_key,
                    "description": fld["description"],
                    "name": fld["name"],
                }
                for fld_key, fld in db.groupings.items()
            ],
        }
        for db_key, db in Aggregator.aggregator.items()
    ]
    report_db = neighbors["report_db"]

    # Different Aggregator classes may report the same name, merge those, see
    # aggregator.py for explanation of Aggregator lookup.
    report_db.sort(key=lambda x: x["name"])
    nghbr_i = 0
    while nghbr_i < len(report_db) - 1:
        if report_db[nghbr_i]["name"] == report_db[nghbr_i + 1]["name"]:
            report_db[nghbr_i]["subFields"].extend(report_db[nghbr_i + 1]["subFields"])
            del report_db[nghbr_i + 1]
        else:
            nghbr_i += 1

    # make the default (first) aggregator listed in panel 3 match the filter
    # False < True sort
    report_db.sort(
        key=lambda x: (x.get("key") != FILTER[sel_by]["aggregator"], x["name"])
    )
    response = echo_flags(request, neighbors)
    try:
        return jsonify(RadialViewResponse.model_validate(response).dict())
    except ValidationError:
        print("ERROR SERIALIZING:", response)
        raise
