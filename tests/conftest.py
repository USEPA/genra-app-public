"""Define common fixtures here.

Brian Okken's 'Python Testing with Pytest' used as reference.
"""

import dataclasses
import json
import logging
import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote_plus

import pytest
import requests
from filelock import FileLock

from genraweb.lib.chem_id import ChemID
from genraweb.lib.db_connection import open_mongo_db
from genraweb.lib.fp.fpclass import FPGen
from tests.defs import FP_GEN_TESTS
from tests.lib.check_response import check_response_basics, skip_if_not_local_dev
from tests.lib.misc import deep_diff, process_calibration

logger = logging.getLogger("genra_test")
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
console.setFormatter(
    logging.Formatter("%(asctime)s: %(message)s", datefmt="%m%d-%H%M%S")
)
logger.addHandler(console)

# Check tests are running, search `COMPARISONS` for details.
COMPARISONS = []


@pytest.fixture(scope="session")
def get_env_var():
    """Get the environment variable.

    If variable DNE, return default if provided else raise an Exception.
    This uses "factory as fixture" pattern.
    """

    def _get_env_var(env_name, default=None):
        env_var = os.environ.get(env_name, default)
        if env_var is None:
            raise Exception("The environment variable %s is not defined" % env_name)
        return env_var.rstrip("/")

    return _get_env_var


@pytest.fixture(scope="session")
def api_url(get_env_var):
    # see also make_url, fixtures vs. functions getting a bit messy
    return get_env_var("GENRA_API_URL")


@pytest.fixture(scope="session")
def api_tolerance(get_env_var):
    return float(get_env_var("TOLERANCE", "0.0"))


@pytest.fixture(scope="session")
def fpcol_suffix(get_env_var):
    return get_env_var("GENRA_FPCOL_SUFFIX", "")


@pytest.fixture(scope="session")
def calibrate(get_env_var):
    return get_env_var("CALIBRATE", "No") in ("1", "Yes", "yes", "Y", "y")


def pytest_addoption(parser):
    parser.addoption(
        "--very-slow", action="store_true", help="run tests marked `very_slow`"
    )


def pytest_runtest_setup(item):
    if "very_slow" in item.keywords and not item.config.getoption("--very-slow"):
        pytest.skip("need --very-slow option to run this test")


@pytest.fixture(scope="session")
def app_context():
    from flask import Flask

    app = Flask(__name__)
    return app.app_context


def make_url(etp, endpoint):
    """Non-fixture URL calc. for endpoints"""
    # see also api_url()
    env_api_url = os.getenv("GENRA_API_URL")
    chem_id = quote_plus(etp.chem_id)
    chem_key = "chem_id"
    return (
        f"{env_api_url}/api/genra/{etp.api_version}/{endpoint}/?"
        f"{chem_key}={chem_id}&k0={etp.k0}&s0={etp.s0}&fp={etp.fp_id}"
        f"&sel_by={etp.sel_by}&summarise={etp.summarise}"
        f"&sumrs_by={etp.sumrs_by}&pos0={etp.min_pos}&neg0={etp.min_neg}{etp.extra}"
    )


def check_all_ids(etp, endpoint, response):
    """Check that calling the endpoint with alternate forms of ID gives the same
    result.
    """
    if "Run" in endpoint:
        return
    chem = ChemID.compounds_chem(etp.chem_id)
    etp_id = dataclasses.replace(etp)  # copy
    # this is intended to check the response we already got (response) against the
    # response for all other IDs.
    reference = response
    for id_type in ChemID.ordered_fields:
        if chem.get(id_type) and chem[id_type] != etp.chem_id or reference is None:
            etp_id.chem_id = chem[id_type]
            url = make_url(etp_id, endpoint)
            logger.info(url)
            logger.info(f"{etp.chem_id}:{etp_id.chem_id}")
            if hasattr(etp, "post_data"):  # RRA or download
                etp.post_data["chem_inc"][0].update({"chem_id": chem[id_type]})
                resp = requests.post(
                    url,  # with lots of ignored params
                    data=json.dumps(etp.post_data),
                    headers={"Content-Type": "application/json", "Accept": "*/*"},
                )
            else:
                resp = requests.get(url)
            data = check_response_basics(resp)
            if reference:
                deep_diff(reference, data, what=f"{etp.chem_id}:{etp_id.chem_id}")
                logger.info(len(str(data)))  # make sure we're comparing something
            else:
                reference = data


