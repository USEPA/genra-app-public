"""Base class for aggregators.  See also ./aggregators.py

Aggregator role
===============

Once a list of neighbors is selected in panels 1 and 2, the Aggregator manages the cross
tabulation of that list of chemicals with some facets (distinct fields or aggregations)
of a data-stream, e.g.  ToxRef (data-stream) assay endpoints (facets) or ToxCast
(data-stream) gene groups (facets).  See Aggregator lookup below for mapping of
data-stream and facet to an Aggregator and presentation in the UI.

When instantiated, the Aggregator calls its .load_frame() method to load data into its
.frame (GenraFrame) variable.  Aggregators are constructed with a GenRAState instance,
stored in .state, which collects fp_id, s0, sel_by etc. parameters.   The .frame.col_def
list of dicts is essentially the searchFP() result for the .state, an can be used rather
than calling searchFP in subsequent steps.  See [./genraframe.py](./genraframe.py) for
an example of .frame content.

An Aggregator should define .ag_grid_al(), .ag_grid_gra(), and .ag_grid_rra() to provide
AG Grid representations of its .frame, *which it should be able to do without further
calculation*.  The exception to this rule is that prior to calling .ag_grid_rra() its
.do_prediction() method must be called.  .do_prediction() should consider .state.engine
("genrapred" or "genrapy") and .state.sumrs_by, in cases where the Aggregator handles
more than one sumrs_by value.

Aggregator lookup
=================

The FPGen and PredEngine Registrable classes are identified by a single key like
`tox_txrf`.

Aggregator represents the "Group" and "By" (data-stream and data-stream facet)
selections in panel 3.  So where FPGen and PredEngine are identified by `x`, Aggregator
is identified by `x,y`.  We want to allow separate Aggregator classes to implement
`x=A,y=M` and `x=A,y=N` selections.  If we just used separate registrable keys, `A_M`
and `A_N`, the regular registrable lookup by scalar key would work.  But we want to
group Aggregators which act on the same data-stream (Group) in the UI.

So in uiRadialView.py Aggregator listings are merged by name, and in subsequent ui*
methods Aggregator.aggregator_for() is used to find the right Aggregator.

For example:
    Aggregator: ToxRefAggBinary   ToxRefAggDosage
        agg_id: tox_txrf          tox_txrf_dosage
     groupings: tox_fp            tox_fp_dosage
          name: ToxRef            ToxRef

because of the matching name these are merged in uiRadialView, and the correct  one is
selected (by unique groupings value) by Aggregator.aggregator_for() when needed.

Note that Aggregators can provide multiple groupings, the "y" in "x,y" above, partly
historical but retained to support a case where separate classes for a lot of groupings
with similar implementations would be inefficient.
"""

import multiprocessing
import os
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from celery import group

from genraweb.deploy_types import DeployType
from genraweb.lib import genrapy_multiprocess, multitarget
from genraweb.lib.aggregator.genraframe import GenraFrame
from genraweb.lib.chem_id import ChemID
from genraweb.lib.engine.engines import PredEngine
from genraweb.lib.fp.fputils import parse_fp
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.genrapred import runGenRA
from genraweb.lib.logging import logger
from genraweb.lib.misc import chunks, get_with_mongo_path
from genraweb.lib.mongofp_NN import searchFP
from genraweb.lib.properties.physprop import prop_data
from genraweb.lib.registerable import Registerable
from genraweb.lib.state import GenRAFlag
from genraweb.resources import DB

COL = FPGen.fp_collection_names()
DS = FPGen.fp_collection_paths()


# Used to describe columns in exports.
METADATA = {
    "pred_class": "Predictions - Pos: positive, no observation; "
    "Neg: negative, no observation; FN: false negative; "
    "FP: false Positive; TN: true negative; TP: true positive.",
    "ACT": "Similarity weighted activity score.",
    "AUC": "Area Under Curve.",
    "log_molar": "log10((mg/kg/day)/mol_mass)",
    "pred_dose": "Predicted dose mg/kg/day.",
    "pred_log_molar": "Predicted log_molar.",
    "pval": "P-value.",
}


