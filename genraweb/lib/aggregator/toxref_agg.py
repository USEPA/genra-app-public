"""Dev. test Aggregator for testing, mostly providing mock data to UI"""

import re
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.exceptions import DataConversionWarning

from genraweb.deploy_types import DeployType

from genra.rax.skl.hybrid import GenRAPredValueHybrid
from genraweb.lib.fp.fputils import parse_fp
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger
from genraweb.lib.misc import backcalc_dosage, get_with_mongo_path, normalize_dosage
from genraweb.resources import ENDPOINT_DETAILS, MESSAGE

from .aggregator import Aggregator, AGGridMixin, BinaryMixin

# remove +0 from 1e+02 and 0 from 1e-02, and trim .0
_squash = re.compile(r"\+0|(?<=-)0|\.0$|0+(?=e)")

COMP = [
    lambda x: str(x),
    lambda x: str(round(x)),
    lambda x: f"{x:.0g}",
    lambda x: f"{x:.0e}",
    lambda x: f"{x:.2g}",
]


def comp_x(number):
    """Represent float number to 4 or fewer chars. if possible."""
    for comp in COMP:
        txt = _squash.sub("", comp(number))
        val = eval(txt)
        if len(txt) <= 4 and 0.8 <= abs(val / number) <= 1.2:
            return txt
    return str(number)


