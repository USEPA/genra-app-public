"""Tests for generate and run readacross endpoints"""
import dataclasses
import json
import logging
import re
from collections import defaultdict
from pprint import pformat

import pytest
import requests

from tests.conftest import make_url
from tests.defs import FP_types
from tests.lib.check_response import check_response_basics
from tests.lib.misc import (
    check_dict_structure_bool,
    check_first,
    check_keys_exist,
)

logger = logging.getLogger("genra_top")

# Currently uiRunReadAcross and uiGenerateReadAcross get the same results from FP_Types,
# so using uiRunReadAcross is ok even though this file runs tests for both.
ENDPOINT = "uiRunReadAcross"

# FIXME: now that we're using Pydantic these tests are deprecated, but this one's
# still used to ID chemical data rows with check_dict_structure_bool below.
# Maybe just drop all of this testing, but use this for now.
CHEM_COLUMN_STRUCTURE = [
    "colId",
    "field",
    {
        "headerComponentParams": [
            "chem_id",
            "isChecked",
            "name",
            "similarity",
            "targetChem",
            "useWidth",
        ],
    },
    "headerName",
    "headerTooltip",
    {"sortable": False},
    {"suppressMenu": True},
    "tooltipField",
]


@pytest.mark.slow_api
@pytest.mark.check_fp_type_variation_results
@pytest.mark.parametrize(
    "expected_test_params", FP_types(ENDPOINT), ids=map(str, FP_types(ENDPOINT))
)
def test_fp_types_results_run_read_across(
    expected_test_params, run_expected_test, api_url, calibrate
):
    """Test of uiRunReadAcross for different FPs."""
    expected_test_params.deep_diff_kwargs["significant_digits"] = 5

    v4_gra_data = run_expected_test(
        __file__, "uiGenerateReadAcross", expected_test_params
    )

    readacross_structural_tests(v4_gra_data)
    check_first(
        expected_test_params,
        v4_gra_data["columns"][1]["headerComponentParams"]["chem_id"],
    )
    check_domain_api(expected_test_params, "gra", v4_gra_data)

    # uiRunReadAcross

    etp = dataclasses.replace(expected_test_params)  # copy

    # pval is stochastic, so we want to ignore in comparison.
    # AUCpval is the "sort by AUC, then pval" sort column, same issue.
    # And it only needs one predClass to change because of pval to change the
    # ordering for the whole column slightly.
    etp = dataclasses.replace(
        etp,
        deep_diff_kwargs=etp_deep_diff_exclude(
            expected_test_params,
            [r"\['predict'\]|\['predClass'\]|\['(AUC)?pval'\]|_tip'\]"],
        ),
    )

    post_data = v4_rra_post(etp, v4_gra_data)
    # print("post_data", pformat(post_data))

    if expected_test_params.alternate_cols:
        # Test UI feature to select chems for neighborhood consideration
        # Simulated with alternating column/chm selection.
        for chem in post_data["chem_inc"][1::2]:
            chem["isChecked"] = False

    rra_url = f"{api_url}/api/genra/v4/uiRunReadAcross/"
    etp.resp = requests.post(
        rra_url,
        data=json.dumps(post_data),
        headers={"Content-Type": "application/json", "Accept": "*/*"},
    )
    etp.post_data = post_data  # for check_all_ids() and write_karate_test()
    v4_rra_data = run_expected_test(__file__, "uiRunReadAcross", etp)
    if expected_test_params.alternate_cols:
        # Covered by expected results but make sure
        assert any(
            item["headerComponentParams"]["isChecked"] is False
            for item in v4_rra_data["columns"]
        )
        assert any(
            item["headerComponentParams"]["isChecked"] is True
            for item in v4_rra_data["columns"]
        )

    if "dosage" not in expected_test_params.sumrs_by:
        # Prepare data to run comparison tests across engines to check we're getting
        # consistent results where expected.
        genrapy_post_data = post_data.copy()
        other_engine = (
            # FIXME: what now?
            "genrapy" if expected_test_params.engine == "genrapred" else "genrapy"
        )
        genrapy_post_data.update({"engine": other_engine})
        genrapy_resp = requests.post(
            rra_url,
            data=json.dumps(genrapy_post_data),
            headers={"Content-Type": "application/json", "Accept": "*/*"},
        )
        genrapy_data = check_response_basics(genrapy_resp)
        readacross_tests(expected_test_params, v4_rra_data, genrapy_data)
    readacross_structural_tests(v4_rra_data)
    check_first(
        expected_test_params,
        v4_rra_data["columns"][1]["headerComponentParams"]["chem_id"],
    )
    check_single_obs_prediction(v4_rra_data)
    check_domain_api(expected_test_params, "rra", v4_rra_data)
    assert len(v4_rra_data["data"]) == len(v4_gra_data["data"]), "Row count mismatch"