@pytest.fixture(scope="session")
def run_expected_test(calibrate):
    """Return a function to run an expected values comparison test.
    https://stackoverflow.com/a/45926164/1072212 making it a fixture allows fixture
    access without having to pass in from the test itself.
    """

    def _run_expected_test(
        test_src,
        endpoint,
        etp,
    ):
        """Test an endpoint against expected values.

        Args:
        ----
            test_src (str): The __file__ special var. in the test module, used to find
                expected data.
            endpoint (str): URL name of endpoint, uiRadialVue etc.
            etp (ExpectedTestParams): params for test

        Returns:
        -------
            dict|list: data returned by endpoint for further tests
        """
        if etp.resp is None:
            url = make_url(etp, endpoint)
            logger.info(url)
            resp = requests.get(url)
        else:
            resp = etp.resp

        data = check_response_basics(resp)
        if isinstance(data, list):
            # So we can add "_changelog" key.
            data = {"_result": data}

        if etp.all_ids:
            check_all_ids(etp, endpoint, data)

        def parse_constant(x):
            raise Exception("Found %s in JSON response" % x)

        json.loads(resp.content, parse_constant=parse_constant)  # check for NaNs

        fp_key = etp.__str__()
        expected_path = Path(test_src).with_name(
            f"{endpoint}_{etp.api_version}_expected.json"
        )

        if calibrate and etp.test_expected:
            process_calibration(fp_key, data, expected_path)
        elif etp.test_expected and not os.environ.get("GENRA_TEST_IGNORE_EXPECTED"):
            if not expected_path.exists():
                raise FileNotFoundError(
                    "CALIBRATE NEEDED no file found for " f"{fp_key} in {expected_path}"
                )
            with expected_path.open() as f:
                try:
                    expected = json.load(f)[fp_key]
                except KeyError:
                    raise KeyError(
                        "CALIBRATE NEEDED no data found for "
                        f"{fp_key} in {expected_path}"
                    )
                deep_diff(
                    expected, data, **({"significant_digits": 5} | etp.deep_diff_kwargs)
                )
            # Uncomment this next line just to verify tests are running, run with
            # something like -vv -k test_fp_types_results (no parallelism).
            # COMPARISONS.append((len(str(expected)), len(str(data))))

        if (
            endpoint in ("uiRadialVue", "uiFingerPrintHeatChart")
            and etp.minn is not None
        ):
            result_list = data["data"]
            if endpoint == "uiRadialVue":
                result_list = data["result"]
            assert etp.minn <= len(result_list) - 1 <= etp.maxn

        write_karate_test(test_src, endpoint, etp, data)

        return data["_result"] if "_result" in data else data

    return _run_expected_test


def write_karate_test(test_src, endpoint, etp, data):
    """Write karate tests for external ~monitoring test runnning."""
    # Get url path without host.
    url = "/" + make_url(etp, endpoint).split("/", maxsplit=3)[3]
    path = Path("karate_tests")
    filename = "slow_tests" if "no_filter" in url else endpoint
    path /= filename + ".feature"
    method = "POST" if hasattr(etp, "post_data") else "GET"
    # Exclusive access for running in parallel.
    with FileLock(path.with_suffix(path.suffix + ".lock")).acquire():
        if not path.exists():
            timestamp = time.asctime()
            path.write_text(
                f"Feature: Test GenRA {filename} functions.\n# Generated {timestamp}\n"
            )

        with path.open("a") as out:
            out.write(
                f"\n  Scenario: Testing the {method} method {endpoint} with {etp}\n"
            )
            if "no_filter" in url:
                # karate's 60 sec. default borderline for no_filter
                out.write("    * configure readTimeout = 180000\n")
            if method == "POST":
                out.write('    * text body =\n"""\n')
                out.write(json.dumps(etp.post_data))
                out.write('\n"""\n    * request body\n')
            out.write(
                f"    Given url genra + '{url}'\n"
                "    And header Content-Type = 'application/json; charset=utf-8'\n"
                f"    When method {method}"
            )
            out.write("\n    Then status 200\n")
            response = etp.resp.json() if method == "POST" else data
            for key, value in response.items():
                if isinstance(value, list):
                    out.write(f"    And assert response.{key}.length == {len(value)}\n")
                elif isinstance(value, dict):
                    out.write(
                        f"    And assert Object.keys(response.{key}).length "
                        f"== {len(value)}\n"
                    )
                elif isinstance(value, str):
                    out.write(f"    And match response.{key} == {value!r}\n")


