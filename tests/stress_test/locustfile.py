import random

from locust import HttpUser, task
from tests.stress_test.defs import IDS

ENDPOINTS = {
    "Setup": {
        "path": "/genra-api/api/genra/v4/uiSetup/?chem_id={chem_id}",
    },
    "Radial": {
        "path": "/genra-api/api/genra/v4/uiRadialView/?chem_id={chem_id}&k0=10&"
        "fp=chm_mrgn&sel_by=tox_txrf&summarise=tox_txrf&sumrs_by=tox_fp&s0=0.1",
    },
    "FastNN": {
        "path": "/genra-api/api/genra/v4/uiFastNN/?fp=chm_mrgn%2Cbio_txct&k0=3&"
        "sel_by=tox_txrf&chem_id={chem_id}&summarise=tox_txrf&sumrs_by=tox_fp&"
        "s0=0.1&neg0=1&steps=3&pos0=1&engine=genrapred&graph_type=all_nhgbrs",
    },
    "PhysChem": {
        "path": "/genra-api/api/genra/v4/uiPhyschemPlot?chem_id={chem_id}&k0=10&"
        "s0=0.1&fp=chm_mrgn&sel_by=tox_txrf&ftype=html",
    },
    "Heatmap": {
        "path": "/genra-api/api/genra/v4/uiFingerPrintHeatChart?chem_id={chem_id}&"
        "k0=10&s0=0.1&fp=chm_mrgn&sel_by=tox_txrf",
    },
    "Assays": {
        "path": "/genra-api/api/genra/v4/uiAssayList/?chem_id={chem_id}&k0=10&s0=0.1&"
        "fp=chm_mrgn&sel_by=tox_txrf&summarise=tox_txrf&sumrs_by=tox_fp",
    },
    "GenReadAcross": {
        "path": "/genra-api/api/genra/v4/uiGenerateReadAcross/?chem_id={chem_id}&"
        "k0=10&s0=0.1&fp=chm_mrgn&summarise=tox_txrf&sel_by=tox_txrf&sumrs_by=tox_fp",
    },
    # Not templating this one because it's more complicated
    "RunReadAcross": {
        "path": "/genra-api/api/genra/v4/uiRunReadAcross/?chem_id=DTXCID30182&"
        "k0=10&s0=0.1&fp=chm_mrgn&summarise=tox_txrf&sel_by=tox_txrf&sumrs_by=tox_fp",
        "post": {
            "chem_id": "DTXCID30182",
            "k0": 10,
            "s0": 0.1,
            "fp": "chm_mrgn",
            "neg0": 1,
            "pos0": 1,
            "engine": "genrapred",
            "sel_by": "tox_txrf",
            "summarise": "tox_txrf",
            "sumrs_by": "tox_fp",
            "chem_inc": [
                {"chem_id": "DTXCID30182", "isChecked": True},
                {"chem_id": "DTXCID001771", "isChecked": True},
                {"chem_id": "DTXCID602360", "isChecked": True},
                {"chem_id": "DTXCID70716", "isChecked": True},
                {"chem_id": "DTXCID10465", "isChecked": True},
                {"chem_id": "DTXCID406081", "isChecked": True},
                {"chem_id": "DTXCID606", "isChecked": True},
                {"chem_id": "DTXCID60220", "isChecked": True},
                {"chem_id": "DTXCID402529", "isChecked": True},
                {"chem_id": "DTXCID501124", "isChecked": True},
                {"chem_id": "DTXCID3024495", "isChecked": True},
            ],
            "useWidth": False,
        },
    },
}

requested = set()


class GenraUser(HttpUser):
    @task
    def hello_world(self):
        self.client.get("/genra-api/version.txt")
        chem_id = random.choice(IDS)
        if chem_id not in requested:
            requested.add(chem_id)
            print(f"Requesting {chem_id}")
        for endpoint, data in ENDPOINTS.items():
            if not data.get("post"):
                self.client.get(data["path"].format(chem_id=chem_id), name=endpoint)
            else:
                self.client.post(data["path"], json=data["post"], name=endpoint)