def etp_deep_diff_exclude(etp, exclusions):
    """*Add* exclude_regex_paths entries to deep_diff_kwargs in ExpectedTestParams"""
    ddk = etp.deep_diff_kwargs
    erp = ddk.get("exclude_regex_paths", [])
    erp.extend(exclusions)
    ddk["exclude_regex_paths"] = erp
    return ddk


def check_min_pos_neg(etp, gra_data, rra_data):
    """Check min pos and neg params applied correctly.  These control the mininum
    number of positive (effect) and negative (no effect) observations needed in the
    analogs to make any positive or negative prediction.

    Args:
    ----
        etp (ExpectedTestParams): test parameters
        gra_data (dict): uiGenerateReadAcross response
        rra_data (dict): uiRunReadAcross response
    """
    # observations for the target chem., target chem. is first entry
    # not use, see commented test below
    # observed = [k for k, v in gra_data[0]["readAcross"].items() if v != "no_data"]
    positives = defaultdict(lambda: 0)  # positive effect observations in the analogs
    negatives = defaultdict(lambda: 0)  # negative (no effect) obs. in the analogs
    for analog in gra_data[1:]:  # target chem. is first entry
        for endpoint, outcome in analog["readAcross"].items():
            if outcome == "no_effect":
                negatives[endpoint] += 1
            elif outcome != "no_data":
                positives[endpoint] += 1
    for endpoint, prediction in rra_data["predict"].items():
        if endpoint == "predicted":
            continue
        # Test that target observation is not replaced with a prediction.
        # This is NOT NEEDED per PO discussion 2021-6-30 as prediction includes true
        # positive, false positive etc. tags.
        # assert (
        #     endpoint not in observed
        # ), f"Prediction for {endpoint} for {etp.chem_id} with observed response."

        # check that we had enough positive effect obs. to make a positive prediction
        if prediction["value"] == 1:
            assert etp.min_pos is not None and positives[endpoint] >= etp.min_pos, (
                f"Positive effect prediction for {etp.chem_id} {rra_data['name']} for "
                f"{endpoint} with {positives[endpoint]} postitive observations, "
                f"needs {etp.min_pos}"
            )
        # check that we had enough no effect obs. to make a negative prediction
        if prediction["value"] == 0:
            assert etp.min_neg is not None and negatives[endpoint] >= etp.min_neg, (
                f"No effect prdiction for {etp.chem_id} with for {endpoint} with "
                f"{negatives[endpoint]} no effect observations, needs {etp.min_neg}"
            )


def readacross_structural_tests(readacross_data):
    """AG-grid structural tests for readacross panel"""
    chem_ids = []
    for column in readacross_data["columns"]:
        if check_dict_structure_bool(column, structure=CHEM_COLUMN_STRUCTURE):
            chem_ids.append(column["field"])

    # Note: "ep_name" and "ep_tip" are the row-data keys for both endpoint data and
    # physchem data
    row_keys = (
        chem_ids + [f"{chem_id}_tip" for chem_id in chem_ids] + ["ep_name", "ep_tip"]
    )
    for row in readacross_data["data"]:
        if row.get("ep_name") != "NO_DATA":
            check_keys_exist(row, row_keys)

            AUC_pval_seen = False
            pos_seen = 0
            neg_seen = 0

            for chem_id in chem_ids:
                # Check for AUC / pval display without 2 pos and 2 neg obs.
                if any(i in (row.get(chem_id + "_tip") or "") for i in ("AUC", "pval")):
                    AUC_pval_seen = True
                else:  # Don't count the target's obs.
                    value = str((row.get(chem_id) or {}).get("value") or "")
                    if not any(i in value for i in ("no_effect", "no_data")):
                        pos_seen += 1
                    if "no_effect" in value:
                        neg_seen += 1

            try:
                assert not (
                    AUC_pval_seen and (pos_seen < 2 or neg_seen < 2)
                ), "AUC/pval without 2 pos. and 2 neg. obs."
            except AssertionError:
                print(row)
                raise


