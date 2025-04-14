import multiprocessing
from io import StringIO
import warnings
from io import StringIO

import numpy as np
import pandas as pd
import sklearn.metrics as metrics
from celery import group
from scipy.spatial.distance import pdist, squareform

from genraweb.genra_celery import app as celery_app
from genraweb.lib.fp.fputils import parse_fp
from genraweb.lib.mongofp import getFP
from genraweb.lib.mongofp_NN import searchFP
from genraweb.lib.misc import chunks
from genraweb.resources import redis_cache


def getKNN(chem_id, Sim, k0=10, s0=0, sim=False, drop_self=True):
    S_i = Sim.loc[chem_id, :]
    if drop_self:
        S_i = S_i.drop(chem_id)
    NN = None

    if k0 and s0:
        # S_i = S_i[S_i > s0] out as unnecessary since that test already performed
        S_i.sort_values()
        NN = S_i[-k0:]
    elif k0:
        S_i.sort_values()
        NN = S_i[-k0:]
    elif s0:
        # NN = S_i[S_i > s0] out as unnecessary since that test already performed
        NN = S_i

    if sim:
        return NN
    else:
        return NN.index


def permuteAUC(auc0, Act, N=100, pos=1):
    Y_t, Y_p = Act.a_t, Act.a_p
    AUC = []
    for i in range(N):
        Y_r = np.array(Y_t.copy())
        np.random.shuffle(Y_r)
        fpr, tpr, t0 = metrics.roc_curve(Y_r, Y_p, pos_label=pos)
        AUC.append(metrics.auc(fpr, tpr))

    p_val = 1.0 * np.sum(np.array(AUC) > auc0) / N

    return p_val


def calcAUC(Act, N=100, pos=1):
    # t0,auc,p_val=0.5,0,1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fpr, tpr, t0 = metrics.roc_curve(
            Act.a_t, Act.a_p, pos_label=1, drop_intermediate=False
        )
    if np.isnan(fpr).any():
        fpr = np.array([0])
    if np.isnan(tpr).any():
        tpr = np.array([1])
    tnr = 1 - fpr
    Roc = pd.DataFrame(zip(fpr, tnr, tpr, t0), columns=["fpr", "sp", "sn", "t0"])
    Roc["BA"] = 0.5 * (Roc.sp + Roc.sn)

    try:
        auc = metrics.auc(fpr, tpr)
        p_val = permuteAUC(auc, Act, N, pos)
        Roc0 = Roc.query("t0<=1")
        idx_max = Roc0.BA.idxmax()
        t0 = Roc0.t0.loc[idx_max]
    except Exception:
        t0, auc, p_val = 0.5, 0, 1
    return t0, auc, p_val, Roc


def calcSimWtAct(A, S, k0=5, s0=0.0):
    A = A[pd.notnull(A)]
    CID = A.index
    S1 = S.loc[CID, CID]

    Res = pd.DataFrame(
        np.zeros((len(CID), 4)), index=CID, columns=["a_t", "a_p", "n_p", "n_n"]
    )

    for chem_id in CID:
        S_i = getKNN(chem_id, S1, k0=k0, s0=s0, sim=True)
        A_i = A[S_i.index]
        Res.loc[chem_id, "a_t"] = A.loc[chem_id]
        Res.loc[chem_id, "a_p"] = 0 if S_i.sum() == 0 else np.sum(A_i * S_i) / S_i.sum()
        Res.loc[chem_id, "n_p"] = (A_i > 0).sum()
        Res.loc[chem_id, "n_n"] = (A_i == 0).sum()
    return Res


def convert(val):
    """Helper to convert data type of val into JSON-serializable Python data type.
    For dealing with incompatibility of numpy data types (e.g., int64) with JSON
    serialization."""
    if val is None:
        return val
    elif isinstance(val, np.integer):
        return int(val)
    elif isinstance(val, np.floating):
        return float(val)
    else:
        return val


