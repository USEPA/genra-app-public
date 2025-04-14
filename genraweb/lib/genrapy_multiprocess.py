"""
Handles multiprocessing for binary genra-py.
"""

import json
import warnings

import numpy as np
import pandas as pd
from celery.contrib import rdb

from genraweb.genra_celery import app as celery_app
from genra.rax.skl.hybrid import GenRAPredBinaryHybrid


def from_json(X, Y, target, slices):
    """Converting args back into original form from JSON"""
    pd_params = []
    for pd_param in [X, Y, target]:
        pd_param = pd.read_json(pd_param).replace({-1: np.nan})
        pd_param.index.name = "chem_id"
        pd_params.append(pd_param)
    slices = [slice(*slice_args) for slice_args in slices]
    return *pd_params, slices


def to_json(X, Y, target, slices):
    """Necessary JSON conversion to pass args into Celery (through Redis)"""
    pd_params = []
    for pd_param in [X, Y, target]:
        pd_param = pd_param.fillna(-1).astype("int").to_json()
        pd_params.append(pd_param)
    slices = [(_slice.start, _slice.stop, _slice.step) for _slice in slices]
    return *pd_params, slices


def convert(val):
    """Helper to convert data type of val into JSON-serializable Python data type.
    For dealing with incompatibility of numpy data types (e.g., int64) with JSON
    serialization."""
    if val is None:
        return val
    elif np.isnan(val):
        return None
    elif isinstance(val, np.integer):
        return int(val)
    elif isinstance(val, np.floating):
        return float(val)
    else:
        return val


@celery_app.task()
def celery_predict_endpoints(
    eps_chunk,
    X,
    Y,
    target,
    chem_id,
    slices,
    weights,
    k0,
    pos_min,
    neg_min,
):
    """Runs genrapy predictions for each endpoint in Celery for multiprocessing.

    Parameters
    ----------
    eps_chunk : Iterable(str)
        List of endpoint names

    X : JSON string of Iterable(DataFrame)
        Pandas DataFrame representing fingerprint data; each row is a chemical
        and each column is a feature/fp-bit

    Y : JSON string of DataFame
        Y endpoint data where each row is a chemical and each column is an endpoint

    target : JSON string of Iterable(DataFrame)
        Single-row Pandas DataFrame representing target fingerprint data

    chem_id : str
        Target's chem_id as would be represented in X_component or Y dataframes

    slices : Iterable(tuple(start, stop, step))
        Arguments to slices that represent the column boundaries for each fingerprint component

    weights : Iterable(float)
        Hybrid weights, does not have to be normalized

    k0 : int
        Number of neighbors to choose, although this gets overidden if data smaller

    pos_min : int
        Minimum positive observations in neighborhood necessary to predict positive

    neg_min : int
        Minimum negative observations in neighborhood necessary to predict negative

    """
    # TODO
    warnings.filterwarnings("ignore")
    X, Y, target, slices = from_json(X, Y, target, slices)
    results = {}
    # for every endpoint, generate a model and predict
    for ep_name in eps_chunk:
        # get sub_Y
        sub_Y = Y[Y[ep_name].notnull()][ep_name]
        neighborhood_size = sub_Y.shape[0]
        num_pos = sub_Y[sub_Y == 1].shape[0]
        num_neg = sub_Y[sub_Y == 0].shape[0]

        if neighborhood_size < 1:
            # no neighborhood data for this endpoint; likely arrived here because only target had data
            continue

        sub_X = X.loc[sub_Y.index]

        # Build model and predict. We give custom lambda 1-distances because jaccard distance always in [0,1]
        # and if we use scikit learn's default settings it'll do 1/distances. Note that when only one fingerprint
        # (i.e., not hybrid) results of GenRAPRedBinaryHybrid is equivalent to GenRAPredBinary.
        model = GenRAPredBinaryHybrid(
            algorithm="brute",
            metric="jaccard",
            weights=lambda distances: 1 - distances,
            n_neighbors=neighborhood_size,
            slices=slices,
            hybrid_weights=weights,
        )
        model.fit(sub_X, sub_Y)

        if num_pos > 0 and num_neg > 0:
            pred, swa, auc, p_val, _ = model.predict_with_uncertainty(
                target, N=100, pos_label=1
            )
        else:
            proba = np.max(model.predict_proba(target), axis=1)[0]
            pred = model.predict(target)[0]
            swa = proba if pred else 1 - proba
            auc, p_val = 0, 1
        a_s = round(swa, 3)

        # Check if min/max requirements met, after removing target
        if pred and num_pos < pos_min:
            continue
        if not pred and num_neg < neg_min:
            continue

        results[ep_name] = {
            "pred": convert(pred),  # actual class predicted
            "a_s": convert(a_s),  # similarity weighted activity
            "auc": convert(auc),  # AUC of ROC curve
            "p_val": convert(p_val),  # p_val, based on ROC curve
        }

    return results