def check_single_obs_prediction(v4_rra_data):
    """This test was prompted by the misinterpretation that a single observation of 100
    should give a prediction of 100 when of course the prediction is scaled by mol.
    mass.  But the logic that the prediction should match the observation when there's
    only one observation holds, so keep test but correct for mol. mass.
    """
    target_id = v4_rra_data["columns"][1]["colId"]
    neighbor_ids = [i["colId"] for i in v4_rra_data["columns"][2:] if not i.get("hide")]
    mass_row = next(
        i
        for i in v4_rra_data["data"]
        if isinstance(i, dict) and i.get("ep_name") == "Mass (g/mol)"
    )
    mass = {
        k: float(mass_row[k]["value"])
        for k in [target_id] + neighbor_ids
        if mass_row.get(k, {}).get("value") and mass_row[k]["value"] != "N/A"
    }
    for row in v4_rra_data["data"]:
        if row.get("ep_name") == "NO_DATA":
            continue
        est = row[target_id].get("est_disp")
        if not est:
            continue
        obs = [
            k
            for k in row
            if isinstance(row[k], dict) and "obs_disp" in row[k] and row[k]["obs_disp"]
        ]
        assert len(obs) >= 1  # must be at least one obs.
        if len(obs) == 1:  # if only one, it should match
            neighbor_id = obs[0]
            try:
                assert eval(est) * mass[neighbor_id] / mass[target_id] == pytest.approx(
                    eval(row[neighbor_id]["obs_disp"]), rel=0.2
                )
            except AssertionError:
                print(row["ep_name"], target_id, neighbor_id, mass, obs)
                raise


def get_act(hover):
    """Helper - given hover-over/tooltip string, returns ACT"""
    assert "ACT" in hover
    act = [sub_str for sub_str in hover.split(";") if "ACT" in sub_str][0]
    act = float(act.split("=")[1])
    return act


def readacross_tests(etp, readacross_data, other_engine_data=None):
    """Test prediction values/similarity weigfhted activities/engines/etc."""
    # test that similarity weighted activity values
    for row in readacross_data["data"]:
        target_cell = row.get(etp.chem_id)
        if (
            not target_cell
            or not isinstance(target_cell, dict)
            or not target_cell.get("isPrediction", False)
        ):
            # case: not a prediction cell
            continue
        hover = row.get(etp.chem_id + "_tip")
        act = get_act(hover)
        # iterate through neighborhood to calculate similarity weighted activity
        numerator, denominator = 0, 0
        for chem_id, chem in row.items():
            if (
                not isinstance(chem, dict)
                or "similarity" not in chem
                or chem["isPrediction"]
                or not chem["isChecked"]
            ):
                # case: not a neighboring chemical (we want to skip target too)
                continue
            sim = chem["similarity"]
            val = chem["value"]
            if val != "no_data":
                # case: an observation (positive or negative)
                denominator += sim
            if val not in ["no_data", "no_effect"]:
                # case: positive observation
                numerator += sim

        assert abs(numerator / denominator - act) < 0.02

    if not other_engine_data:
        return

    # test that similarity weighted activities are same across engines
    for row, other_row in zip(readacross_data["data"], other_engine_data["data"]):
        if row.get("isPhysProp"):
            continue
        if row.get("ep_name") == "NO_DATA":
            # case: no_filter with no data to predict on
            continue
        for what in ("ACT", "AUD"):  # Check ACT and AUC as shown in tooltips
            for chem_id in (
                k
                for k in row
                if isinstance(row[k], dict) and row[k].get("isPrediction")
            ):
                where = (  # ID test case to show in failed asserts
                    what,
                    chem_id,
                    row.get(f"{chem_id}_tip"),
                    other_row.get(f"{chem_id}_tip"),
                )
                what_match = re.search(rf"{what}=(\d+)", row[f"{chem_id}_tip"])
                other_what_match = re.search(
                    rf"{what}=(\d+)", other_row[f"{chem_id}_tip"]
                )
                assert (  # Both no match or neither no match.
                    (not what_match and not other_what_match)
                    or (what_match and other_what_match)
                ), where
                if what == "ACT" or what_match:  # AUC is optional, ACT is not
                    # Tested test with forced fail 2024-01-27 (ACT) and 2024-11-05 (AUC)
                    assert float(what_match.group(1)) == float(
                        other_what_match.group(1)
                    ), where