class Aggregator(
    metaclass=Registerable,
    _reg_class="aggregator",
    _reg_id="agg_id",
    _reg_order="_agg_order",
):
    """Base class for data aggregators.

    See Registerable for docs. on sub-class registration.
    """

    # filters aren't Registerables
    # filters match fp_ids
    # agg_ids need to match?  Or filters specify defaul agg?

    # Order to present aggregators in dropdowns etc.
    _agg_order = [
        "tox_txrf",
        "tox_txrf_dosage",
        "test_group_db",
        "test_group_db2",
        "bio_txct",
    ]

    # Classes that inherit this class should define class variable `agg_fp_class`
    # that is an FPGen class of the aggregating data type.
    # E.g., for toxcast aggregators: agg_fp_class = FPGen.FPClass["bio_txct"]

    @classmethod
    def _reg_check_register(cls, aggr_class) -> bool:
        """See Registerable - check if aggr_class should be registered."""
        deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]
        return deployment_type <= aggr_class.maxDepType

    def __init__(self, state):
        self.state = state
        logger.info(f"Using {self.__class__.__name__}")
        self.frame = self.load_frame()
        self.row_description = "endpoint name"
        self.sort_options = [
            {
                "sortId": "alphaName",
                "name": lambda agg: agg.row_description.capitalize(),
                "description": lambda agg: f"Alphabetical by {agg.row_description}",
                "key": lambda rowdef, row: rowdef["name"],
            }
        ]

    def load_frame(self):
        """*PARTIALLY* initialize a frame, just setting the col_def component."""
        frame = GenraFrame()
        neighbors = searchFP(
            chem_id_in=self.state.chem_id,
            fp=self.state.fp_str(),
            sel_by=self.state.sel_by,
            s0=self.state.s0,
            max_hits=self.state.k0 + 1,
            simple=True,
        )
        frame.col_def.extend(neighbors)
        for col_def in frame.col_def:
            col_def["col_id"] = col_def["chem_id"]
            # column "zero" set to target below
            col_def["role"] = (
                "target" if GenRAFlag.MULTITARGET & self.state.flags else "analog"
            )

            col_def["_exports"] = [
                # In a column called col_def["chem_id"], report dose if present else
                # value
                {"name": col_def["chem_id"], "source": ["dose", "value"]},
            ]
        frame.col_def[0]["role"] = "target"
        return frame

    @staticmethod
    def aggregator_for(summarise, sumrs_by):
        """See module doc. string for explanation."""
        name = Aggregator.aggregator[summarise].name
        for key, agg in Aggregator.aggregator.items():
            if agg.name == name and sumrs_by in agg.groupings:
                break
        else:
            raise Exception(f"Could not find Aggregator for ({summarise},{sumrs_by})")
        return Aggregator.aggregator[key]

    @staticmethod
    def col_description(ngbr):
        """Make "Bisphenol A : DTXCID30182 / DTXSID424242" text for header."""
        description = []
        if "dsstox_cid" in ngbr:
            description.append(ngbr["dsstox_cid"])
        if "dsstox_sid" in ngbr:
            description.append(ngbr["dsstox_sid"])
        description = " / ".join(filter(lambda x: x, description))  # No Nones or ""
        sep = " : " if description else ""
        return f"{ngbr['name']}{sep}{description}"

    def do_prediction(self):
        """Run the prediction."""
        # UI API can specify a subset of chemicals to include in prediction
        if self.state.get("chem_inc"):
            self.chem_inc = [
                chem["chem_id"] for chem in self.state.chem_inc if chem["isChecked"]
            ]
        else:
            self.chem_inc = [i["chem_id"] for i in self.frame.col_def]

        predictor = (
            self.do_prediction_genrapred
            if self.state.engine == "genrapred"
            else self.do_prediction_genrapy
        )

        # FIXME: first_only needed?  or permute only for multitarget?
        if multitarget.is_multi(self.state.chem_id):
            return multitarget.permute(
                self, predictor, first_only=GenRAFlag.USERNN in self.state.flags
            )

        return predictor


