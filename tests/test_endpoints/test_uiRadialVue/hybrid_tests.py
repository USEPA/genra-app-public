"""
hybrid_tests.py - test behavior of FP NN hybrid selection code

This test isn't intended to be run routinely, but just to confirm expected beahvior in
hybrid NN calc.  The test runs a sliding weight for one FP from 0 to 1, and another
from 1 to 0, and confirms the expected transition between the two.  The test is repeated
with a third FP present at an intermediate weight.

Terry N. Brown Brown.TerryN@epa.gov Wed 07 Jul 2021 03:06:20 PM UTC
"""

import requests
from deepdiff import DeepDiff

url = (
    "http://genra_api:5000/api/genra/v4/uiRadialView/?chem_cid=DTXCID30182&"
    "k0=10&s0=0.1&sel_by=tox_txrf&fp="
)


def chems_in(fp):
    return {i["dtxcid"] for i in requests.get(f"{url}{fp}").json()["result"]}


for half in "", "tox_txrf_W0.5_and_":
    for fp0id, fp1id in ("chm_mrgn", "chm_httr"), ("chm_mrgn", "bio_txct"):
        fp0 = chems_in(fp0id)
        fp1 = chems_in(fp1id)

        for step in range(11):
            wght0 = step / 10
            wght1 = 1 - wght0
            chems = chems_in(f"{half}{fp0id}_W{wght0}_and_{fp1id}_W{wght1}")
            print(f"\n{half} {wght0}:{wght1}")
            print(fp0id)
            print(DeepDiff(fp0, chems).pretty())
            print(fp1id)
            print(DeepDiff(fp1, chems).pretty())
