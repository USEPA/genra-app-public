"""Tests for hybrid functionalities."""
import io
import json

import numpy as np
import pandas as pd
import pytest
import requests

from genraweb.lib.mongofp_NN import searchFP
from tests.defs import EQUIVALENT_SETS, EQUIVALENT_SETS_IDS, STOCHASTIC_PATHS
from tests.lib.check_response import check_response_basics
from tests.lib.misc import deep_diff


@pytest.mark.parametrize("equivalent_set", EQUIVALENT_SETS, ids=EQUIVALENT_SETS_IDS)
def test_hybrid_edge_cases(api_url, equivalent_set):
    """Tests the edge cases of hybrid predictions in lib/genrapred.py. See
    `EQUIVALENT_SETS` defined in `tests.defs.py`.
      - for weight=0, its FP similarity doesn't get counted for NNs calc/prediction.
      - if weights are "equivalent" (ratio), NNs/predictions are same
      - ordering of FPs doesn't change NNs/predictions assuming same (ratio) weights
      - decimal/floating weights are accepted

    Uses uiRadialView to tests neighborhood equivalence, and uiRRA to test prediction
    equivalence."""

    rv_prev = None
    rra_prev = None
    fp_prev = None

    chem_id = "DTXCID103900"

    rra_url = f"{api_url}/api/genra/v4/uiRunReadAcross"
    for fp in equivalent_set:

        # test neighborhood data equivalent (chems info, similarity values)
        rv_url = (
            f"{api_url}/api/genra/v4/uiRadialView/?chem_id={chem_id}&"
            f"k0=10&fp={fp}&sel_by=tox_txrf&summarise=tox_txrf"
            f"&sumrs_by=tox_fp&s0=0.1&neg0=1"
        )
        rv_resp = requests.get(rv_url)
        rv_data = check_response_basics(rv_resp)
        if rv_prev is None:
            rv_prev = rv_data
            fp_prev = fp
        else:
            # adjust comparison paths because similarity tag different on hybrids,
            # Significant digits is 3 because tests that collapse to a single FP
            # (other weights zero) get looked up from pre-calc. which is rounded
            # for efficiency in writing to mongo DB.
            deep_diff(
                rv_prev,
                rv_data,
                what=(fp_prev, fp),
                significant_digits=3,
                exclude_regex_paths={r"root\['result'\]\[\d+\]\[('similarity_tag')"},
            )

        # test predictions equivalent
        post_data = {
            "fp": fp,
            "k0": 10,
            "chem_id": chem_id,
            "sel_by": "tox_txrf",
            "neg0": 0,
            "pos0": 0,
            "chem_inc": [
                {"chem_id": chem["chem_id"], "isChecked": True}
                for chem in rv_data["result"]
            ],
            "engine": "genrapred",
        }
        rra_resp = requests.post(
            rra_url,
            data=json.dumps(post_data),
            headers={"Content-Type": "application/json", "Accept": "*/*"},
        )
        rra_data = check_response_basics(rra_resp)
        if rra_prev is None:
            rra_prev = rra_data
        else:
            # Adjust comparison paths because pval is stochastic
            deep_diff(
                rra_prev,
                rra_data,
                significant_digits=3,
                exclude_regex_paths=STOCHASTIC_PATHS + [f"{chem_id}_tip"],
            )


COMBOS = [
    ("chm_mrgn", 1, "chm_httr", 1),
    ("chm_mrgn", 2, "chm_httr", 1),
    ("chm_httr", 1, "chm_mrgn", 2),
    ("chm_mrgn", 1, "chm_httr", 2),  # fails to include httr, because mrgn ~= httr ?
    ("chm_mrgn", 1, "chm_ct", 2),  # pulls in something from neither
    ("chm_mrgn", 1, "chm_phch", 1),  # == nn_a
    ("chm_mrgn", 1, "chm_phch", 2),  # only gets 4 total?
]


@pytest.mark.parametrize("combo", COMBOS, ids=[str(i) for i in COMBOS])
def test_hybrid_sim(api_url, combo):
    """Tests that a 1:1 Morgan : PhysChem hybrid with ToxRef filter is a mixture of the
    two.  Similarities for Morgan are < 0.5, for PhysChem they're > 0.98, but should not
    just get all PhysChem because of this.
    """
    chem_id = "DTXCID30182"
    hits = 11
    hybrid_a, weight_a, hybrid_b, weight_b = combo
    nn_a = searchFP(chem_id, hybrid_a, max_hits=hits)
    nn_b = searchFP(chem_id, hybrid_b, max_hits=hits)
    nn_ab = searchFP(
        chem_id, f"{hybrid_a}_W{weight_a}_and_{hybrid_b}_W{weight_b}", max_hits=hits
    )
    nn_a = set(i["chem_id"] for i in nn_a)
    nn_b = set(i["chem_id"] for i in nn_b)
    nn_ab = set(i["chem_id"] for i in nn_ab)
    assert len(nn_a) == hits
    assert len(nn_b) == hits
    assert len(nn_ab) == hits
    # This is invalid, chem. X from neither non-hybrid list can be included in hybrid
    # assert len(nn_ab - nn_a - nn_b) == 0  # ab is a mix of a and b
    assert nn_ab != nn_a
    assert nn_ab != nn_b


HYBRIDS = "chm_httr", "chm_phch"


@pytest.mark.parametrize("hybrid", HYBRIDS)
def test_hybrid_download(api_url, hybrid):
    """Confirm jaccard_ column in top 100 download is not empty."""
    url = f"{api_url}/api/genra/v4/uiDownload/allNN"
    resp = requests.post(
        url,
        json={
            "chem_id": "DTXCID30182",
            # "fp": "chm_mrgn_W1_and_chm_phch_W1",
            "fp": f"chm_mrgn,{hybrid}",
            "fp_weight": "1,1",
            "sel_by": "tox_txrf",
        },
        headers={"Content-Type": "application/json", "Accept": "*/*"},
    )
    resp.raise_for_status()
    # use BytesIO to convert to file-like object
    dframe = pd.read_csv(io.BytesIO(resp.content))
    for name, data in dframe.items():
        if name.startswith("jaccard_"):
            # data[0] is a 1 for the target, so test data[1]
            assert (
                isinstance(data[1], float) and np.isfinite(data[1]) and data[1] != 0
            ), (name, data)
