"""Shared definitions for tests"""
import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

STOCHASTIC_PATHS = [
    r"\['predClass'\]",
    r"\['(AUC)?pval'\]",
    r"\['ACT'\]",
    r"\['isPrediction'\]",
    r"\['_changelog'\]",  # for convenience
]


@dataclass
class ExpectedTestParams:
    """chem_id+options for tests against ui* endpoints"""

    fp_id: str  # ID of fingerprint chms_fp etc.
    chem_id: str  # ID of chemical
    k0: int  # number of neighbors to fetch
    s0: float  # minimum similarity to accept
    minn: int = None  # minimum neighbors to expect in response (not -min / +min)
    maxn: int = None  # maximum neighbors to expect in response (not -min / +min)
    endpoints: list = None  # only use for these endpoints
    # List to exclude, will override remove any included in `endpoints` (override).
    # Used mainly for uiFastNN, for cases such as custom SMILES or chemical FP+no_filter
    exclude_endpoints: list = None
    min_pos: int = 1  # minimum obs. in analogs to make a positive effect prediction
    min_neg: int = 1  # minimum obs. in analogs to make a no effect prediction
    sel_by: str = "tox_txrf"  # filter applied to results, can be "no_filter"
    summarise: str = "tox_txrf"  # database to predict/aggregate
    sumrs_by: str = "tox_fp"  # data type to predict/aggregate
    engine: str = "genrapred"  # prediction engine, "genrapred" or "genrapy"
    # special case, confirm, in uiGenerateReadAcross test, that there is no data for
    # this target, to confirm it's a valid test of the no data case.  See
    # test_fp_types_results_run_read_across.py for details.
    no_data: bool = False
    # special case, check a filtered ep_subset has the same results. See
    # test_fp_types_results_run_read_across.py for details.
    ep_subset: str = None
    # the case where every other chemical in neighborhood (not including target)
    # is deselected from prediction consideration; i.e. `isChecked: False`).
    # Simulate testing of users' ability to customize neighborhood selection.
    alternate_cols: bool = False
    # special case - check all IDs for chem. return same answer
    all_ids: bool = False

    # more general items not expected to be specified in list of tests

    extra: str = ""  # extra URL parts
    # a response object to use instead of GETing, used to pass in POST response from RRA
    resp: object = None
    test_expected: bool = True  # whether to test against expected results
    api_version: str = "v4"  # API version to test, inserted into URL
    deep_diff_kwargs: dict = field(
        default_factory=lambda: dict(exclude_regex_paths=STOCHASTIC_PATHS)
    )  # args to pass to DeepDiff

    def __str__(self):
        """How params are displayed by pytest AND stored in <expected>.json"""
        keys = [
            "fp_id",
            "chem_id",
            "k0",
            "s0",
            "sel_by",
            "summarise",
            "sumrs_by",
            "min_pos",
            "min_neg",
        ]
        excludes = ["deep_diff_kwargs", "resp", "exclude_endpoints"]
        core = ":".join(str(getattr(self, i, "NA")) for i in keys)
        defaults = ExpectedTestParams("", "", 0, 0)
        # Add settings not covered by keys if not default (alternate_cols etc. etc.)
        for k, v in self.__dict__.items():
            if (
                k in keys
                or k in excludes
                or k.startswith("_")
                or not hasattr(defaults, k)
                or v == getattr(defaults, k)
            ):
                continue
            clean = "".join(i for i in str(v) if i in "-_," or i.isalnum())
            core += f":{k}:{clean}"

        return core


@dataclass
class FPGenerationTest:
    """fp_id+params for tests of FP generation"""

    # using a dict (below) for now, but could eliminate individual tests with
    # fp_id: str  # Fingerpring ID, chms_fp etc.
    ref_db: str  # database containing reference results, PB_V4, RES, etc.
    ref_collection: str  # collection in ref_db with results
    projection: dict  # MongoDB document keys to compare
    filter: dict = None  # MongoDB filter
    # optional transformation of reference before comparison
    transform: Callable[[dict], dict] = None


