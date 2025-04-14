"""test_deployment.py - tests for deployment / performance etc."""
import os
import re
import threading
import time
from pathlib import Path

import pytest
import requests

from genraweb.task_utils import batches
from tests.lib.check_response import check_response_basics


def test_vars_in_template() -> None:
    """Test that all env. vars. defined in `.env` are defined in `template.env`"""
    template = Path("template.env")
    assert template.exists()  # or test setup is messed up
    settings = Path(".env")
    if not settings.exists():
        # user doesn't have to use .env
        pytest.skip("Didn't find .env")
    var_pattern = re.compile(r"^(\w+)=", re.ASCII)
    settings_vars = set(
        var_pattern.match(line)[1]
        for line in settings.open()
        if var_pattern.match(line)
        and not var_pattern.match(line)[1].startswith("GENRA_DB_")
    )
    assert len(settings_vars) > 3, "Nothing in .env?"
    # Variables may be defined but commented out in template.env, so just
    # scan the text for the variable names.
    template_vars = template.read_text()
    extras = [i for i in settings_vars if not re.search(f"\\b{i}\\b", template_vars)]
    print("Extra vars in .env not seen in template.env: ")
    print(extras)
    assert not extras, "Found vars. in .env not seen in template.env"


def test_build_matches_req() -> None:
    """Unpinning / re-pinning reqs. requires copying /requirements.txt.installed.

    From the container to the repo., check that this has been done.
    """
    repo = Path("requirements.txt").read_text()
    live = Path("/requirements.txt.installed").read_text()
    assert repo == live


@pytest.mark.slow_api
@pytest.mark.no_smoke  # Using timing to test multiprocessing not foolproof.
def test_multiprocess(api_url):
    """Test that multiple ~simultaneous requests are processed in parallel.
    Should fail when just using flask directly, but pass with Apache
    multiprocessing / WSGI deployment.
    But turns out Flask is multi-threaded by default, so only fails if you
    disable that first.  Can still be used to test parallel request handling.
    """
    unicorn = os.environ.get("GUNICORN_CMD_ARGS", "")
    if re.search(r"workers.1(\D|$)", unicorn) and re.search(
        r"threads.1(\D|$)", unicorn
    ):
        # matches "=1" and " 1" but not "=10" or " 10"
        pytest.skip("No multiprocessing when worker and threads == 1")

    def get_result(result):
        """Get a result, puts start_time, end_time in result"""
        start = time.time()
        requests.get(
            api_url + "/api/genra/v4/uiRadialView/?chem_id=DTXCID30182&"
            "k0=12&s0=0.1&fp=chm_mrgn&sel_by=tox_txrf"
        )
        result.extend([start, time.time()])

    threads = []
    results = []
    # clock starts running for all threads ~immediately / simultaneously
    for i in range(5):
        result = []  # separate list private to each thread
        results.append(result)
        thread = threading.Thread(target=get_result, args=(result,))
        threads.append(thread)
        thread.start()

    # probably a better way, but wait for Python 3
    while any(i.is_alive() for i in threads):
        time.sleep(1)

    # Assume last thread takes no more than 150% time of first thread.
    # If they're not parallel, last will be about 5 x first.  This test could
    # fail when it shouldn't, if load / DB response time makes the final call
    # really slow.  Or pass when it shouldn't, if the first call is really
    # slow.
    assert results[-1][1] - results[-1][0] < 1.5 * (results[0][1] - results[0][0])


def test_fp_gen_availbility(api_url):
    """Test that depending on the deployment type (as identified by
    GENRA_DEPLOYMENT_TYPE), the availbility of FP generation material
    is hidden (or not). GEN-392.
    """
    resp = requests.get(f"{api_url}/api/genra/v3/genFP/?fp=dummy_fp")

    genra_deployment_type = os.environ.get("GENRA_DEPLOYMENT_TYPE")

    if genra_deployment_type == "LOCAL_DEV":
        response_dict = check_response_basics(resp)
        assert "error" in response_dict
        assert response_dict["error"] == "Unsupported fingerprint"
    else:
        assert resp.status_code == 404


def test_batches():
    """Test the batches function"""
    twelve = range(12)
    assert len(list(batches(twelve, batch_size=5))) == 3

    twelve = list(range(12))
    assert len(list(batches(twelve, batch_size=5))) == 3

    twelve = iter(range(12))
    assert len(list(batches(twelve, batch_size=5))) == 3

    twelve = iter(range(12))
    assert len(list(batches(twelve, batch_size=5, max_batches=2))) == 2


def test_version_txt(api_url):
    """Test /version.txt"""
    resp = requests.get(f"{api_url}/version.txt")
    print(f"{api_url}/version.txt")
    resp.raise_for_status()
    print(resp.text)
    assert resp.text[0].isdigit()