class AGGridMixin:
    """Mixin to support AG Grid data. Mainly created to follow DRY principle across
    aggregators.

    NOTE: Following condition(s) must be met by classes inheriting this mixin:
    - It inherits Aggregator class
    """

    def ag_grid_al(self):
        """Return AG Grid AL represetnation"""
        response = {
            "columns": [
                {
                    # Column def. for the end point name column
                    "cellRenderer": None,
                    "cellStyle": {"borderBottom": "1px dashed grey"},
                    "field": "ep_name",
                    "filter": "agTextColumnFilter",
                    "floatingFilter": True,
                    "headerComponentParams": {"name": "Assay endpoint"},
                    "headerName": "Assay endpoint",
                    "headerTooltip": "The biological system tested by the assay",
                    "maxWidth": 150,
                    "minWidth": 35,
                    "tooltipField": "ep_tip",
                },
            ],
            "data": [],
        }

        # Column defs. for each neighbor
        for ngbr in self.frame.col_def:
            response["columns"].append(
                {
                    "field": ngbr["chem_id"],
                    "headerComponentParams": {
                        "name": ngbr["name"],
                    },
                    "headerName": ngbr["name"],
                    "headerTooltip": self.col_description(ngbr),
                    "sortable": False,
                    "suppressHeaderMenuButton": True,
                    "tooltipField": ngbr["chem_id"] + "_tip",
                    "filter": False,
                    "minWidth": 35,
                }
            )

        # Add rows
        for row_def, row in zip(self.frame.row_def, self.frame.row):
            data = {
                "ep_name": row_def["name"],
                "ep_tip": row_def["description"],
            }
            response["data"].append(data)
            for col_def, col in zip(self.frame.col_def, row):
                data[col_def["chem_id"] + "_tip"] = col["observation"]
                value = 0 if col["observation"] == "no_data" else 1
                data[col_def["chem_id"]] = value

        return response

    def ag_grid_gra(self):
        """Return AG Grid GRA representation"""
        response = {
            "predEngines": [
                {
                    "key": i.engine_id,
                    "name": i.engine_name,
                    "description": i.engine_description,
                    "data_exists": i.is_supported(
                        fp_id=self.state.fp_str(), sumrs_by=self.state.sumrs_by
                    ),
                }
                for i in PredEngine.engine.values()
            ],
            "sortOptions": [
                {
                    "key": i["sortId"],
                    "name": i["name"](self),
                    "description": i["description"](self),
                    "data_exists": True,  # shouldn't be there otherwise
                }
                for i in self.sort_options
            ],
            "columns": [
                {
                    # Column def. for the end point name column
                    "cellStyle": {"borderBottom": "1px dashed grey"},
                    "field": "ep_name",
                    "filter": "agTextColumnFilter",
                    "floatingFilter": True,
                    "headerComponentParams": {
                        "chem_id": "ep_name",
                        "isChecked": True,
                        "useWidth": False,
                        "name": "Assay endpoint",
                        "similarity": 0,
                    },
                    "headerName": "Assay endpoint",
                    "headerTooltip": "The biological system tested by the assay",
                    "hide": True,
                    "maxWidth": 150,
                    "minWidth": 35,
                    "suppressColumnsToolPanel": True,
                    "tooltipField": "ep_tip",
                },
            ],
            "data": [],
        }

        # Column defs. for each neighbor
        for col_i, ngbr in enumerate(self.frame.col_def):
            response["columns"].append(
                {
                    "colId": ngbr["chem_id"],
                    "field": ngbr["chem_id"],
                    "headerComponentParams": {
                        "chem_id": ngbr["chem_id"],
                        "isChecked": True,
                        "useWidth": False,
                        "name": ngbr["name"],
                        "similarity": ngbr["similarity"],
                        "targetChem": ngbr["role"] == "target",
                    },
                    "headerName": ngbr["name"],
                    "headerTooltip": self.col_description(ngbr),
                    "sortable": False,
                    "suppressHeaderMenuButton": True,
                    "tooltipField": ngbr["chem_id"] + "_tip",
                    "filter": False,
                    "minWidth": 35,
                }
            )
        # Column defs. for sort options
        for sort in self.sort_options:
            response["columns"].append(
                {
                    "colId": sort["sortId"],
                    "field": sort["sortId"],
                    "hide": True,
                    "suppressColumnsToolPanel": True,
                    "filter": False,
                    "minWidth": 35,
                }
            )

        # Add rows
        for row_def, row in zip(self.frame.row_def, self.frame.row):
            out_row = {
                "ep_name": row_def["name"],
                "ep_tip": row_def["description"],
            }
            response["data"].append(out_row)
            for col_def, cell in zip(self.frame.col_def, row):
                out_row[col_def["chem_id"]] = {
                    "cellRenderer": "RedBlueTooltip",
                    "isChecked": True,  # for GRA, always True
                    "isPrediction": False,
                    "similarity": round(col_def["similarity"], 2),
                    "useWidth": False,  # for GRA, always False
                    "value": cell["value"],
                }
                out_row[col_def["chem_id"] + "_tip"] = cell["description"]

        # Columns for sorting
        for row_def_i, row_def in enumerate(self.frame.row_def):
            row_def["_index"] = row_def_i
        for sort in self.sort_options:
            row_def_row = list(zip(self.frame.row_def, self.frame.row, strict=True))
            if row_def_row[0][1]:
                # keys use `row[0]...` fails when no results (no_filter)
                try:
                    row_def_row.sort(key=lambda x: sort["key"](x[0], x[1]))
                except Exception:
                    logger.error(sort)
                    raise
            for row_i, order in enumerate(row_def_row):
                response["data"][order[0]["_index"]][sort["sortId"]] = row_i

        # panel_four_edits():
        # Phys. Chem. chemical properties added here
        chem_ids = self.frame.col_attr("chem_id")
        response["data"][:0] = prop_data(chem_ids)
        response["columns"][0].update(dict(hide=True, suppressColumnsToolPanel=True))
        response["columns"].append(
            dict(
                field="physchem",
                hide=True,
                rowGroup=True,
                suppressColumnsToolPanel=True,
                filter=False,
                minWidth=35,
            )
        )
        return response

    def ag_grid_rra(self):
        """Return AG Grid RRA representation"""
        response = self.ag_grid_gra()
        del response["predEngines"]
        phys_prop = sum(1 for i in response["data"] if i.get("isPhysProp"))
        assert len(self.frame.row) == len(response["data"]) - phys_prop
        checked_ids = [
            chem["chem_id"] for chem in self.state.chem_inc if chem["isChecked"]
        ]
        logger.info(checked_ids)
        for data_row, out_row in zip(self.frame.row, response["data"][phys_prop:]):
            for col_def, cell in zip(self.frame.col_def, data_row):
                out = out_row[col_def["chem_id"]]
                out["isChecked"] = col_def["chem_id"] in checked_ids
                out["useWidth"] = bool(self.state.get("useWidth"))
                out["isPrediction"] = cell["isPrediction"]
                out_row[col_def["chem_id"] + "_tip"] = cell["description"]
                if "p_val" in cell:
                    out["pval"] = cell["p_val"]
        for col_def, out_col in zip(self.frame.col_def, response["columns"][1:]):
            out_col["headerComponentParams"]["isChecked"] = (
                col_def["chem_id"] in checked_ids
            )
            out_col["headerComponentParams"]["useWidth"] = bool(
                self.state.get("useWidth")
            )

        return response