def predSimWtAct(chem_id, A, S, p, k0=5, s0=0.0, t0=0.5):
    a_t = A.loc[chem_id] if chem_id in A.index else None
    A = A[pd.notnull(A)]
    CID = list(A.index)
    if chem_id not in CID:
        CID = [chem_id] + CID
    S1 = S.loc[CID, CID]

    S_i = getKNN(chem_id, S1, k0=k0, s0=s0, sim=True)
    A_i = A[S_i.index]

    if p > 0.2:
        t0 = 0.5

    a_s = a_p = 0
    if S_i.sum() == 0:
        # no chems in neighborhood has data
        return {}
    else:
        a_s = np.sum(A_i * S_i) / S_i.sum()
        a_p = 1 if a_s >= t0 else 0

    # PY3 None > int comparison
    if a_t is not None and a_t > 0:
        if a_p == 1:
            pred = "TP"
        elif a_p == 0:
            pred = "FN"
    elif a_t is not None and a_t == 0:
        if a_p == 1:
            pred = "FP"
        elif a_p == 0:
            pred = "TN"
    else:
        if a_p == 1:
            pred = "Pos"
        elif a_p == 0:
            pred = "Neg"

    a_s = np.round(a_s, decimals=3)
    return dict(pred=pred, a_t=convert(a_t), a_s=convert(a_s), a_p=convert(a_p))


def from_json(Y_pos, Y_neg, S, Y_fp):
    """Converting args back into original form from JSON"""
    Y_pos = pd.read_json(StringIO(Y_pos)).replace({-1: np.nan})
    Y_neg = pd.read_json(StringIO(Y_neg)).replace({-1: np.nan})
    S = pd.read_json(StringIO(S))
    Y_fp = pd.read_json(StringIO(Y_fp)).replace({-1: np.nan})

    return Y_pos, Y_neg, S, Y_fp


def to_json(Y_pos, Y_neg, S, Y_fp):
    """Necessary JSON conversion to pass args into Celery (through Redis)"""
    Y_pos = Y_pos.fillna(-1).astype("int").to_json()
    Y_neg = Y_neg.fillna(-1).astype("int").to_json()
    S = S.astype("float").to_json()
    Y_fp = Y_fp.fillna(-1).astype("int").to_json()

    return Y_pos, Y_neg, S, Y_fp


@celery_app.task()
def predict_endpoints(
    eps_chunk,
    Y_pos,
    Y_neg,
    target_chem_id,
    pos_min,
    neg_min,
    S,
    k0,
    s0,
    n_perm,
    Y_fp,
    fp_x,
):
    """Runs genrapred predictions for each endpoint in Celery task, given all necessary
    values in `args`."""
    Y_pos, Y_neg, S, Y_fp = from_json(Y_pos, Y_neg, S, Y_fp)
    Res = []

    for y in eps_chunk:
        posnb = Y_pos[y].sum() if y in Y_pos else 0
        negnb = Y_neg[y].sum() if y in Y_neg else 0

        # don't count obs. for target in obs. count
        if (
            y in Y_pos
            and target_chem_id in Y_pos[y]
            and not np.isnan(Y_pos[y][target_chem_id])
        ):
            posnb -= 1
        if (
            y in Y_neg
            and target_chem_id in Y_neg[y]
            and not np.isnan(Y_neg[y][target_chem_id])
        ):
            negnb -= 1
        if posnb < pos_min and negnb < neg_min:
            continue
        if posnb == 0 and negnb == 0:
            # case: no chems in neighborhood have data on this endpoint
            continue

        Act = calcSimWtAct(Y_fp[y], S, k0=k0, s0=s0)
        t0, auc, p_val, Roc = calcAUC(Act, N=n_perm)
        Yi = Y_fp[y]
        Yi = Yi[Yi.notnull()]
        R = {
            "out": y,
            "auc": convert(auc),
            "k0": convert(k0),
            "s0": convert(s0),
            "fp": fp_x,
            "n_pos": convert((Yi == 1).sum()),
            "n_neg": convert((Yi == 0).sum()),
            "p_val": convert(p_val),
            "t0": convert(t0),
            "chem_id": target_chem_id,
            "dsstox_cid": target_chem_id,  # keep compatible with v3
        }

        R.update(predSimWtAct(target_chem_id, Yi, S, p_val, k0=k0, s0=s0, t0=t0))

        assert R["pred"] in ("Neg", "TN", "FN", "Pos", "TP", "FP")
        if R["pred"] in ("Neg", "TN", "FN") and negnb < neg_min:
            continue
        if R["pred"] in ("Pos", "TP", "FP") and posnb < pos_min:
            continue

        Res.append(R)

    return Res