class ToxRefAggBinary(BinaryMixin, AGGridMixin, Aggregator):
    """Aggregator for Toxref binary data."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for col_def in self.frame.col_def:  # Add units to exports
            col_def["_exports"].append(
                {"name": col_def["chem_id"] + "_units", "source": ["unit"]}
            )

    # Aggregator attributes
    agg_id = "tox_txrf"
    name = "ToxRef"
    description = "The ToxRef DB"
    groupings = {
        "tox_fp": {"name": "Tox Fingerprint", "description": "A ToxRef FP"},
    }
    maxDepType = DeployType.PROD
    agg_fp_class = FPGen.FPClass["tox_txrf"]
    fp_y_pos = "toxp_txrf"
    fp_y_neg = "toxn_txrf"
    label_path = "tox_q"

    def get_row_label(self, ep_name):
        """Get the endpoint label. Previously used to be in fp_stats collection,
        but was moved locally for GEN-789.

        Parameters
        ----------
        ep_name : str
            assay endpoint name


        Returns
        ----------
        label : str
            endpoint label that may include notes ("Effects may include X, Y, Z, ...")

        """
        label = ep_name
        if stat := ENDPOINT_DETAILS.get(ep_name):
            more = [stat[i] for i in ["name", "notes"] if i in stat and stat[i]]
            if more:
                label = ": ".join(more)

        return label

    def get_chem_labels(self, chem):
        chem_labels = get_with_mongo_path(chem, self.label_path)
        chem_labels = pd.DataFrame(chem_labels)
        chem_labels = chem_labels.set_index("fp2")
        return chem_labels

    def get_positive_label(self, ep_name, tox_q_df):
        """Get the dosage label stored in "tox_q" of document. Currently, dosage
        choice for when a given endpoint has multiple studies is the minimum
        dosage among the studies.

        Parameters
        ----------
        ep_name : str
            assay endpoint name
        tox_q_df: Pandas.DataFrame
            dataframe of rows of dosages across endpoints, from get_chem_labels


        Returns
        ----------
        label : str
            dosage label using tox_q
        """
        if tox_q_df.empty:
            return None
        dosage_df = tox_q_df.loc[[ep_name]]
        dosage_df = dosage_df[dosage_df.dose > 0]
        dosage_df = dosage_df[dosage_df.dose == dosage_df.dose.min()]
        if dosage_df.empty:
            return None
        ans = {"dose": dosage_df.dose.iat[0], "unit": dosage_df.dose_unit.iat[0]}
        ans["text"] = f"{ans['dose']} {ans['unit']}"
        return ans


def _get_assay_dosage(ep_name, tox_q):
    """Gets the toxref study dosage and units for given endpoint based on
    `tox_q` field in the chemical's document in toxref_tr_fp collection.

    Currently, dosage choice for when a given endpoint has multiple studies
    is the minimum dosage among the studies."""
    if not tox_q:
        return None
    dosage_df = pd.DataFrame(tox_q)
    dosage_df = dosage_df[dosage_df.fp2 == ep_name]
    dosage_df = dosage_df[dosage_df.dose > 0]
    dosage_df = dosage_df[dosage_df.dose == dosage_df.dose.min()]
    if dosage_df.empty:
        return None
    dose = str(dosage_df.dose.iat[0])
    unit = str(dosage_df.dose_unit.iat[0])
    return f"{dose} {unit}"


class ToxRefAggDosage(ToxRefAggBinary):
    _dir = "RL"  # dir(ection) for gradient display

    @staticmethod
    def _lfmt(num):
        """Format for log values, whether displayed or not."""
        return num if not num else f"{num:.3f}"

    agg_id = "tox_txrf_dosage"
    name = "ToxRef"
    description = "The ToxRef DB"
    groupings = {
        "tox_fp_dosage": {
            "name": "Tox Fingerprint Dosage",
            "description": "Negative log molar of dosage",
        }
    }
    maxDepType = DeployType.PROD

    def load_frame(self):
        frame = super().load_frame()
        # normalized dosage for all cells
        for row_def, row in zip(frame.row_def, frame.row):
            for col_def, col in zip(frame.col_def, row):
                col["norm_dose"] = normalize_dosage(
                    col["observation"], col_def.get("mol_weight")
                )
        # min / max by CHR etc.
        min_max = defaultdict(lambda: None)
        for row_def, row in zip(frame.row_def, frame.row):
            for col in row:
                if not np.isnan(col["norm_dose"]):
                    for stat in min, max:
                        key = (row_def["name"].split(":")[0], stat)  # split CHR: etc.
                        min_max[key] = (
                            col["norm_dose"]
                            if min_max[key] is None
                            else stat(min_max[key], col["norm_dose"])
                        )
        # copy min / max into place
        for row_def, row in zip(frame.row_def, frame.row):
            for col in row:
                col["rangeMin"] = min_max[(row_def["name"].split(":")[0], min)]
                col["rangeMax"] = min_max[(row_def["name"].split(":")[0], max)]
                if col["rangeMin"] == col["rangeMax"]:
                    col["rangeMin"] -= 0.5
                    col["rangeMax"] += 0.5

        return frame

    def do_prediction(self):
        """To avoid do_prediction() from BinaryMixin, which we have even though
        not Binary."""
        predictor = Aggregator.do_prediction(self)
        if predictor is not True:
            return predictor()

    def do_prediction_genrapy(self):
        """Needs to be do_prediction_genrapy() and not do_prediction() so aggregator
        do_prediction() can use multitarget.permute() if needed.
        """
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
        Y = []
        for row_def, row in zip(self.frame.row_def, self.frame.row):
            obs = {"endpoint": row_def["row_id"]}
            Y.append(obs)
            for col_def, col in zip(self.frame.col_def, row):
                if chem_inc and col_def["chem_id"] not in chem_inc:
                    continue
                obs[col_def["chem_id"]] = col["norm_dose"]

        Y = pd.DataFrame(Y).set_index("endpoint")
        # each row is a chemical and each column is an endpoint; index is now chem_id
        Y = Y.transpose()
        # remove target and set the same order
        Y = Y.reindex(X.index)

        for row, ep_name in zip(self.frame.row, Y.columns):
            # get sub_Y
            sub_Y = Y[Y[ep_name].notnull()][ep_name]

            # Check if min/max requirements met; because target data set to NaN in
            # Y[self.state.chem_id] = step above, don't need to worry about counting
            # target obs. here.
            # NOTE: no_effect *ignored* so testing neg_min makes no sense
            if (~np.isnan(sub_Y)).sum() < self.state.pos_min:
                continue

            # get sub_X
            sub_X = X.loc[sub_Y.index]

            if sub_X.shape[0] == 0 or sub_Y.shape[0] == 0:
                continue
            # build model and predict
            model = GenRAPredValueHybrid(
                algorithm="brute",
                metric="jaccard",
                weights=lambda distances: 1 - distances,
                n_neighbors=len(sub_Y.index),
                slices=slices,
                hybrid_weights=weights,
            )
            model.fit(sub_X.values.astype("bool"), sub_Y.values.astype("float"))
            # target is a single row dataframe, so return is also a single row dataframe
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=DataConversionWarning)
                pred = model.predict(target)[0]

            row[0]["estimate"] = pred
            dosage = backcalc_dosage(pred, self.frame.col_def[0]["mol_weight"])
            row[0]["pred_dose"] = dosage  # For export
            row[0]["description"] = (
                f"pred. log molar={self._lfmt(pred)}, "
                f"pred. toxicity value={dosage:g} mg/kg/day"
            )

            if not np.isnan(row[0]["norm_dose"]):
                row[0]["description"] += (
                    f", act. log molar={self._lfmt(row[0]['norm_dose'])}, "
                    f"act. dosage={row[0]['observation']}"
                )

        self.frame.col_def[0]["_exports"].extend(
            [
                {"name": "log_molar", "source": ["norm_dose"]},
                {"name": "pred_dose", "source": ["pred_dose"]},
                {"name": "pred_log_molar", "source": ["estimate"]},
            ]
        )

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
        for col_i, ngbr in enumerate(self.frame.col_def):
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
        response = super().ag_grid_gra()
        # Can't use chems. with no mass.
        for out_col, ngbr in zip(response["columns"], self.frame.col_def):
            if "headerComponentParams" in out_col:
                out_col["headerComponentParams"]["isChecked"] = "mol_weight" in ngbr

        prop_rows = sum(1 for i in response["data"] if i.get("isPhysProp"))
        for row_def, row, out_row in zip(
            self.frame.row_def,
            self.frame.row,
            response["data"][prop_rows:],
            strict=True,  # check lengths of these match
        ):
            for col_def, col in zip(self.frame.col_def, row):
                out_row[col_def["chem_id"] + "_tip"] = col["observation"]
                value = (
                    "pos_effect"
                    if col["observation"] not in ["no_effect", "no_data"]
                    else col["observation"]
                )
                out_row[col_def["chem_id"]] |= {
                    "value": value,
                    "isChecked": "mol_weight" in col_def,
                }

                if col["norm_dose"] is not None and not np.isnan(col["norm_dose"]):
                    out_row[col_def["chem_id"] + "_tip"] = (
                        f"dosage={col['observation']}, "
                        f"log molar={self._lfmt(col['norm_dose'])}"
                    )
                    out_row[col_def["chem_id"]].update(
                        {
                            "cellRenderer": "ContinuousPredObs",
                            "continuousData": True,
                            "rangeMin": col["rangeMin"],
                            "rangeMax": col["rangeMax"],
                            "confMin": col.get("confMin"),
                            "confMax": col.get("confMax"),
                            "estimate": col.get("estimate"),
                            "observation": col.get("norm_dose"),
                            "obs_disp": (
                                comp_x(col["dose"]) if col.get("dose") else None
                            ),
                            "isPrediction": False,
                            "dir": self._dir,
                        }
                    )

        return response

    def ag_grid_rra(self):
        """Return AG Grid RRA represetnation"""
        response = self.ag_grid_gra()
        del response["predEngines"]
        phys_prop = sum(1 for i in response["data"] if i.get("isPhysProp"))
        assert len(self.frame.row) == len(response["data"]) - phys_prop
        checked_ids = [
            chem["chem_id"] for chem in self.state.chem_inc if chem["isChecked"]
        ]
        logger.info(checked_ids)
        assert len(self.frame.row) == len(response["data"]) - phys_prop
        remove = []
        for data_row, out_row in zip(self.frame.row, response["data"][phys_prop:]):
            for col_def, data in zip(self.frame.col_def, data_row):
                out = out_row[col_def["chem_id"]]
                out["isChecked"] = col_def["chem_id"] in checked_ids
                out["useWidth"] = self.state.useWidth
                if not col_def.get("mol_weight"):
                    out["isChecked"] = False
                    if col_def["chem_id"] not in remove:
                        remove.append(col_def["chem_id"])
                    # uncheck if no weight to normalize dosage
                if "estimate" in data and not np.isnan(data["estimate"]):  # GenraPy
                    out["isPrediction"] = True
                    out["continuousData"] = True
                    out["cellRenderer"] = "ContinuousPredObs"
                    out["confMin"] = data.get("confMin")
                    out["confMax"] = data.get("confMax")
                    out["rangeMin"] = data["rangeMin"]
                    out["rangeMax"] = data["rangeMax"]
                    out["estimate"] = data["estimate"]
                    est_disp = backcalc_dosage(data["estimate"], col_def["mol_weight"])
                    out["est_disp"] = comp_x(est_disp)
                    out["dir"] = self._dir
                    out_row[col_def["chem_id"] + "_tip"] = data["description"]

        for col_def, out_col in zip(self.frame.col_def, response["columns"][1:]):
            out_col["headerComponentParams"]["isChecked"] = (
                col_def["chem_id"] in checked_ids
            )
            out_col["headerComponentParams"]["useWidth"] = bool(
                self.state.get("useWidth")
            )

        if remove:
            response["error_msg"] = (
                MESSAGE["weightless"] + " (" + ", ".join(remove) + ")"
            )

        return response