class BinaryMixin:
    """Mixin to support binary level aggregator data, integrating genrapred
    and genra-py (GenRAPredClass) predictions.

    NOTE: Following conditions must be met by classes using/inheriting this mixin:
    - Inherits Aggregator class
    - Defines following class attributes:
        fp_y_pos : (str)
            key to positive observations (e.g. "toxp_txrf")
        fp_y_neg : (str)
            key to negative observations (e.g. "bion_txct")
        label_path : (str)
            mongodb path to additional labeling data (e.g. "hits")
        agg_fp_class : (FPGen)
            FPGen fingerprint class for aggregating data
    - Implements the get_row_label method
    - Implements the get_positive_label method
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sort_options.extend(
            [
                {
                    "sortId": "posObs",
                    "name": lambda frame: "Positive obs.",
                    "description": lambda frame: "Number of positive observations",
                    "key": self.pos_obs_key,
                },
                {
                    "sortId": "negObs",
                    "name": lambda frame: "Negative obs.",
                    "description": lambda frame: "Number of negative observations",
                    "key": self.neg_obs_key,
                },
                {
                    "sortId": "allObs",
                    "name": lambda frame: "Observations",
                    "description": lambda frame: "Total number of observations",
                    "key": self.all_obs_key,
                },
            ]
        )

    def pos_obs_key(self, row_def, row):
        """Number of positive observations on a row, as a sorting option."""
        return (
            sum(1 for cell in row if cell["value"] not in ("no_data", "no_effect")),
            row_def["name"],
        )

    def neg_obs_key(self, row_def, row):
        """Number of negative observations on a row, as a sorting option."""
        return (
            sum(1 for cell in row if cell["value"] == "no_effect"),
            row_def["name"],
        )

    def all_obs_key(self, row_def, row):
        """Number of observations on a row, as a sorting option."""
        return (
            sum(1 for cell in row if cell["value"] != "no_data"),
            row_def["name"],
        )

    def load_frame(self):
        frame = super().load_frame()  # set col_def, neighbors list

        chem_ids = frame.col_attr("chem_id")
        # START: modified from fputils.get_toxref_data_for_chems
        search = ChemID.chem_id_search(chem_ids)
        projection = ChemID.chem_id_proj(include_core_fields=True)
        pos_path = DS[self.fp_y_pos]
        neg_path = DS[self.fp_y_neg]
        projection.update({pos_path: 1, neg_path: 1, self.label_path: 1})
        coll_name = self.agg_fp_class.fp_output_basename
        data = {i["chem_id"]: i for i in DB[coll_name].find(search, projection)}
        # END: modified from fputils.get_toxref_data_for_chems
        # START: modified from fputils.get_toxref_assays_for_chems
        sparse = defaultdict(dict)  # (end_point, chem) -> cell mapping
        for chem_id in chem_ids:
            if chem_id not in data:
                continue  # target has no FP
            chem = data[chem_id]
            chem_labels = self.get_chem_labels(chem)
            # do neg first so conflicting records choose pos_effect over no_effect
            for ep_name in get_with_mongo_path(chem, neg_path + ".ds"):
                assert (ep_name, chem_id) not in sparse
                sparse[(ep_name, chem_id)] = {"text": "no_effect"}
            for ep_name in get_with_mongo_path(chem, pos_path + ".ds"):
                # assert (ep_name, chem_id) not in sparse # TODO
                label = self.get_positive_label(ep_name, chem_labels)
                sparse[(ep_name, chem_id)] = label if label else {"text": "pos_effect"}

        endpoints = sorted(set(i[0] for i in sparse))
        for endpoint in endpoints:
            description = self.get_row_label(endpoint)
            frame.row_def.append(
                {"row_id": endpoint, "name": endpoint, "description": description}
            )
            frame.row.append([])
            for chem_id in chem_ids:
                obs = sparse.get((endpoint, chem_id), {"text": "no_data"})
                frame.row[-1].append(
                    {
                        "isPrediction": False,
                        "observation": obs["text"],
                        "description": obs["text"],
                        "dose": obs.get("dose"),
                        "unit": obs.get("unit"),
                        "value": (
                            "pos_effect"
                            if obs["text"] not in ["no_effect", "no_data"]
                            else obs["text"]
                        ),
                    }
                )
        # END: modified from fputils.get_toxref_assays_for_chems

        if not endpoints:  # no_filter or similar selected neighbors with no data
            frame.row_def.append(
                {
                    "row_id": "NO_DATA",
                    "name": "NO_DATA",
                    "description": "No data for these neighbors,\n"
                    "select a different filter in panel 1.",
                }
            )
            frame.row.append([])

        return frame

    def do_prediction(self):
        predictor = super().do_prediction()
        if predictor is True:
            # `True` used to indicate a multi-target prediction has run
            return

        self.sort_options.extend(
            [
                {
                    "sortId": "predClass",
                    "name": lambda agg: "Pred. class",
                    "description": lambda agg: "Prediction class (FN/FP/Neg/Pos/TN/TP)",
                    "key": lambda rowdef, row: (
                        # GenraPy calls it "accuracy", GenraPred "pred"
                        row[0].get("accuracy", row[0].get("pred", " ")),
                        rowdef["name"],
                    ),
                },
                {
                    "sortId": "ACT",
                    "name": lambda agg: "ACT",
                    "description": lambda agg: "Order by ACT",
                    "key": lambda rowdef, row: (
                        row[0].get("a_s", 0),
                        rowdef["name"],
                    ),
                },
            ]
        )

        return predictor()

    def do_prediction_genrapy(self):
        # get FP data (X) in dataframe form; initialize emty
        X = pd.DataFrame()
        fps, weights = parse_fp(self.state.fp_str())
        chem_inc = [
            i["chem_id"] for i in self.state.get("chem_inc", []) if i["isChecked"]
        ]
        slices = []
        # the column index that each component starts in
        _idx = 0
        for fp in fps:
            # get FP data (X) in dataframe form
            rows = []
            for chem in self.frame.col_def:
                if chem_inc and chem["chem_id"] not in chem_inc:
                    continue
                row = {"chem_id": chem["chem_id"]}
                if fpds := chem.get(f"fpds_{fp}"):
                    row.update({bit: 1 for bit in fpds})
                rows.append(row)
            X_component = pd.DataFrame(rows)
            X_component = X_component.fillna(0)
            X_component = X_component.set_index("chem_id")
            # target is included, but removed a few lines down
            # some chemicals won't have component data so use "outer"
            X = X.merge(X_component, how="outer", left_index=True, right_index=True)
            new_idx = _idx + len(X_component.columns)
            slices.append(slice(_idx, new_idx))
            _idx = new_idx
        target = X.loc[[self.state.chem_id]]  # single row dataframe
        X = X.drop([self.state.chem_id])

        # get assay endpoint data (Y) in dataframe form
        Y = [
            {"endpoint": row_def["row_id"]}
            | {
                chem_id: (
                    np.nan
                    if col["observation"] == "no_data"
                    else 0
                    if col["observation"] == "no_effect"
                    else 1
                )
                for chem_id, col in zip(self.frame.col_attr("chem_id")[1:], row[1:])
                if chem_id in self.chem_inc
            }
            for row_def, row in zip(self.frame.row_def, self.frame.row)
        ]
        Y = pd.DataFrame(Y).set_index("endpoint")
        # each row is a chemical and each column is an endpoint
        Y = Y.transpose()
        Y.index.name = "chem_id"
        # remove target and set the same order
        Y = Y.reindex(X.index)

        ep_names = list(Y.columns)

        eps_chunks = chunks(ep_names, multiprocessing.cpu_count())
        X, Y, target, slices = genrapy_multiprocess.to_json(X, Y, target, slices)
        Res = group(
            genrapy_multiprocess.celery_predict_endpoints.subtask(
                (
                    chunk,
                    X,
                    Y,
                    target,
                    self.state.chem_id,
                    slices,
                    weights,
                    self.state.k0,
                    self.state.pos_min,
                    self.state.neg_min,
                )
            )
            for chunk in eps_chunks
        )
        with warnings.catch_warnings():
            Res = Res.apply_async()
            Res = Res.get()
        preds = {}
        for pred in Res:
            # flatten
            preds.update(pred)

        # generate a model and predict for every endpoint
        for row, ep_name in zip(self.frame.row, ep_names):
            if ep_name not in preds:
                # prediction was skipped one of various reasons (e.g., not enough
                # positive observations)
                continue
            pred = preds[ep_name]
            pred, a_s, auc, p_val = (
                pred["pred"],
                pred["a_s"],
                pred["auc"],
                pred["p_val"],
            )

            row[0]["isPrediction"] = True
            row[0].update({"pred": pred, "a_s": a_s})
            predicted = "pos_effect" if pred else "no_effect"
            row[0]["value"] = predicted
            # Check genraweb/lib/genrapred.py for consistency, if making changes
            observed = row[0]["observation"]
            if predicted == "pos_effect" and observed not in ("no_effect", "no_data"):
                accuracy = "TP"
            elif predicted == "pos_effect" and observed == "no_effect":
                accuracy = "FP"
            elif predicted == "no_effect" and observed not in ("no_effect", "no_data"):
                accuracy = "FN"
            elif predicted == "no_effect" and observed == "no_effect":
                accuracy = "TN"
            else:
                # case: no observation
                accuracy = "Pos" if predicted == "pos_effect" else "Neg"
            row[0]["accuracy"] = accuracy

            row[0]["description"] = f"{accuracy}; ACT={row[0]['a_s']}"
            if auc is not None:
                # do this check otherwise UI could error out
                row[0]["auc"], row[0]["p_val"] = auc, p_val
                if AUC_for_row_ok(row[1:]):
                    row[0][
                        "description"
                    ] += "; AUC={auc:.3g}; pval={p_val:.3g}".format_map(row[0])
            else:
                # could not measure, so set auc=0 and p_val=1
                row[0]["auc"], row[0]["p_val"] = 0, 1

        self.frame.col_def[0]["_exports"].extend(
            [
                {"name": "pred_class", "source": ["accuracy"]},
                {"name": "ACT", "source": ["a_s"]},
                {"name": "AUC", "source": ["auc"]},
                {"name": "pval", "source": ["p_val"]},
            ]
        )

    def get_chem_labels(self, chem):
        """Classes inheriting this mixin should override this method if there are labels
        to be extracted for a given chem document.
        """
        pass

    def do_prediction_genrapred(self):
        self.sort_options.append(
            {
                "sortId": "AUCpval",
                "name": lambda agg: "AUC, pval",
                "description": lambda agg: "Order by AUC then pval",
                "key": lambda rowdef, row: (
                    row[0].get("auc", 0),
                    row[0].get("p_val", 0),
                    rowdef["name"],
                ),
            }
        )
        preds = runGenRA(
            self.state.chem_id,
            CID=self.chem_inc,
            DB=DB,
            fp_x=self.state.fp_str(),
            fp_y_pos=self.fp_y_pos,
            fp_y_neg=self.fp_y_neg,
            sel_by=self.state.sel_by,
            metric="jaccard",
            k0=self.state.k0,
            s0=self.state.s0,
            pred=True,
            ret="df",
            n_perm=200,
            pos_min=self.state.pos_min,
            neg_min=self.state.neg_min,
        )
        # Example pred:
        # {'out': 'CHR:adrenal gland', 'auc': 0.0, 'k0': 10, 's0': 0.1, 'fp':
        # 'chm_mrgn', 'n_pos': 1, 'n_neg': 4, 'p_val': 0.83, 't0': 0.0, 'chem_id':
        # 'DTXCID30182', 'dsstox_cid': 'DTXCID30182', 'pred': 'TN', 'a_t': 0.0, 'a_s':
        # 0.212, 'a_p': 0}

        endpoint = self.frame.row_index("name")  # endpoint name -> row number
        chem = self.frame.col_index("chem_id")  # chem_id -> col_number
        self.frame.col_def[0]["_exports"].extend(
            [
                {"name": "pred_class", "source": ["pred"]},
                {"name": "ACT", "source": ["a_s"]},
                {"name": "AUC", "source": ["auc"]},
                {"name": "pval", "source": ["p_val"]},
            ]
        )
        for pred in preds:
            row = self.frame.row[endpoint[pred["out"]]]
            cell = row[chem[pred["chem_id"]]]
            cell.update(pred)
            cell["isPrediction"] = True

            if cell["pred"] in ("Neg", "TN", "FN"):
                cell["value"] = "no_effect"
            else:
                # better to crash than report incorrectly
                assert cell["pred"] in ("Pos", "TP", "FP"), cell["pred"]
                cell["value"] = "pos_effect"

            fmt = "{pred}; ACT={a_s:.3g}"
            # don't show AUC without 2 pos. and 2 neg. obs.
            if AUC_for_row_ok(row[1:]):
                fmt += "; AUC={auc:.3g}; pval={p_val:.3g}"
            cell["description"] = fmt.format_map(cell)


def AUC_for_row_ok(row):
    """Row meets criteria for displaying AUC."""
    return (
        sum(1 for i in row if i["observation"] not in ("no_effect", "no_data")) >= 2
        and sum(1 for i in row if i["observation"] == "no_effect") >= 2
    )