@pytest.fixture(scope="session")
def run_fp_generation_test(api_url):
    """Return a function to run a fingerprint generation test.
    https://stackoverflow.com/a/45926164/1072212 making it a fixture allows fixture
    access without having to pass in from the test itself.
    """
    skip_if_not_local_dev()

    def _run_fp_generation_test(fp_id, from_path):
        """Test generation of a particular fingerprint against reference results.

        Args:
        ----
            fp_id (str): Fingerprint ID
        """
        from genraweb.resources import DB  # seems premature to import sooner

        fp = FPGen.FPClass[fp_id]  # the class lets us get output_collection
        output_collection = fp.output_collection_name()
        if not output_collection.endswith("_test"):
            output_collection += "_test"
        # but we need an instance later, for delete_fps()
        fp = fp(DB, output_collection)

        test = FP_GEN_TESTS[fp_id]

        # reference database collection, collection name
        DBRef = open_mongo_db(test.ref_db)
        # equal if open_mongo_db() falls back to default

        # list of chems to test, delete existing
        with (Path(from_path) / "chemicals_ids.json").open() as chem_ids:
            chem_ids = json.load(chem_ids)
        if hasattr(fp, "cell"):  # HTPP variants
            chem_ids = chem_ids[fp.cell]
        # Allow for multiple FPs in file, support legacy single FP
        data = chem_ids[fp_id] if fp_id in chem_ids else chem_ids
        chem_ids = data.get("cids", []) + data.get("sids", [])
        # chem_ids = chem_ids[:5]  # for debugging run_fp_generation_test (this code)
        chem_list = "%2C".join(chem_ids)
        fp.delete_fps(chem_ids=chem_ids)  # do this to give it a chance to fail, then
        fp.delete_fps("ALL")

        req = (
            f"{api_url}/api/genra/v3/genFP/?fp={fp_id}&"
            f"collection_name={output_collection}&chem_ids={chem_list}"
        )
        resp = requests.get(req)
        check_response_basics(resp)

        for chem_id in chem_ids:
            print(fp_id, chem_id)
            # can't think of a case where we have reference FP data with no SID/CID
            field = "dsstox_cid" if chem_id.startswith("DTXCID") else "dsstox_sid"
            generated = DB[output_collection].find_one(
                {field: chem_id}, test.projection
            )
            assert generated, chem_id
            if "htpp" in fp_id:
                ref_query = {"dtxsid": generated["dtxsid"]}  # unfortunate variation
            else:
                ref_query = {field: chem_id}
            ref_query.update(test.filter or {})
            reference = list(
                DBRef[test.ref_collection].find(ref_query, test.projection)
            )
            assert len(reference) == 1, (chem_id, ref_query)
            reference = reference[0]
            if test.transform:
                reference = test.transform(reference)
            # to go with the print() above, show we're not comapring [] to []
            print(len(str(reference)), len(str(generated)))

            # ordering differences in FP "bit lists" don't matter
            deep_diff(reference, generated, what=(fp_id, chem_id), ignore_order=True)

    return _run_fp_generation_test


def pytest_sessionstart(session):
    """Clear the karate_tests folder."""
    # https://github.com/pytest-dev/pytest-xdist/issues/271
    if getattr(session.config, "workerinput", None) is not None:
        # In a worker, not top level session.
        return
    shutil.rmtree("karate_tests", ignore_errors=True)
    # May have ignored a permissions error in rmtree(), so could exist still.
    Path("karate_tests").mkdir(exist_ok=True)


def pytest_sessionfinish(session, exitstatus):
    """Check tests are running, search `COMPARISONS` for details."""
    if COMPARISONS:
        logger.info("\n" + "\n".join(f"{n} {i}" for n, i in enumerate(COMPARISONS)))
