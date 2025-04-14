import json
import math
import time

import numpy as np
import pandas as pd

from genraweb.lib.logging import logger


class Timer:
    """For simple in function time profiling."""
    def __init__(self, active=True):
        self.active = active
        if self.active:
            self.first = time.time()
            self.last = self.first

    def check(self, text):
        if not self.active:
            return
        now = time.time()
        logger.info(
            "==TIME== %s %g (%g%% of %g) elapsed",
            text,
            (last := now - self.last),
            last / (total := now - self.first) * 100,
            total,
        )
        self.last = now


def check_params(data, params, optional=None):
    """Checking that mapping `data` contains all the params in params (unles they're
    also in optional) and no params not in params or optional.
    """
    unexpected = set(data) - (set(optional or []) | set(params))
    if unexpected:
        logger.info("### UNEXPECTED PARAMS ### %s", unexpected)
    missing = set(params) - set(optional or []) - set(data)
    if missing:
        logger.info("### MISSING PARAMS ### %s", missing)


def nan_to_none(d):
    """Post process results to make NaN None in JSON object results.

    Args:
        d (dict or list): result object to adjust

    Returns:
        dict or list: adjusted result object
    """

    def recurse(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(d[k], float) and np.isnan(d[k]):
                    d[k] = None
        if isinstance(d, (dict, list)):
            for i in d if isinstance(d, list) else d.values():
                if isinstance(i, (dict, list)):
                    recurse(i)

    return recurse(d)


def map_with_key(elem_list, elem_key):
    """Convenience method that takes a list of dictionary `elem_list` as input,
    and returns a dictionary with each element's value for `elem_key` as key
    and the element as a value."""
    mapped = {}
    for elem in elem_list:
        key = elem[elem_key]
        if key in mapped:
            mapped[key].update(elem)
        else:
            mapped[key] = elem.copy()
    return mapped


def keep_only(dict_obj, keep_keys):
    """Convenience method; given a dictionary removes all key-value pairs
    except those specified in `keep_keys`; in-place"""
    all_keys = list(dict_obj.keys())  # use list() to change in-place
    for key in all_keys:
        if key in keep_keys:
            continue
        del dict_obj[key]


def normalize_dosage(dosage, weight):
    """Given a dosage string that includes unit (e.g., "100 mg/kg/day"),
    and molecular weight, returns the negative log molar of its equivalent mg/kg/day

    Update backcalc_dosage() to match this.
    """
    assert isinstance(dosage, str)
    if dosage in ["no_data", "pos_effect", "no_effect"]:
        return np.nan

    if pd.isnull(weight) or weight is None:
        return np.nan

    split = dosage.split(" ")
    assert len(split) == 2

    val, unit = float(split[0]), split[1]

    return math.log(normalize_dosage_unit(val, unit) / weight, 10)


def normalize_dosage_unit(val, unit):
    """Helper for normalize_dosage()."""
    conversion = {
        "mg/kg/day": 1.0,
        "mg/m^3": 0.001,
        "mg/m3": 0.001,
        "ppm": 1.0,
        # these two dropped per PO discussion 2022-9-21
        # "mg/L/day": 1.0,  # or is it (1000 * 24.5)/weight ?
        # "mg/L": 1.0,  # here too
        # more oddities from toxref_effects
        "g/kg/day": 0.001,
        "mg/animal/day": np.nan,
        "mg/kg": np.nan,
        "mg/kg/da": 1.0,  # assuming mis-typed day
        "mg/kg/wk": 1.0 / 7.0,
        "ml/kg/day": np.nan,  # would need conc. to get from ml to mg
        "oom": 1.0,  # assuming mis-typed ppm
    }

    return val * conversion.get(unit, np.nan)


def backcalc_dosage(normalized, weight):
    """Inverse of normalize_dosage()."""
    return 10 ** (normalized) * weight


def get_with_mongo_path(doc, mongo_path):
    """
    get_with_mongo_path(
        doc = {
            "a": {
                "b"; {
                    "c": "some_data"
                }
            }
        },
        mongo_path = "a.b.c"
    )

    returns
    "some_data"
    """
    curr = doc
    if "." in mongo_path:
        keys = mongo_path.split(".")
        for key in keys:
            curr = curr.get(key)
            if not curr:
                break
    else:
        curr = doc.get(mongo_path)
    return curr


def echo_flags(request, response):
    """Echoes the flags in the request to the response."""
    if "flags" in request.args:
        response["flags"] = request.args["flags"]
    else:
        try:
            data = json.loads(request.data)
            if "flags" in data:
                response["flags"] = data["flags"]
        except json.decoder.JSONDecodeError:
            pass
    return response


def chunks(lst, n):
    """Chunkifies a list into n even sublists."""
    for i in range(n):
        yield lst[i::n]
