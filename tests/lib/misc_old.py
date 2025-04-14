"""Miscellaneous library tools"""
import json
import logging
import random
from pathlib import Path

import requests
from deepdiff import DeepDiff
from filelock import FileLock

from tests.lib.check_response import check_response_basics

logger = logging.getLogger("genra_top")


def check_all_keys_exist(data, keys):
    for key in keys:
        assert key in data


def sample_data(data, randomize=True, size=5):
    """Helper for printing; given a big dictionary (like 500+ assay list),
    deletes key-value pairs in place such that the dictionary size is reduced
    to `size`. In other words, takes a subset in place."""
    assert size > 0
    keys = list(data.keys())
    if randomize:
        random.shuffle(keys)

    selected_keys = keys[0:size]
    for key in keys:
        if key not in selected_keys:
            del data[key]
    return data


def print_data(data):
    """prints dictionary as pretty-fied JSON"""
    logger.info(json.dumps(data, indent=4))


def process_calibration(fp_type, data, name, first=False):
    """Write "canonical" expected data format, so git diff is useful.

    For a given test_fp_types_results_* test, this is called once for each FP
    type, so clear the existing data the first time (first == True) then just
    load, add, and save on subsequent calls.

    Args:
        fp_type (str): name of FP type
        data (dict): expected data
        name (str): path to file for expected data
        first (bool): first FP in new calibration, wipe old data
    """
    with FileLock(name.with_suffix(name.suffix + ".lock")).acquire():
        if Path(name).exists():
            expected = json.load(open(name))
        else:
            expected = {}
        expected[fp_type] = data
        with open(name, "w") as expected_file:
            json.dump(expected, expected_file, indent=4, sort_keys=True)


def deep_diff(expected, result, *, what=None, **deep_diff_kwargs):
    """Compare expected and actual results"""

    assert expected
    assert result

    diff = DeepDiff(expected, result, **deep_diff_kwargs)
    if diff:
        if what is not None:
            print(f"Failed on: {what}")
        print(diff.pretty())
        print(f"{deep_diff_kwargs=}")
        assert expected == result


def clear_cache(api_url):
    """Clears the GenRARedisLRU cache via endpoint and returns its response data"""
    req = api_url + "/api/genra/v3/uiClearCache"
    resp = requests.get(req)
    data = check_response_basics(resp)
    assert "keys" in data
    assert "keys_cleared" in data
    return data


def check_keys_exist(data, keys):
    """Given a dictionary, checks all keys exist"""
    absent = []
    for key in keys:
        if key not in data:
            absent.append(key)
    assert len(absent) == 0, f"keys missing: {absent}"


def is_primitive(elem):
    """Convenience method to check if `elem` is primitive"""
    return type(elem) in (int, float, bool, str) or elem is None


def check_dict_structure(data, structure, exact_match=True):
    """Convenience method. Checks that a Python dictionary `data` follows
    the given `structure`. A structure is a list of structure_key. A structure key
    is one of:
        - string => checks that key exists in `data`
        - dict with a single key-value pair => first checks key exist in `data` and:
          - if value is primitive, check equality in values
          - if value is a list therefore another structure, a recursive
            case where we are checking the structure of a dict in a dict,
            specifically checking structure of `data[<key>]`

    Args:
        data (dict): data to check dictionary structure
        structure (list): see above
        exact_match (bool): if True, keys specificied in `structure`
            will raise an assertion error
    """
    assert isinstance(data, dict)
    checked_keys = []
    for key in structure:
        if isinstance(key, str):
            # case: only check if key exists
            assert key in data, f"didn't find {key} in {data}"
        else:
            assert isinstance(key, dict)
            assert len(key.keys()) == 1
            key, val = list(key.items())[0]
            # first check if key exists
            assert key in data, f"{key} not in {data}"
            if is_primitive(val):
                # case: check same values
                assert data[key] == val, f"expected {val}, got {data[key]}"
            else:
                # case: nested dictionary
                assert isinstance(val, list)
                check_dict_structure(data[key], val, exact_match)
        checked_keys.append(key)
    if exact_match:
        unexpected_keys = set(data.keys()) - set(checked_keys)
        assert (
            len(unexpected_keys) == 0
        ), f"Unexpectedly got {unexpected_keys} in {data}"


def check_dict_structure_bool(data, structure, exact_match=True):
    """Convenience wrapper on check_dict_structure() that returns
    a boolean as opposed to AssertionError"""
    try:
        check_dict_structure(data, structure, exact_match=exact_match)
        return True
    except AssertionError as err:
        return False


def check_dict_structure_one_of(data, structures, exact_match=True):
    """Convenience method. Checks one of the `structures` matches `data`.
    See check_dict_structure() above."""
    errs = []
    matched = False
    for structure in structures:
        try:
            check_dict_structure(data, structure, exact_match=exact_match)
            matched = True
            break
        except AssertionError as err:
            errs.append(str(err))
    
    if not matched:
        raise AssertionError("\n".join(errs))
