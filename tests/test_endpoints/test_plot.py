"""Test phys. chem. plot generation."""

from genraweb.lib.mongofp_NN import searchFP
from genraweb.lib.state import GenRAState
from genraweb.routes.v4.uiPhyschemPlot import plot_data

TEST_REQUEST = {
    "chem_id": "DTXCID30182",
    "k0": 10,
    "s0": 0.1,
    "fp": "chm_mrgn",
    "sel_by": "tox_txrf",
}


def test_physchem_plot_data() -> None:
    """Test phys. chem. plot generation."""
    plot_df = plot_data(GenRAState(TEST_REQUEST))
    # GEN-1158 normalization was wrong, so check normalized order == value order.
    # Ties are ok here, we're not testing ordering of chem. IDs
    for name, group in plot_df.groupby("prop_id"):
        group.sort_values("prop_val", inplace=True)
        assert list(group["prop_norm"]) == list(sorted(group["prop_norm"])), group
    assert plot_df["prop_norm"].min() == 0
    assert plot_df["prop_norm"].max() == 1

    # GEN-1204 key length / ordering off
    assert sum(plot_df["prop_id"] == "mass") == TEST_REQUEST["k0"] + 1
    gst = type("Values", (), TEST_REQUEST)
    neighbors = searchFP(
        gst.chem_id, fp=gst.fp, sel_by=gst.sel_by, s0=gst.s0, max_hits=gst.k0 + 1
    )
    assert [i["chem_id"] for i in neighbors] == plot_df[plot_df["prop_id"] == "mass"][
        "chem_id"
    ].to_list()
