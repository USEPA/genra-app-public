"""Sends UI a lot of details, drop down options, etc."""
import urllib
from pathlib import Path

import yaml
from flask import jsonify, request
from flask_openapi3 import APIBlueprint
from pydantic import ValidationError

from genraweb.defs import COLORS, FILTER
from genraweb.lib import multitarget
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.nn_lookup import fp_n_for_chems
from genraweb.lib.logging import logger
from genraweb.lib.misc import echo_flags
from genraweb.lib.state import GenRAFlag, GenRAState
from genraweb.resources import MESSAGE, V4_URL_PREFIX
from genraweb.routes.api_models import Setup, SetupResponse
from genraweb.routes.api_tags import uiv4_tag

# order in which COLORS are assigned to FPS
FP_COLOR_ORDER = [  # this should be kept constant for consistency
    "chm_mrgn",
    "bio_txct",
    "tox_txrf",
    "chm_ct",
    "chm_httr",
    "SKIP",  # FIXME reserved for "tox_txvl", expected in future
    "bio_htpp_MCF7",
    "bio_htpp_U2OS",
    "bio_txct_ATG",
    "bio_txct_BSK",
    "bio_txct_NVS",
    "chm_aim",
    "bio_pest",
    "SKIP",  # color is too light
    "chm_phch",
    "chm_pfas",
]

# order of priority of FPs for showing on neighborhood graph explorer (default is top 3)
# Per conversation with PO it seems identical to FP_COLOR_ORDER, for now
FP_GRAPH_PRIORITY_ORDER = FP_COLOR_ORDER.copy()

# neighborhood exploration graph types
GRAPH_TYPE = {
    # Per discussion with PO, single-incoming makes it visually simpler but harder
    # to interpret, so don't use.
    # "out_only": {
    #     "description": "Only one incoming edge per FP type per chemical.",
    #     "name": "single-incoming",
    # },
    "all_nhgbrs": {
        "description": "Include all paths to each chemical for each FP type.",
        "name": "all-paths",
    },
}


uiSetup_bp = APIBlueprint("uiSetup_bp", __name__)


def expand_dropdown(data):
    """Expand a dropdown data structure for UI consumption."""
    return [
        {
            "data_exists": True,
            "description": v["description"],
            "key": k,
            "name": v["name"],
        }
        for k, v in data.items()
        if not v.get("skip")
    ]


@uiSetup_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiSetup/"),
    summary=Setup.__doc__,
    tags=[uiv4_tag],
    responses={200: SetupResponse},
)
def uiSetup(query: Setup):
    """Information to populate drop-downs etc."""
    help_text = yaml.safe_load(Path(__file__).with_name("help_texts.yaml").open())
    help_path = (
        Path(__file__).parent.parent.parent.parent / "docs/explorer/explorer.html"
    )
    help_id = "GENRA Neighborhood Explorer"
    help_text[help_id] = {
        "helpPosition": "right",
        "iconType": "Information",
        "helpTextId": help_id,
        "helpText": help_path.read_text(),
    }
    state = GenRAState(request.args)  # Mostly for flags

    chem_id_in = request.args.get("chem_id")
    chem_id = multitarget.clean_id(chem_id_in)
    if multitarget.is_multi(chem_id):
        response = {}
    else:
        chem_id, chem = ChemID.promote_id(chem_id_in)
        chem_id_type = ChemID.id_type(chem_id)
        response = chem or {}

    response.update(
        dict(
            chem_id=chem_id,
            neighbor_by=[],
            hybrid_fp_max=3,  # max. neigbors to allow user to blend
            fp_needs_gen=[],  # FP IDs for FPs that will require calculation.
            help_text=list(help_text.values()),
            # not sure we can make data_exists meaningful for filter_by?
            filter_by=expand_dropdown(FILTER),
            graph_type=expand_dropdown(GRAPH_TYPE),
            fpColor=dict(i for i in zip(FP_COLOR_ORDER, COLORS) if i[0] != "SKIP"),
            # NOTE: there is another setting added, initGraphFP, below
        )
    )
    if multitarget.is_multi(chem_id):
        _, chem = ChemID.promote_id(multitarget.chem_ids(chem_id)[0])
        response = chem | response
        response["initGraphFPs"] = ["chm_mrgn", "bio_txct"]
        response["hybrid_fp_max"] = 0
        response["neighbor_by"] = [
            {
                "data_exists": True,
                "description": "User defined neighborhood",
                "name": "user-defined",
                "key": "user-defined",
            }
            if GenRAFlag.USERNN in state.flags
            else {
                "data_exists": True,
                "description": "Multi-target",
                "name": "multitarget",
                "key": "multitarget",
            }
        ]
        response["filter_by"] = [FILTER[response["neighbor_by"][0]["key"]]]
    else:
        complete_setup(response, chem_id_in, chem_id, chem_id_type, chem)

    # download options:
    response["download"] = [
        {
            "subdir": None,
            "name": "File Type",
            "description": "Select file type to download",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/csv",
            "name": "CSV - read across panel",
            "description": "CSV download of the read across panel",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/xlsx",
            "name": "Excel - read across panel",
            "description": "Excel download of the read across panel",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/RAview",
            "name": "Radial plot image",
            "description": "Radial plot image",
            "data_exists": True,
            "rel": "/step/radial/download",
        },
    ]

    if not multitarget.is_multi(chem_id):
        response["download"].append(
            {
                "subdir": "/allNN",
                "name": "Top ~100 nearest neighbors",
                "description": "CSV, Excel compatible, includes fingerprints",
                "data_exists": True,
                "rel": "/step/radial/download",
            }
        )

    if state.flags & GenRAFlag.MULTITARGET:
        # Nullify fields that apply to the first chem. only
        for key in "dsstox_cid", "dsstox_sid", "casrn", "smiles", "mol_weight":
            if key in response:
                response[key] = None
        response["name"] = "Multitarget"

    echo_flags(request, response)
    try:
        return jsonify(SetupResponse.model_validate(response).dict())
    except ValidationError:
        response.pop("help_text", None)  # Swamps the error message.
        print("ERROR SERIALIZING:", response)
        raise


