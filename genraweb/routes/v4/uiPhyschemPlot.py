"""Generate SVG PhysChem plot."""
import random
import urllib

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from flask import Response, make_response
from flask_openapi3 import APIBlueprint

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fputils import fp_hybrid_name_from_lists
from genraweb.lib.mongofp_NN import searchFP
from genraweb.lib.properties.physprop import ID2PP, chem_props
from genraweb.lib.state import GenRAFlag, GenRAState
from genraweb.resources import V4_URL_PREFIX
from genraweb.routes.api_models import PhyschemPlot
from genraweb.routes.api_tags import uiv4_tag

uiPhyschemPlot_bp = APIBlueprint("uiPhyschemPlot_bp", __name__)


@uiPhyschemPlot_bp.get(
    urllib.parse.urljoin(V4_URL_PREFIX, "uiPhyschemPlot/"),
    summary=PhyschemPlot.__doc__,
    tags=[uiv4_tag],
    responses={200: {"description": "A Physchem plot"}}
)
def uiPhyschemPlot(query: PhyschemPlot):
    """Generate plot for physchem properties of neighborhood."""
    gst = GenRAState(
        query.model_dump(),
        chem_id=ChemID.promote_id(query.chem_id)[0],
        fp=fp_hybrid_name_from_lists(query.model_dump()),
    )
    data = plot_data(gst)
    includes_target = query.chem_id.split(",")[0] in data["chem_id"].values
    return build_plot(
        query.ftype,
        data,
        includes_target=includes_target
        and not gst.flags & GenRAFlag.MULTITARGET,
    )


def plot_data(gst: GenRAState) -> pd.DataFrame:
    """Prepare data for plot as DataFrame."""
    # obtain and merge neighborhood data and physchem data, then flatten out
    neighbors = searchFP(
        gst.chem_id, fp=gst.fp, sel_by=gst.sel_by, s0=gst.s0, max_hits=gst.k0 + 1
    )
    chem_ids = [chem["chem_id"] for chem in neighbors]
    all_props = chem_props(chem_ids)

    props_data = [
        {
            "prop_id": prop_id,
            "prop_units": ID2PP[prop_id].units,
            "chem_id": gst.chem_id,
            "prop_val": prop,
        }
        for gst.chem_id, props in ((i, all_props.get(i, {})) for i in chem_ids)
        for prop_id, prop in props.items()
        if ID2PP[
            prop_id
        ].in_plot  # some properties (HBD/HBA) aren't plotted but included in panel data
    ]

    props_df = pd.DataFrame(props_data)
    plot_df = pd.merge(props_df, pd.DataFrame(neighbors), on=["chem_id"], how="inner")
    # If a field like CASRN mixes ints and strings .transform("min") etc. fails
    for column in list(plot_df):
        if plot_df[column].dtype == np.dtype("O"):
            # Ensure `O`bject type columns are entirely strings
            plot_df[column] = plot_df[column].astype(str)
    plot_gb = plot_df.groupby(["prop_id"])
    prop_min = plot_gb.transform("min")
    prop_max = plot_gb.transform("max")
    # normalize [0,1] to put on same y axis
    plot_df["prop_norm"] = (plot_df["prop_val"] - prop_min["prop_val"]) / (
        prop_max["prop_val"] - prop_min["prop_val"]
    )
    # With no filter and something like ethanol, you get results like ethanol, C13
    # ethanol, ethanol + Fe, 2 x ethanol + Fe, etc.  For boiling point, at least, OPERA
    # sees these as all the same, so you can have 15 results with no x.max()-x.min()
    # range, so normalization is NaN.  Make it 0.5 instead so the user can see the one
    # value being predicted for all NN.
    plot_df.loc[plot_df["prop_norm"].isna(), "prop_norm"] = 0.5

    return plot_df


def build_plot(
    ftype: str,  # "html" or "svg",
    plot_df: pd.DataFrame,
    includes_target: bool,  # Possible for target to have no physchem data.
) -> Response:
    """Construct the plotly plot and return as response."""
    fig = go.Figure()

    chem_ids = plot_df["chem_id"].unique()
    chem_id = chem_ids[0]
    order = list(ID2PP)  # order of property IDs from PHYSPROP
    prop_types = sorted(set(plot_df["prop_id"]), key=lambda x: order.index(x))
    for prop_type in prop_types:
        # for each prop type, trace a boxplot
        prop_df = plot_df[plot_df["prop_id"] == prop_type]
        trace = {
            "boxpoints": False,
            "x": [order.index(i) for i in prop_df["prop_id"]],
            "y": prop_df["prop_norm"],
            "showlegend": False,
            "fillcolor": None,
            "line": {"color": "grey"},
            "hoverinfo": "skip",
            "width": 0.6,
        }
        fig.add_trace(go.Box(trace))

    # at most 24 distinct colors/chems
    colors = list(px.colors.qualitative.Dark24)
    if includes_target:
        colors[:0] = ["white"]
    for chem_id in chem_ids:
        # for each chem, trace markers/scatter, using plotly Box
        chem_df = plot_df[plot_df["chem_id"] == chem_id]
        if chem_df.empty:
            continue
        name_text = chem_df["name"].iloc[0]
        if len(name_text) > 30:
            name_text = name_text[:30].strip() + "..."
        trace = {
            "x": [
                order.index(i) + 0.1 - 0.2 * random.random()  # noqa: S311 not crypto.
                for i in chem_df["prop_id"]
            ],
            "y": chem_df["prop_norm"],
            "marker": {
                "color": colors.pop(0) if colors else "black",
                "symbol": "diamond"
                if chem_id == chem_ids[0] and includes_target
                else "circle",
                "size": 10,
                "line": {
                    "width": 2 if chem_id == chem_ids[0] and includes_target else 0
                },
            },
            "boxpoints": "all",
            "fillcolor": "rgba(255,255,255,0)",
            "hoverinfo": "text",
            "hovertext": [
                f"{i.prop_val} {i.prop_units} {i.name}" for i in chem_df.itertuples()
            ],
            "line": {
                "color": "rgba(255,255,255,0)",
            },
            "pointpos": 0,
            "showlegend": True,
            "name": name_text,
        }
        fig.add_trace(go.Box(trace))

    fig.update_layout(
        title="Physchem Properties",
        title_x=0.5,
        xaxis_title="Physchem property",
        yaxis_title="Relative distribution",
        yaxis_showticklabels=False,
        legend_title_text="Analogs, decreasing similarity",
    )

    cats = [
        ID2PP[i].name + (f" ({ID2PP[i].units})" if ID2PP[i].units else "")
        for i in prop_types
    ]
    fig.update_xaxes(ticktext=cats, tickvals=list(range(len(cats))))
    if ftype == "html":
        response_data = fig.to_html()
        content_type = "text/html"
    elif ftype == "json":
        response_data = fig.to_json()
        content_type = "application/json"
    else:
        # default will be SVG
        response_data = fig.to_image("svg")
        content_type = "image/svg+xml"

    response = make_response(response_data)
    response.content_type = content_type
    return response
