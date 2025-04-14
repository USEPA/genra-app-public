"""Tests for uiDownload.py"""
import io
import json

import pandas as pd
import pytest
import requests

from genraweb.routes.v4.uiDownload import floaty
from tests.lib.misc import deep_diff

POST_DATA = {
    "s0": 0,
    "chem_inc": [
        {"chem_id": "DTXCID30182", "isChecked": True},
        {"chem_id": "DTXCID001771", "isChecked": False},
        {"chem_id": "DTXCID602360", "isChecked": False},
        {"chem_id": "DTXCID70716", "isChecked": True},
        {"chem_id": "DTXCID10465", "isChecked": False},
        {"chem_id": "DTXCID406081", "isChecked": True},
    ],
    "chem_id": "DTXCID30182",
    "fp": "chm_mrgn",
    "k0": 10,
    "neg0": 0,
    "pos0": 0,
    "sel_by": "tox_txrf",
    "tox_inc": ["CHR:adrenal gland", "CHR:albumin"],
    "summarise": "tox_txrf",
    "sumrs_by": "tox_fp",
}


@pytest.mark.slow_api
def test_uiDownload(api_url):
    """Tests the uiDownload across both file types and states (gra vs rra) by
    (1) checking valid (file content) returned, and (2) checking expected
    table structure.
    """
    dfs = []
    for ftype, read_fn in [("csv", pd.read_csv), ("xlsx", pd.read_excel)]:
        url = f"{api_url}/api/genra/v4/uiDownload/{ftype}"
        resp = requests.post(
            url,
            data=json.dumps(POST_DATA),
            headers={"Content-Type": "application/json", "Accept": "*/*"},
        )
        assert resp.ok
        # check the filename is in headers
        assert "Content-Disposition" in resp.headers, resp.headers
        assert ftype in resp.headers["Content-Disposition"], resp.headers
        assert "filename=genra_2" in resp.headers["Content-Disposition"], resp.headers
        # Access-Control-Expose-Headers gives UI ability to access filename
        assert "Access-Control-Expose-Headers" in resp.headers, resp.headers
        # use BytesIO to convert to file-like object
        base_df = read_fn(io.BytesIO(resp.content))
        if ftype == "csv":
            assert "metadata" in base_df.columns
            assert base_df["metadata"][0].startswith("run_at: ")
            del base_df["metadata"]
        base_df.set_index(base_df.columns[0], inplace=True)
        # from_excel reads similarity and weight as string not float
        base_df.loc[["Mass g/mol", "similarity"]] = base_df.loc[
            ["Mass g/mol", "similarity"]
        ].astype(float)
        assert min(base_df.loc["similarity"]) >= 0.0
        assert max(base_df.loc["similarity"]) == 1.0
        dfs.append(base_df)
    # comparing dataframes whines about "100.0" != 100, so apply floaty()
    dfs[0] = [[floaty(cell) for cell in row.tolist()] for _, row in dfs[0].iterrows()]
    dfs[1] = [[floaty(cell) for cell in row.tolist()] for _, row in dfs[1].iterrows()]
    # Header row repeated in Excel data, delete second copy.
    for row, data in enumerate(dfs[1]):
        if row > 5 and str(data[0]).startswith("DTXCID"):
            del dfs[1][row]
            break
    else:
        assert False, "Did not find second copy of headers in Excel."
    deep_diff(dfs[0], dfs[1], ignore_nan_inequality=True, significant_digits=5)


@pytest.mark.slow_api
def test_uiDownload_dosage(api_url):
    """2024-11-13 uiDownload was not respecting summarise / sumrs_by.

    This test is similar to test_uiDownload, but with sumrs_by set to
    tox_fp_dosage.
    """
    post_data = POST_DATA.copy()
    post_data["sumrs_by"] = "tox_fp_dosage"
    post_data["rra"] = True

    dfs = []
    real_dfs = []
    for ftype, read_fn in [("csv", pd.read_csv), ("xlsx", pd.read_excel)]:
        url = f"{api_url}/api/genra/v4/uiDownload/{ftype}"
        resp = requests.post(
            url,
            data=json.dumps(post_data),
            headers={"Content-Type": "application/json", "Accept": "*/*"},
        )
        # use BytesIO to convert to file-like object
        base_df = read_fn(io.BytesIO(resp.content))
        real_dfs.append(base_df.copy())  # Need full non-transposed data for later.
        print(real_dfs[-1].columns)
        if ftype == "csv":
            assert "metadata" in base_df.columns
            assert base_df["metadata"][0].startswith("run_at: ")
            del base_df["metadata"]
        base_df.set_index(base_df.columns[0], inplace=True)
        # from_excel reads similarity and weight as string not float
        base_df.loc[["Mass g/mol", "similarity"]] = base_df.loc[
            ["Mass g/mol", "similarity"]
        ].astype(float)
        assert min(base_df.loc["similarity"]) >= 0.0
        assert max(base_df.loc["similarity"]) == 1.0
        dfs.append(base_df)
    # comparing dataframes whines about "100.0" != 100, so apply floaty()
    dfs[0] = [[floaty(cell) for cell in row.tolist()] for _, row in dfs[0].iterrows()]
    dfs[1] = [[floaty(cell) for cell in row.tolist()] for _, row in dfs[1].iterrows()]
    # Header row repeated in Excel data, delete second copy.
    for row, data in enumerate(dfs[1]):
        if row > 5 and str(data[0]).startswith("DTXCID"):
            del dfs[1][row]
            break
    else:
        assert False, "Did not find second copy of headers in Excel."
    deep_diff(dfs[0], dfs[1], ignore_nan_inequality=True, significant_digits=5)

    # Now the differences from test_uiDownload - check pred_log_mol etc. is present.
    for col_name in ("log_molar", "pred_dose", "pred_log_molar"):
        assert col_name in real_dfs[0].columns
        assert col_name in real_dfs[1].columns


@pytest.mark.slow_api
def test_top_100(api_url):
    """Tests top 100 download"""
    url = f"{api_url}/api/genra/v4/uiDownload/allNN"
    resp = requests.post(
        url,
        json={
            "chem_id": "DTXCID30182",
            "fp": "chm_mrgn",
            "sel_by": "tox_txrf",
        },
        headers={"Content-Type": "application/json", "Accept": "*/*"},
    )
    resp.raise_for_status()
    # check the filename is in headers
    assert "Content-Disposition" in resp.headers, resp.headers
    assert "csv" in resp.headers["Content-Disposition"], resp.headers
    assert "filename=genra_2" in resp.headers["Content-Disposition"], resp.headers
    assert "Access-Control-Expose-Headers" in resp.headers, resp.headers
    # use BytesIO to convert to file-like object
    dframe = pd.read_csv(io.BytesIO(resp.content))
    assert dframe.shape[0] == 100, dframe
    assert "similarity" in dframe.columns, dframe.columns