def complete_setup(response, chem_id_in, chem_id, chem_id_type, chem):
    """Finish setup - moved out of uiSetup() as not needed if is_multi()."""
    # Valid FPs for chem_id
    fps_for_chem = fp_n_for_chems(chem_ids=[chem_id], min_s0=0.1)
    # NOTE: relying on Registerable to omit FPs not available at deployment level
    for fp_class in FPGen.FPClass.values():  # implementation ensures preferred order
        data_exists = fps_for_chem[chem_id].get(fp_class.fp_id, 0) > 0
        if not data_exists and fp_class.on_the_fly and chem_id_type == ChemID.SMILES:
            data_exists = True
            response["fp_needs_gen"].append(fp_class.fp_id)
        response["neighbor_by"].append(
            dict(
                key=fp_class.fp_id,
                name=fp_class.name,
                description=fp_class.description,
                data_exists=data_exists,
            )
        )
    MinFPs = 2  # minimum number of FPs needed for hybrid FP
    response["neighbor_by"].extend(
        [
            {
                "key": "hybrid",
                "name": "Custom hybrid (can be slow)",
                "description": "User specified hybrid FP weightings",
                # There must be at least two FPs with existing data for custom hybrid.
                "data_exists": len(
                    [
                        fp_option
                        for fp_option in response["neighbor_by"]
                        if fp_option["data_exists"]
                    ]
                )
                >= MinFPs,
            }
        ]
    )

    # control which 3 (or fewer, depending on availability) FPs initially render on
    # neighborhood graph explorer
    allowed_fps = [
        fp["key"]
        for fp in response["neighbor_by"]
        if fp["key"] != "hybrid" and fp["data_exists"]
    ]
    response["initGraphFPs"] = [
        fp for fp in FP_GRAPH_PRIORITY_ORDER if fp in allowed_fps
    ][:2]

    # if no FP available, make error msg.
    error_msg = None
    if not chem:
        error_msg = MESSAGE["not_found"]
    elif not chem.get("dsstox_cid") and chem.get("dsstox_sid"):
        error_msg = MESSAGE["sid_only"]
    elif chem.get("is_markush"):
        error_msg = MESSAGE["markush"]
    available_fp = sum(i["data_exists"] for i in response["neighbor_by"])
    if available_fp < 1 and not error_msg:
        logger.info("No available FPs but no error msg. in uiSetup! %s", chem_id_in)
        error_msg = MESSAGE["unknown"]
    if available_fp < 1:
        # error_msg gets set for SID only chem., but not passed to UI if we have SID
        # only FP (bio/tox types)
        response["error_msg"] = (error_msg + "\n Target: {chem_id}").format(
            chem_id=chem_id + (f" ({chem_id_in})" if chem_id != chem_id_in else "")
        )

    # download options:
    response["download"] = [
        {
            "subdir": None,
            "name": "File Type",
            "description": "Select file type to download",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/xlsx",
            "name": "Excel - read across panel",
            "description": "Excel download of the read across panel"
            "\nBest for sorting etc.",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/csv",
            "name": "CSV - read across panel",
            "description": "CSV download of the read across panel"
            "\nTabular data for processing",
            "data_exists": True,
            "rel": "/step/readacross/download",
        },
        {
            "subdir": "/allNN",
            "name": "Top ~100 nearest neighbors",
            "description": "CSV, Excel compatible, includes fingerprints",
            "data_exists": True,
            "rel": "/step/radial/download",
        },
        {
            "subdir": "/RAview",
            "name": "Radial plot image",
            "description": "Radial plot image",
            "data_exists": True,
            "rel": "/step/radial/download",
        },
    ]

    # Just returning updated response to uiSetup() here, not sending response.
    return response
