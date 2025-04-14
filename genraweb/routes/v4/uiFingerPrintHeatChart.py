"""Generate tabular data for rendering heatmap."""
import os
import urllib

from flask import jsonify, request
from flask_openapi3 import APIBlueprint

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.fp.nn_lookup import fp_n_for_chems
from genraweb.lib.logging import logger
from genraweb.lib.misc import echo_flags
from genraweb.lib.mongofp_NN import searchFP
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import (
    FingerPrintHeatChart,
    FingerPrintHeatChartResponse,
)
from genraweb.routes.api_tags import uiv4_tag

# FPs shown be default in panel 2, in order.  Until needed elsewhere, isolate here.
FPS_SHOW = ["chm_mrgn", "chm_httr", "chm_ct", "bio_txct", "tox_txrf"]
uiFingerPrintHeatChart_bp = APIBlueprint("uiFingerPrintHeatChart_bp_v4", __name__)


@uiFingerPrintHeatChart_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiFingerPrintHeatChart/"),
    responses={200: FingerPrintHeatChartResponse},
    summary=FingerPrintHeatChart.__doc__,
    tags=[uiv4_tag],
)
def uiFingerPrintHeatChart(query: FingerPrintHeatChart):
    """Render summary of ct,bio,tox information for chemical."""
    return jsonify(
        echo_flags(
            request,
            heatmap_table(
                chem_id=query.chem_id,
                s0=query.s0,
                k0=query.k0,
                fp_id=fp_hybrid_name_from_lists(query.model_dump()),
                sel_by=query.sel_by,
            ),
        )
    )


def heatmap_table(
    chem_id,  # chemical ID
    s0,  # similarity limit
    k0,  # number of neighbors
    fp_id,  # FP to use
    sel_by,  # data to filter by
):
    """Generate tabular data for rendering heatmap"""
    logger.info(
        dict(
            cid=chem_id,
            fp=fp_id,
            sel_by=sel_by,
            s0=s0,
            max_hits=k0 + 1,  # +1 for the target
        )
    )
    NN = searchFP(
        chem_id,
        fp=fp_id,
        sel_by=sel_by,
        s0=s0,
        max_hits=k0 + 1,  # +1 for the target
    )

    response = dict(
        columns=[
            dict(
                headerName="Chemical",
                headerTooltip="Target chemical and neighbors, "
                "click ☰ then ⦀ to show more data streams.",
                field="name",
                tooltipField="name",
                cellRenderer="GenraChemicalLink",
                cellRendererParams={"useField": "name"},
                suppressHeaderMenuButton=False,
                lockPosition="left",
                filter=False,
                minWidth=45,
            )
        ],
        data=[],
    )
    details_link = os.environ.get("GENRA_DETAILS_LINK", "")
    fp_ids = set()  # collect all FP IDs seen (chm_httr, tox_txrf, etc.)
    chem_ids = [ChemID.chem_id(chem) for chem in NN]
    fps = fp_n_for_chems(chem_ids=chem_ids)
    for chem in NN:
        chem_id = ChemID.chem_id(chem)
        response["data"].append(
            {
                "chem_id": chem_id,
                "dtxcid": chem.get("dsstox_cid"),
                "dtxsid": chem.get("dsstox_sid"),
                "name": chem.get("name"),
            }
        )
        current = response["data"][-1]
        fp_ids.update(fps[chem_id])
        current.update(fps[chem_id])
        if details_link.strip() and ChemID.id_type(chem_id) in (ChemID.SID, ChemID.CID):
            ccd_id = current.get("dtxsid") or current.get("dtxcid")
            current["details_link"] = details_link.format(chem_id=ccd_id)

    for fp_id_i in sorted(fp_ids):  # _i to not overwrite the param.
        fp_class = FPGen.FPClass[fp_id_i]
        response["columns"].append(
            dict(
                # bio_ -> b: etc. to save space
                # headerName=re.sub(r"^(.)[^_]*_", r"\1:", fp_id_i),
                headerName=fp_id_i,
                headerTooltip=fp_class.description,
                field=fp_id_i,  # e.g. chm_httr
                cellRenderer="HeatColoredNumber",
                suppressHeaderMenuButton=True,
                filter=False,
                hide=fp_id_i not in FPS_SHOW,
                minWidth=35,
                maxWidth=35,
                cellClass="ag-right-aligned-cell",
            )
        )
        values = [  # all FP counts for this FP ID / column
            i[fp_id_i] for i in response["data"] if i[fp_id_i] is not None
        ]
        min_value = min(values)
        max_value = max(values)
        for row in response["data"]:
            # convert `n` to {"value": n, "scaled": 0.2} where scaled is column relative
            row[fp_id_i] = dict(
                value=row[fp_id_i],
                scaled=(
                    round((row[fp_id_i] - min_value) / (max_value - min_value), 4)
                    if max_value > min_value
                    else 0
                ),
            )

    return response
