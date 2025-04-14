import random

from locust import HttpUser, task
from tests.stress_test.defs import IDS

ENDPOINTS = {
    "Setup": {"path": "/genra"},
    "Nuxt01": {"path": "/genra/_nuxt/09815ca.js"},
    "Nuxt02": {"path": "/genra/_nuxt/255818b.js"},
    "Nuxt03": {"path": "/genra/_nuxt/35a5f25.js"},
    "Nuxt04": {"path": "/genra/_nuxt/bdd0788.js"},
    "Nuxt05": {"path": "/genra/_nuxt/css/4f7be52.css"},
    "Nuxt06": {"path": "/genra/_nuxt/css/f4d3e35.css"},
    "Nuxt07": {"path": "/genra/_nuxt/d2ceab0.js"},
    "Nuxt08": {"path": "/genra/_nuxt/img/epa_logo.57f82b9.png"},
}


class GenraUser(HttpUser):
    @task
    def hello_world(self):
        chem_id = random.choice(IDS)
        for endpoint, data in ENDPOINTS.items():
            if not data.get("post"):
                self.client.get(data["path"].format(chem_id=chem_id), name=endpoint)
            else:
                self.client.post(data["path"], json=data["post"], name=endpoint)