htpp_projection = {"_id": 0, "fp": 1, "stype": 1, "dtxsid": 1}


def htpp_transformer_factory(cell_type):
    """Return a function to extract single cell type data from reference DB"""

    def trans(d, cell_type=cell_type):
        d = deepcopy(d)
        d["fp"] = {k: v for k, v in d["fp"].items() if k.startswith(cell_type)}
        return d

    return trans


FP_GEN_TESTS = {
    "chm_httr": FPGenerationTest(
        ref_db="RES_V5",
        ref_collection="chms_fp",
        projection={"httr": 1, "mrgn": 1, "_id": 0},
    ),
    # chm_mrgn covered by chm_httr
    "chm_ct": FPGenerationTest(
        ref_db="RES_V4",
        ref_collection="chemotypes",
        projection={"chemotypes.ds": 1, "_id": 0},
    ),
    "chm_aim": FPGenerationTest(
        ref_db="DEV",
        ref_collection="aim_fp_reference",
        projection={"chemotypes.ds": 1, "_id": 0},
    ),
    "bio_txct": FPGenerationTest(
        ref_db="RES_V5", ref_collection="toxcast_fp", projection={"fpnd": 1, "_id": 0}
    ),
    # "bio_htpp_MCF7": FPGenerationTest(
    #     ref_db="RES_V5",
    #     ref_collection="htpp_fp_1",
    #     projection=htpp_projection,
    #     transform=htpp_transformer_factory("MCF7"),
    # ),
    # "bio_htpp_U2OS": FPGenerationTest(
    #     ref_db="RES_V5",
    #     ref_collection="htpp_fp_1",
    #     projection=htpp_projection,
    #     transform=htpp_transformer_factory("U2OS"),
    # ),
    "tox_txrf": FPGenerationTest(
        ref_db="RES_V5",
        ref_collection="toxref_tr_fp",
        projection={
            # would like to check mg/kg/wk -> mg/kg/day but all fail with this
            # "tox_q": 1,
            "tox_fp1": 1,
            "tox_fp2": 1,
            "_id": 0,
        },
    ),
}


