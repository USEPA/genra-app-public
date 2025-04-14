"""Dev. test Aggregator for testing, mostly providing mock data to UI"""
from collections import defaultdict

import numpy as np
import pandas as pd

from genraweb.deploy_types import DeployType
from genraweb.defs import COLORS
from genraweb.lib.engine.engines import PredEngine
from genraweb.lib.misc import normalize_dosage
from genraweb.lib.properties.physprop import prop_data

from .toxref_agg import ToxRefAggDosage


# copied from fputils
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


class DevTestAgg(ToxRefAggDosage):
    """Descending from ToxRefAggDosage gives us rangeMin etc."""

    agg_id = "test_group_db"
    name = "A Test"
    description = "The Test DB Entry"
    groupings = {
        "test_fld": {"name": "Test Field", "description": "The first test field"},
    }
    maxDepType = DeployType.DEV

    def do_prediction(self):
        for row in self.frame.row:  # first norm_dose value on the row, if any
            data0 = next((i for i in row if not np.isnan(i["norm_dose"])), None)
            if data0 is not None:
                row[0]["norm_dose"] = data0["norm_dose"]
                row[0]["estimate"] = round(0.6 * data0["norm_dose"], 2)
                row[0]["confMin"] = 0.4 * data0["norm_dose"]
                row[0]["confMax"] = 0.6 * data0["norm_dose"]

    def round(self, x, p):
        return x if x is None else round(x, p)

    def ag_grid_gra(self):
        """Return AG Grid GRA represetnation"""
        response = super().ag_grid_gra()
        response |= {
            "predEngines": [
                {
                    "key": i.engine_id,
                    "name": i.engine_name,
                    "description": i.engine_description,
                    "data_exists": i.is_supported(
                        fp_id=self.state.fp_id, sumrs_by=self.state.sumrs_by
                    ),
                }
                for i in PredEngine.engine.values()
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
                        "name": "Assay endpoint",
                        "similarity": 0,
                    },
                    "headerName": "Assay endpoint",
                    "headerTooltip": "The biological system tested by the assay",
                    "hide": True,
                    "maxWidth": 150,
                    "maxWidth": 35,
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
                        "name": ngbr["name"],
                        "similarity": ngbr["similarity"],
                        "targetChem": col_i == 0,
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
        chem_ids = self.frame.col_attr("chem_id")
        # Phys. Chem. chemical properties added here
        response["data"].extend(prop_data(chem_ids))
        for row_def, row in zip(self.frame.row_def, self.frame.row):
            data = {
                "ep_name": row_def["name"],
                "ep_tip": row_def["description"],
            }
            response["data"].append(data)
            for col_def, col in zip(self.frame.col_def, row):
                data[col_def["chem_id"] + "_tip"] = col["observation"]
                value = (
                    "pos_effect"
                    if col["observation"] not in ["no_effect", "no_data"]
                    else col["observation"]
                )
                data[col_def["chem_id"]] = {
                    "cellRenderer": "RedBlueTooltip",
                    "isChecked": True,  # for GRA, always True
                    "isPrediction": False,
                    "similarity": round(col_def["similarity"], 2),
                    "useWidth": False,  # for GRA, always False
                    "value": value,
                }
                if col["norm_dose"] is not None and not np.isnan(col["norm_dose"]):
                    data[
                        col_def["chem_id"] + "_tip"
                    ] = f"dosage={col['observation']}, log molar={col['norm_dose']}"
                    data[col_def["chem_id"]].update(
                        {
                            "cellRenderer": "ContinuousPredObs",
                            "continuousData": True,
                            "rangeMin": col["rangeMin"],
                            "rangeMax": col["rangeMax"],
                            "confMin": col.get("confMin"),
                            "confMax": col.get("confMax"),
                            "estimate": self.round(col.get("estimate"), 2),
                            "observation": self.round(col.get("norm_dose"), 2),
                            "isPrediction": False,
                        }
                    )

                if col.get("estimate"):
                    data[
                        col_def["chem_id"] + "_tip"
                    ] = f"dosage={col['observation']}, log molar={col['norm_dose']}"
                    data[col_def["chem_id"]].update(
                        {
                            "estimate": col["estimate"],
                            "isPrediction": True,
                        }
                    )

        # panel_four_edits():
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
        """Return AG Grid RRA represetnation"""
        return self.ag_grid_gra()

    def skip_key(self, row, key):
        if key.startswith("ep") or key.endswith("_tip"):
            return True
        if (
            "no_data" in (tip := row[key + "_tip"].strip())
            or "no_effect" in tip
            or tip.startswith("TN")
            or tip.startswith("Neg")
        ):
            return True
        return False


class DevTestAgg2(DevTestAgg):  # need .rows() etc. from ToxRefAgg for uiAssayList
    agg_id = "test_group_db2"
    name = "A Test"
    description = "The Test DB Entry"
    groupings = {
        "test_fld2": {
            "name": "Test Field 2",
            "description": "The second test field",
        },
    }
    maxDepType = DeployType.DEV

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
                        key = (row_def["name"].split(":")[0], stat)
                        min_max[key] = (
                            col["norm_dose"]  # split of CHR:, etc.
                            if min_max[key] is None
                            else stat(min_max[key], col["norm_dose"])
                        )
        # copy min / max into place
        for row_def, row in zip(frame.row_def, frame.row):
            for col in row:
                col["rangeMin"] = min_max[(row_def["name"].split(":")[0], min)]
                col["rangeMax"] = min_max[(row_def["name"].split(":")[0], max)]

        return frame

    def do_prediction(self):
        pass

    def ag_grid_gra(self):
        """Return AG Grid GRA represetnation"""
        response = super().ag_grid_gra()
        response |= {
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
                        "name": ngbr["name"],
                        "similarity": ngbr["similarity"],
                        "targetChem": col_i == 0,
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
        chem_ids = self.frame.col_attr("chem_id")
        # Phys. Chem. chemical properties added here
        response["data"].extend(prop_data(chem_ids))
        for row_def, row in zip(self.frame.row_def, self.frame.row):
            out = {
                "ep_name": row_def["name"],
                "ep_tip": row_def["description"],
            }
            response["data"].append(out)
            for col_def, col in zip(self.frame.col_def, row):
                out[col_def["chem_id"] + "_tip"] = col["observation"]
                value = (
                    "pos_effect"
                    if col["observation"] not in ["no_effect", "no_data"]
                    else col["observation"]
                )
                out[col_def["chem_id"]] = {
                    "cellRenderer": "RedBlueTooltip",
                    "isChecked": True,  # for GRA, always True
                    "isPrediction": False,
                    "similarity": round(col_def["similarity"], 2),
                    "useWidth": False,  # for GRA, always False
                    "value": value,
                }
                if not np.isnan(col["norm_dose"]):
                    out[col_def["chem_id"]] |= dict(
                        cellRenderer="MultiCategory",
                        color=self.categoryColor(col["norm_dose"]),
                    )

        # panel_four_edits():
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
        """Return AG Grid RRA represetnation"""
        return self.ag_grid_gra()

    def categoryColor(self, text):
        text = str(text)
        return COLORS[sum(ord(i) for i in text) % 7]

    def demo_cat_data(self, readacross):
        for row in readacross["data"]:
            for key in row:
                if key.startswith("ep") or key.endswith("_tip"):
                    continue  # skips less than self.skip_key()
                row[key].update(
                    dict(
                        cellRenderer="MultiCategory",
                        color=self.categoryColor(row[key + "_tip"]),
                    )
                )