@redis_cache(to_ignore_keys=["DB"], to_tuple_keys=["Y", "CID"])
def runGenRA(
    target_chem_id,
    Y=None,
    CID=None,
    DB=None,
    fp_x="chm_mrgn",
    fp_y="toxp_txrf",  # legacy
    fp_y_pos="toxp_txrf",
    fp_y_neg="toxn_txrf",
    sel_by=None,
    k0=10,
    s0=0.1,
    metric="jaccard",
    pred=True,
    ret=None,
    wt=True,
    n_perm=100,
    pos_min=1,
    neg_min=1,
):
    """
    target_chem_id  : the ChemID of the target chemical (required)

    Y    : list of toxicities for evaluation of activities (optional)

    CID  : list of chem_ids of chemicals to consider in neighbourhood (optional)

    DB   : reference to mongodb (required)

    fp_x : fingerprint for chemical similarity. Options:
          - chm_mrgn: RDKit Morgan (default)
          - chm_httr: RDKit Torsion
          - chm_ct  : ChemoTypes

    fp_y: fingerprint for predicted bioactivity. This is resolved to a specific
          database collection and attribute. Currently only consider toxicity. Options
          - toxp_txrf: toxref toxicity classifications.
          NOTE*: deprecated/legacy, see fp_y_pos and fp_y_neg

    fp_y_pos: positive fingerprint for predicted bioactivity. This is resolved to a
          specific database collection and attribute.
          - toxp_txrf: toxref toxicity classifications.
          - biop_txct: toxcast classification

    fp_y_ngqeg: negative fingerprint for predicted bioactivity. This is resolved to a
          specific database collection and attribute.
          - toxn_txrf: toxref toxicity classifications.
          - bion_txct: toxcast classification


    sel_by: when finding nearest neighbours of target, select the neighbours based on
            availability of this information. Options:
          - tox_txrf: toxref toxicity classifications.

    k0    : Number of nearest neighbours to consider

    s0    : Similarity threshold measured by metric

    metric: Similarity metric. Options:
          - Jaccard (default)

    n_perm: Number of permutations for testing significance of AUC

    pred  : Whether to predict activity for target or just calculate the
            predictive performances

    ret   : Results to return. Options:
          - full: a list with three elements
            1. Predictions for target
            2. Performance results for neighbourhood
            3. Similarity scores for chemicals in neighbourhood
          - else:
            * Performance results

    pos_min: Minimum number of positive effects in analogs to predict a positive effect

    neg_min: Minimum number of negative effects in analogs to predict a negative effect

    Description of returned values:

    * Predictions for target - a list of predictions, one for each bioactivity outcome.
      Each prediction is a dict with the following keys:
      - dsstox_cid  : DSSTOX CID of target
      - out         : bioactivity/toxicity endpoint
      - k0          : k0
      - s0          : s0
      - fp          : fp_x
      - a_t         : Observed activity of target for out
      - a_s         : Similarity weighted bioactivity of target across neighbours
      - a_p         : Predicted activity 0/1 based on threshold t0
      - auc         : ROC area under curve across a_s and a_t for neighbours
      - t0          : activity threshold that produces best balanced accuracy
      - p_val       : the significance of auc across n_perm
      - pred        : the prediction class
                      if a_t known  : one of TN/TP/FN/FP
                      if a_t unknown: one of Pos/Neg

    * Performance results for neighbourhood as a dict in which keys are
      bioactivity/toxicity endpoints and values are dictionaries with the following
      keys:
      - out        : Binary activity of each analog (no effect:0/effect: 1)
      - act        : Similarity weighted activities for each analog in the
                     neighbourhood as a pandas.DataFrame with the following columns:
             - chem_id: DSSTOX CID of analog (index)
             - a_t       : True activity of analog
             - a_p       : Simiarity weighted bioactivity of analog
             - n_p       : Number of positives
             - n_n       : Number of negatives
      - roc        : The receiver operating characteristic for the neighbourhood
                     as a dataframe with the following columns:
             - fpr       : false positive rate
             - sp        : specificity
             - sn        : sensitivity
             - t0        : score threshold
             - BA        : balanced accuracy = 0.5 * (sn+sp)

    * Similarity matrix for all k0 chemicals considered in neighbourhood as a
      k0xk0 pandas.DataFrame in which rows and columns are indexed by chem_id and
      the value of each cell is the similarity score based on above metric

    """
    Hits = searchFP(
        target_chem_id,
        fp=fp_x,
        s0=s0,
        max_hits=k0 + 1,
        DB=DB,
        sel_by=sel_by,
        # simple=False,  # Premature here, searchFP() can work this out
    )

    if not Hits:
        Hits = []
        if ret == "all":
            return [], {}, {}
        else:
            return Hits
        # return jsonify(dict(hits=[]))

    target_chem_id = Hits[0]["chem_id"]  # In case target_chem_id was multi
    NN = pd.DataFrame(Hits)
    CID0 = list(set(NN.chem_id).intersection(CID)) if CID else list(NN.chem_id)

    if len(CID0) == 1 and target_chem_id in CID0:
        # Case where no other chems in neighborhood but the target. Here until GEN-546
        # is resolved, at which point it should be fixed at endpoint level.
        # Return no predictions since UI will display actual results (if exists).
        return []

    # get weighted pairwise similarity matrix for each fingerprint
    fps, weights = parse_fp(fp_x)
    sum_weights = sum(weights)
    pairwise_similarities = []

    for fp, weight in zip(fps, weights):
        # X_fp is a dataframe: each row is a chemical's raw fp-vector.
        # instead of using `getFP` method in mongofp.py, use the raw fp
        # data given by `searchFP` in mongofp_NN.py, since on-the-fly fp-gen
        # chemical isn't in the collection to be queried.
        X_fp_rows = []
        for chem in Hits:
            fpds = chem.get(f"fpds_{fp}")
            if not fpds:
                # no fp data for this chem
                continue
            row = {bit: 1 for bit in fpds}
            row.update(({"chem_id": chem["chem_id"]}))
            X_fp_rows.append(row)
        X_fp = pd.DataFrame(X_fp_rows)
        X_fp = X_fp.set_index(["chem_id"])
        X_fp = X_fp.fillna(0)

        if X_fp.empty:
            continue
        S_fp = 1 - pd.DataFrame(
            squareform(pdist(X_fp, metric)), columns=X_fp.index, index=X_fp.index
        )
        S_fp_weighted = S_fp * weight / sum_weights
        pairwise_similarities.append(S_fp_weighted)
    # sum weighted similarities across fingerprints
    S = pd.concat(pairwise_similarities).groupby("chem_id").sum()
    S = S[S.index]  # make it symmetric

    if S.empty:
        return []

    Y_pos = getFP(CID0, DB=DB, fp=fp_y_pos, FP=Y)
    Y_neg = getFP(CID0, DB=DB, fp=fp_y_neg, FP=Y)

    # in the case of fp_y="bio_txct", calling them "components" would probably be more
    # appropriate than calling them "endpoints"
    endpoints = list(set(Y_pos.columns.values) | set(Y_neg.columns.values))
    endpoints.sort()

    Y_fp = Y_neg.replace({1: 0}).reindex(endpoints, axis=1)
    Y_fp = Y_fp.reindex(CID0, axis=0)
    Y_fp[Y_pos == 1] = 1

    eps_chunks = chunks(list(Y_fp.columns), multiprocessing.cpu_count())

    Y_pos, Y_neg, S, Y_fp = to_json(Y_pos, Y_neg, S, Y_fp)

    Res = group(
        predict_endpoints.subtask(
            (
                chunk,
                Y_pos,
                Y_neg,
                target_chem_id,
                pos_min,
                neg_min,
                S,
                k0,
                s0,
                n_perm,
                Y_fp,
                fp_x,
            )
        )
        for chunk in eps_chunks
    )
    Res = Res.apply_async()
    Res = Res.get()
    Res = [item for sublist in Res for item in sublist]  # flatten
    Res = [pred for pred in Res if pred is not None]
    return Res