def FP_types(endpoint):
    """Function rather than constant because it depends on DB and endpoint being used.

    Can't use fixtures with pytest.mark.parametrize().
    """
    neighbor_ep = ["uiRadialView", "uiFingerPrintHeatChart"]
    # inputs for pytest.mark.parametrize are iterables of iterables
    EP = ExpectedTestParams
    types = [
        # fp_id, chem_id, k0, s0, minn, maxn, endpoints
        # FOOF, not a subject for bioassays
        EP("chm_mrgn", "DTXCID90150942", 15, 0.1),
        # low s0, neighbors limited by k0
        EP("chm_mrgn", "DTXCID30182", 15, 0.1, minn=15, maxn=15, all_ids=True),
        # low s0, neighbors limited by k0
        EP("chm_mrgn", "DTXCID30182", 2, 0.1, minn=2, maxn=2, endpoints=neighbor_ep),
        # high s0 limits neighbors
        EP("chm_mrgn", "DTXCID30182", 10, 0.3, minn=3, maxn=3, endpoints=neighbor_ep),
        # unless k0 even more restrictive
        EP("chm_mrgn", "DTXCID30182", 1, 0.3, minn=1, maxn=1, endpoints=neighbor_ep),
        EP("chm_httr", "DTXCID30182", 5, 0.2),
        # DO NOT remove the only use of `ep_subset` here, replace it elsewhere if
        # needed.  Checks the subset of results matching "survival early" and "heart"
        # for proper interaction with min_pos/neg in RRA.
        EP(
            "chm_ct",
            "DTXCID8047",
            5,
            0.2,
            min_pos=3,
            min_neg=3,
            ep_subset="ear",
            # True / False for this is non-deterministic
            deep_diff_kwargs={"exclude_regex_paths": STOCHASTIC_PATHS},
            exclude_endpoints=['uiRunReadAcross'],   # FIXME stochastically flaky
        ),
        # chlorine to test target reamains first when sim. == 1.0 (Iodine)
        EP("chm_ct", "DTXCID50273", 5, 0.2),
        EP("bio_txct", "DTXCID50485", 5, 0.2),
        EP("bio_tx21", "DTXCID50485", 5, 0.2),
        EP("tox_txrf", "DTXCID704235", 5, 0.2),
        # EP(
        #     "bio_htpp_U2OS",
        #     "DTXCID9031147",
        #     5,
        #     0.001,
        #     deep_diff_kwargs={
        #         "exclude_regex_paths": STOCHASTIC_PATHS,
        #         "ignore_order": True,
        #     },
        # ),
        # user custom hybrid
        EP(
            "chm_mrgn,chm_httr",
            "DTXCID30182",
            10,
            0.1,
            extra="&fp_weight=1,1",
        ),
        EP(
            "bio_txct,tox_txrf,chm_ct",
            "DTXCID30182",
            10,
            0.1,
            extra="&fp_weight=3,2,5",
        ),
        EP(
            "chm_mrgn,bio_txct",
            "DTXCID30182",
            15,
            0.1,
            extra="&fp_weight=4,10",
        ),
        # Thalidomide - was failing because of code issues with chems. with no
        # toxref data.  If this ceases to be a no data case, pick something else.
        EP(
            "chm_mrgn",
            "DTXCID402524",
            5,
            0.2,
            endpoints=["uiRunReadAcross"],
            no_data=True,
        ),
        # regular test case for no filter
        EP(
            "bio_txct", "DTXCID40662", 9, 0.1, endpoints=neighbor_ep, sel_by="no_filter"
        ),
        # whole neighborhood (incl. target) not having toxref data for no_filter
        EP(
            "chm_mrgn",
            "DTXCID501455110",
            10,
            0.1,
            sel_by="no_filter",
            exclude_endpoints=["uiFastNN"],
        ),
        # A case that failed in the wild, although would have had coverage if not for a
        # test code bug elsewhere, i.e. somewhat redundant.
        EP(
            "chm_mrgn",
            "DTXCID30182",
            10,
            0.1,
            sel_by="no_filter",
            endpoints=["uiRunReadAcross"],
        ),
        # customize neighborhood; simulate user selection of chemicals (columns)
        # on last panel by selecting every other column (starting with target)
        EP("chm_ct", "DTXCID401478006", 12, 0.1, alternate_cols=True),
        # a SID only chem.
        EP(
            "bio_txct",
            "DTXSID0034695",
            10,
            0.1,
        ),
        # a SMILES only chem with genrapy
        EP(
            "chm_httr",
            "OC(C)COC(CO)CO",
            10,
            0.1,
            engine="genrapy",
            exclude_endpoints=["uiFastNN"],
        ),
        # a SMILES only chem on custom hybrid
        EP(
            "chm_mrgn,chm_ct",
            "OC(C)COC(CO)CO",
            10,
            0.1,
            extra="&fp_weight=1,1",
            exclude_endpoints=["uiFastNN"],
        ),
        # a chem with no NN unless you use the no_filter filter
        EP(
            "bio_htpp_MCF7",
            "DTXCID70151654",
            10,
            0.1,
            sel_by="tox_txrf",  # this test tests that API switches this as needed
            endpoints=["uiRadialView"],
        ),
        # dosage - toxref FP
        EP(
            "tox_txrf",
            "DTXCID606",
            5,
            0.1,
            sel_by="tox_txrf",
            summarise="tox_txrf",
            sumrs_by="tox_fp_dosage",
            engine="genrapy",
        ),
        # dosage - unweighted neighbor
        EP(
            "bio_txct",
            "DTXCID30182",
            5,
            0.1,
            sel_by="tox_txrf",
            summarise="tox_txrf",
            sumrs_by="tox_fp_dosage",
            engine="genrapy",
        ),
        # dosage - custom SMILES
        EP(
            "chm_ct",
            # apparently PFAS-like chemical
            "C(C(C(=CC(F)(F)C(F)(F)C(F)(F)F)[N+]([O-])=O)O)O",
            10,
            0.1,
            sel_by="tox_txrf",
            summarise="tox_txrf",
            sumrs_by="tox_fp_dosage",
            exclude_endpoints=["uiFastNN"],
            engine="genrapy",
        ),
        # toxcast predictions
        # target chem with no toxcast data, genrapred
        EP(
            "chm_ct",
            "DTXCID00408880",
            8,
            0.1,
            sel_by="bio_txct",
            summarise="bio_txct",
            sumrs_by="bio_fp",
            engine="genrapred",
        ),
        # target chem with toxcast data, genrapy
        EP(
            "chm_httr",
            "DTXCID606",
            10,
            0.1,
            sel_by="bio_txct",
            summarise="bio_txct",
            sumrs_by="bio_fp",
            engine="genrapy",
        ),
        # uiFastNN seen returning "DTXCID20353" instead of expected dict in `nodes`
        # for this case.
        EP(
            "chm_mrgn,chm_ct",
            "DTXCID404665",  # Butnane
            3,
            0.1,
            endpoints=["uiFastNN"],
            extra="&steps=3",
        ),
        # multi-target test
        EP(
            "chm_mrgn",
            "DTXCID406081,tert-Butylhydroquinone,DTXSID3020465,"
            "120-32-1,OC1=CC=C(O)C=C1",
            15,
            0.1,
            exclude_endpoints=["precalc"],
            extra="&flags=multitarget",
        ),
        # user-nn test
        EP(
            "chm_mrgn",
            "DTXCID10714,DTXCID9013664,DTXCID902370,DTXCID204523",
            15,
            0.1,
            exclude_endpoints=["precalc"],
            extra="&flags=usernn",
        ),
        # hybrid (genrapy) continuous
        EP(
            "chm_mrgn,bio_txct",
            "DTXCID603235",
            15,
            0.1,
            sel_by="tox_txrf",
            summarise="tox_txrf",
            sumrs_by="tox_fp_dosage",
            engine="genrapy",
            extra="&fp_weight=3,1",
        ),
        # hybrid (genrapy) binary; Sodium erythorbate (DTXCID90570)
        # Predicting toxcast because it's a pretty large readacross table
        EP(
            "chm_aim,chm_httr,chm_mrgn",
            "DTXCID90570",
            15,
            0.1,
            sel_by="bio_txct",
            summarise="bio_txct",
            sumrs_by="bio_fp",
            engine="genrapy",
            extra="&fp_weight=1,1,3",
        ),
    ]

    types = [i for i in types if i.endpoints is None or endpoint in i.endpoints]
    types = [
        i
        for i in types
        if i.exclude_endpoints is None or endpoint not in i.exclude_endpoints
    ]

    if os.environ.get("GENRA_NEW_TOXREF_DB") == "Y":
        types = [i for i in types if i.fp_id != "bio_tx21"]

    return types


# constant definitions

EQUIVALENT_SETS = [
    [
        "chm_httr",
        "chm_mrgn_W0_and_chm_httr_W3",
        "chm_httr_W8_and_chm_mrgn_W0_and_bio_txct_W0.0",
    ],
    [
        "chm_ct_W1_and_bio_txct_W1",
        "bio_txct_W3.14_and_tox_txrf_W0.0_and_chm_ct_W3.14",
        "chm_httr_W0_and_chm_mrgn_W0_and_chm_ct_W0.5_and_bio_txct_W0.5",
    ],
]

EQUIVALENT_SETS_IDS = ["==".join(fp_keys) for fp_keys in EQUIVALENT_SETS]