def v4_rra_post(expected_test_params, v4_gra_data):
    post_data = {
        "fp": expected_test_params.fp_id,
        "k0": expected_test_params.k0,
        "s0": expected_test_params.s0,
        "chem_id": expected_test_params.chem_id,
        "sel_by": expected_test_params.sel_by,
        "neg0": expected_test_params.min_neg,
        "pos0": expected_test_params.min_pos,
        "engine": expected_test_params.engine,
        "summarise": expected_test_params.summarise,
        "sumrs_by": expected_test_params.sumrs_by,
    }
    if any(i in expected_test_params.extra for i in ("&fp_weight=", "&flags=")):
        # fragile but sufficient
        extra = dict(
            i.split("=") for i in expected_test_params.extra.strip("&").split("&")
        )
        if "fp_weight" in extra:
            post_data["fp_weight"] = extra["fp_weight"]
            logger.info("Updated\n%s", post_data["fp_weight"])
        if "flags" in extra:
            post_data["flags"] = extra["flags"]
            if "usernn" in post_data["flags"]:
                post_data["fp"] = "user-defined"
                post_data["sel_by"] = "user-defined"
            if "multitarget" in post_data["flags"]:
                post_data["fp"] = "multitarget"
                post_data["sel_by"] = "multitarget"
    post_data["chem_inc"] = [
        {"isChecked": True, "chem_id": i["field"]}
        for i in v4_gra_data["columns"][1:]
        if "headerName" in i
    ]
    post_data["tox_inc"] = []
    return post_data


def check_domain_api(etp, endpoint, ui_data):
    """Check domain API matches for both GRA and RRA"""

    def parse_constant(constant):
        raise Exception(f"Found {constant} in JSON response")

    url = make_url(etp, "dataMatrix" if endpoint == "gra" else "readAcross")
    url = url.replace("pos0", "minpos")
    url = url.replace("neg0", "minneg")
    url += f"&engine={etp.engine}"
    logger.info(url)
    resp = requests.get(url)
    domain_data = check_response_basics(resp)
    json.loads(resp.content, parse_constant=parse_constant)  # check for NaNs
    # Don't count the sorting and row group columns
    cols = sum(1 for i in ui_data["columns"] if "headerComponentParams" in i)
    cols -= 1  # for the endpoint name column
    assert len(domain_data["coldef"]) == cols
    physprop = sum(1 for i in ui_data["data"] if i.get("isPhysProp"))
    assert len(domain_data["rowdef"]) == len(ui_data["data"]) - physprop
    chem_ids = [i["chem_id"] for i in domain_data["coldef"]]
    for ui_col, dom_col in zip(
        ui_data["columns"][1 : 1 + cols], domain_data["coldef"], strict=True
    ):
        assert ui_col["headerComponentParams"]["similarity"] == dom_col["similarity"]
    if ui_data["data"][physprop]["ep_name"] == "NO_DATA":
        assert len(domain_data["rowdef"]) == 1  # Informiative msg.
        assert domain_data["rowdef"][0]["name"] == "NO_DATA"
        assert len(domain_data["row"]) == 1  # empty row
    else:
        for row_i, (ui_row, dom_row) in enumerate(
            zip(ui_data["data"][physprop:], domain_data["row"], strict=True)
        ):
            for col_i, chem_id in enumerate(chem_ids):
                try:
                    if "ACT" in dom_row[col_i]["description"]:
                        # stochastic, prediction may differ
                        pass
                    else:
                        assert ui_row[chem_id]["value"] == dom_row[col_i]["value"]
                        # Need to match both
                        # '42 mg/kg/day' == '42 mg/kg/day' and
                        # 'dosage=340.3 mg/kg/day, log molar=-0.002' ==
                        # '340.3 mg/kg/day'
                        assert len(dom_row[col_i]["description"]) >= 3  # 'hit'
                        assert dom_row[col_i]["description"] in ui_row[chem_id + "_tip"]
                except Exception:
                    # This is a lot of output, only print it if there is an error
                    print(pformat(domain_data["coldef"][col_i]))
                    print(pformat(dom_row[col_i]))
                    print(pformat(domain_data["rowdef"][row_i]))
                    print(pformat(ui_row["ep_name"]))
                    print(pformat(ui_row[chem_id + "_tip"]))
                    print(pformat(ui_row[chem_id]))
                    raise
