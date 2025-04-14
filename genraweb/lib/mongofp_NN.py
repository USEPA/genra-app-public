from genraweb.lib import multitarget
from genraweb.lib.chem_id import NOTNAMES, UNNAMED, ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO, parse_fp, physchem_slow
from genraweb.lib.fp.genfputils import GenerateFPs
from genraweb.lib.fp.nn_lookup import chem_nn, fp_n_for_chems
from genraweb.lib.logging import logger
from genraweb.lib.misc import Timer, get_with_mongo_path
from genraweb.resources import DB as DEFAULT_DB
from genraweb.resources import TOXREF_SIZE, redis_cache

COL = FPGen.fp_collection_names()
DS = FPGen.fp_collection_paths()


def mongo_eucdist_func():
    """To make it work like all the Jaccard FPs, would need to add a mongodb function to
    calc. Euclid similarity, probably not hard.

    However, we can't do this calc. on the fly, for a SMILES not in the DB, because
    OPERA logKow values are not calc'ed on the fly.

    Therefore, we will only ever be using pre-calced PhysChem FPs, therefore,
    planning to only add Euclid calc. to the HPC based distributed pre-calc. code, which
    will run in a few hours, vs. the batch processing pre-calc. code for mongodb based
    calcs, which will take a few days (800+k phys. chem. FPs, limited by OPERA logKow
    data, vs. the 1.2M for other chem. FPs, which take several days).

    BUT searchFP() relies on having the top 1000+ NN for the hybrid case, so we either
    need to implement this OR store the top 1050 in HPC calc. OR somehow calc. Euclid
    similarity elsewhere.  Going with the last one, see phch_nn().
    """
    raise NotImplementedError


def phch_nn(DB, target_chem_id, sel_by, s0, max_hits_search):
    """A special case because there's no mongo implementation for Euclidian similarity
    and we need more than the ~100 results in fp_info for hybrid case (see comment in
    searchFP()).
    """
    timer = Timer(active=False)
    # Get list (760k!) of NN and sims, this is the time hog here, 10+ sec., other "slow"
    # code below is < 0.5 sec. (two cases)
    nn = physchem_slow(DB, [target_chem_id])[target_chem_id]
    timer.check("got physchem_nn")
    projection = ChemID.chem_id_proj(include_core_fields=True)  # for chem_id key
    if sel_by and sel_by != "no_filter":
        # Don't use output_collection_name(), it might not exist
        filter_collection = FPGen.FPClass[sel_by].fp_output_basename
        # FIXME - The filter itself may need filtering.  For current filters (toxref,
        # toxcast, pesticides) this is ok - if we wanted to filter by chemotypes_fp
        # (why?) we'd need to allow for "failed to process" records in the
        # output_collection.  GEN-1188 might address this
        in_filter = set(
            i["chem_id"] for i in DB[filter_collection].find({}, projection)
        )
        timer.check("read filter")
        nn = nn._replace(
            nn=[i for i in nn.nn if i in in_filter],
            sims=[j for (i, j) in zip(nn.nn, nn.sims) if i in in_filter],
        )
        timer.check("processed filter")

    # Build chem. list, sim. lookup
    chem_ids = nn.nn[:max_hits_search]
    sim = {k: v for k, v in zip(chem_ids, nn.sims)}
    timer.check("updated sims")
    chem_ids[:0] = [target_chem_id]
    sim[target_chem_id] = 1
    # Build lookup for FP ds
    query = ChemID.chem_id_search(chem_ids)
    projection["phch"] = True
    ds = {
        chem["chem_id"]: chem["phch"]["ds"]
        # The query used here from chem_id_search() is ok but unusable in the for loop
        # below.
        for chem in DB.physchem_fp.find(query, projection)
    }
    timer.check("read ds")
    # Build results list
    result = []
    for chem_id in chem_ids:
        # Sending 1000+ queries against an indexed field this way is orders of magnitude
        # faster than one
        # {$or: [{dsstox_cid: {$in: list_}}, {dsstox_sid: {$in: list_}}]} query.
        query = {"dsstox_cid" if "CID" in chem_id else "dsstox_sid": chem_id}
        chem = DB[FP_INFO].find_one(query, projection)
        if not chem:
            continue
        result.append(chem)
        chem["similarity"] = sim[chem["chem_id"]]
        chem["euclid_chm_phch"] = sim[chem["chem_id"]]
        chem["fpds"] = ds[chem["chem_id"]]
    timer.check("assigned ds")
    return result


def mongo_jaccard_func(fpn, target_fp):
    """MongoDB function to calculate Jaccard similarity.
    mongo_eucdist_func() would be an alternative, see docs. for mongo_eucdist_func()
    """
    return {
        "$let": {
            "vars": {
                "olap": {
                    "$size": {
                        "$setIntersection": [
                            "$%s.ds" % fpn,
                            target_fp["ds"],
                        ]
                    }
                }
            },
            "in": {
                "$divide": [
                    "$$olap",
                    {
                        "$subtract": [
                            {"$add": [target_fp["n"], "$%s.n" % fpn]},
                            "$$olap",
                        ]
                    },
                ]
            },
        }
    }


@redis_cache(to_ignore_keys=["DB"], to_tuple_keys=["chem_ids_filter"])
def searchColByFP(
    target_chem_id,  # promoted, from caller (searchFP)
    s0,
    max_hits_search,
    DB=None,
    col="chms_fp",
    fpn="mrgn",
    fp=None,
    sel_by="no_filter",
    simple=False,
):
    """NOTE: results are not consistent between simple=True (attempt fp_info lookup) and
    simple=False (use mongodb calc.) *but* this is because of similarity ties and those
    ties are broken deterministically by searchFP(), the only function that calls this.
    (also only simple=True results include chem_id, a difference also removed by
    searchFP)
    """
    # First get target chem. fp data
    target_query = ChemID.chem_id_search(target_chem_id, index=True)
    if target_query is None:
        # This is a custom SMILES
        target = None
    else:
        target = DB[col].find_one(target_query)

    # next get neighborhood
    if not target and (not fp or not fp.on_the_fly):
        # i.e. SMILES only for an FP that can't be calc'ed on the fly
        logger.debug(
            "searchColByFP no %s in %s for %s %s",
            target_chem_id,
            col,
            target_query,
            fp,
        )
        return []
    target_exists = True
    nn = "DIDN'T TRY"
    if not target:  # generate on the fly, therefore no fp_info lookup possible
        target_exists = False
        batcher = GenerateFPs(DB, target_chem_id, fp.fp_id, None)
        target = batcher.queue_batches()[0]
    elif (
        # simple  # check for pre-calc. in fp_info
        # and sel_by
        # and
        (
            nn := chem_nn(
                chem_id=target_chem_id,
                fp_id=fp.fp_id,
                sel_by=sel_by,
                min_similarity=s0,
                max_nghbrs=max_hits_search,
            )
        )
        is not None
    ):
        return nn

    # FIXME: a special case - this is a big / may not happen fix me
    if fp.fp_id == "chm_phch":  # no mongo implementation available
        return phch_nn(DB, target_chem_id, sel_by, s0, max_hits_search)

    # start building the mongo search query

    # navigate nested keys in document
    # e.g., target_fp = ["mrgn_1", "mrgn_8"]
    target_fp = get_with_mongo_path(target, fpn)

    scalar = max(s0, 0.00001)  # to prevent ZeroDivisionError
    min_size = int(scalar * target_fp["n"])
    max_size = int(target_fp["n"] / scalar)

    # reduce searchspace to speed up query
    Match1 = {
        "%s.n" % fpn: {"$gte": min_size, "$lte": max_size},
        # $in is true for a: {$in: b} if there's any overlap between lists a and b
        "%s.ds" % fpn: {"$in": target_fp["ds"]},
    }

    if sel_by != "no_filter":
        chem_ids_filter = ChemID.chem_ids_in_collection(
            FPGen.FPClass[sel_by].fp_output_basename
            if sel_by in FPGen.FPClass
            else sel_by  # Allow collections to be filter lists without an FP class,
            # e.g. for initial pesticide list filter.
        )
        if target_chem_id not in chem_ids_filter and target_exists:
            # Target may not have prediction/filter data (e.g. toxref), but we still
            # want to pull out its FP fata.
            # NOTE: Custom smiles is an exception, since we won't have data for it. It
            # would be simpler to leave it in, but this will error out since smiles is
            # not an indexed field.
            chem_ids_filter.append(target_chem_id)
        Match1.update(ChemID.chem_id_search(chem_ids_filter, index=True))

    proj = ChemID.core_fields()
    proj["fpds"] = f"${fpn}.ds"  # extract raw FP vector

    proj["similarity"] = (
        mongo_eucdist_func()
        if isinstance(target_fp["ds"], dict)
        else mongo_jaccard_func(fpn, target_fp)
    )

    Agg = [
        {"$match": Match1},
        {"$project": proj},
        {"$match": {"similarity": {"$gte": s0}}},
        {"$sort": {"similarity": -1}},
        {"$limit": max_hits_search},
    ]

    neighborhood = list(DB[col].aggregate(Agg))

    if not target_exists:
        # case: target isn't in neighborhood/collection because on-the-fly
        target["fpds"] = target_fp["ds"]
        for field_key in list(target.keys()):
            if field_key not in proj:
                del target[field_key]
        # add jaccard
        target["similarity"] = 1.0
        # add weight
        target.update(ChemID.chem_from_smiles(target_chem_id))
        neighborhood = [target] + neighborhood

    return neighborhood


def join_neighborhoods(neighborhoods_for_fps, fps, weights):
    """Joins the neighborhoods for each FP, and computes hybrid similarity

    Returns
    -------
    dict: chem_id as keys and diciontary with chemical fields as values.
    """
    # pair each chemical-dictionary with chem_id for key
    chemicals = {}
    for neighborhood, fp_id in zip(neighborhoods_for_fps, fps):
        fp = FPGen.FPClass[fp_id]
        for NN in neighborhood:
            chem_id = ChemID.chem_id(NN)
            NN["chem_id"] = chem_id
            # Note: originally `fp.nn_distance` was always `"jaccard"`
            NN[f"{fp.nn_distance}_{fp_id}"] = NN.pop("similarity")
            NN[f"fpds_{fp_id}"] = NN.pop("fpds", [])  # extract and remove the fp ds
            if chem_id in chemicals:
                chemicals[chem_id].update(NN)
            else:
                chemicals[chem_id] = NN.copy()

    sum_of_weights = sum(weights)
    for chemical in chemicals.values():
        weighted_similarities = [
            chemical.get(f"{FPGen.FPClass[fp_id].nn_distance}_{fp_id}", 0) * weight
            for fp_id, weight in zip(fps, weights)
        ]
        chemical["similarity"] = sum(weighted_similarities) / sum_of_weights

    return chemicals


def add_sortable_keys(chemicals):
    """Adds additional keys to sort on, for tiebreakers:
    `data_quality` (int): number of toxref assays that data exists for the chem.
    `name` (str): if NoneType, this will be changed to UNNAMED
    """
    # add data_quality field
    fp_n = fp_n_for_chems(chem_ids=sorted(chemicals.keys()))
    data_quality_fp = "tox_txrf"  # currently fixed since sel_by=="tox_txrf"
    for chem_id, chemical in chemicals.items():
        chemical["data_quality"] = fp_n[chem_id].get(data_quality_fp, 0)

    # to sort on name, have to make sure all valid strings and no NoneType
    for chemical in chemicals.values():
        name = chemical.get("name")
        if name in NOTNAMES:
            chemical["name"] = UNNAMED


def get_neighborhood(
    target_chem_id,
    neighborhoods_for_fps,
    fps,
    weights,
    s0,
    max_hits=100,
):
    """Returns a list of dictionaries, ordered by similarity (descending), of each
    NN chemical. See below for notes on tie breakers. Size of neighborhood is set
    by max_hits. Target chemical is included at top of list. Therefore,
    number of neighbors = max_hits - 1.

    If hybrid: similarity for each FP is pair with key 'jaccard_{fp_id}', and weighted
    hybrid similarity (computed across all FPs) is paired with key 'jaccard'.
    Additionally, threshold filtering (on calculated similarity), set by s0,
    takes place.

    If not hybrid: not much happens, values for 'jaccard_{fp_id}' and 'jaccard' are
    the same. Threshold filtering (on similarity) is already done in the mongo
    query by searchCollByFP(...).

    Tie breakers: if similarities of two chemicals are the same, the chemical with
    more data points for fingerprint data corresponding to `sel_by`. Currently only
    option is "tox_txrf", so this corresponds to number of toxicities/assay endpoints
    the chemical has data for. This is referred to here with key "data_quality".
    Then after, sorted by name.

    Args:
    ----
        neighborhoods_for_fps (list): list of NNs, where each NNs is in turn a list of
            dictionaries for neighboring chemicals. List index corresponds to that of
            `fps` and `weights`.
        fps (list): list of FPs, e.g: ["chm_mrgn", "bio_txct"]
        weights (list): list of relative weights, e.g.: [21, 7]

    Returns:
    -------
    list: see above
    """
    chemicals = join_neighborhoods(neighborhoods_for_fps, fps, weights)

    # threshold filtering, iterate through keys because of potential deletion
    for chem_id in list(chemicals.keys()):
        if chemicals[chem_id]["similarity"] < s0:
            del chemicals[chem_id]

    add_sortable_keys(chemicals)

    # sort in order of (high to low similarity, high to low data_quality, alphabetic)
    NNs_sorted = sorted(
        [
            chemical
            for chem_id, chemical in chemicals.items()
            if chem_id != target_chem_id
        ],
        key=lambda chemical: (
            -chemical["similarity"],  # take negative because reverse=False
            -chemical["data_quality"],  # take negative here too
            chemical["name"],
        ),
    )[
        : max_hits - 1
    ]  # max_hits includes target too; therefore decrement to get real "K"

    promoted, chem = ChemID.promote_id(target_chem_id)
    target = [
        chemical for chem_id, chemical in chemicals.items() if chem_id == promoted
    ]
    if not target:
        return []
    target = target[0]

    return [target] + NNs_sorted


def searchFP(
    chem_id_in,
    fp="chm_mrgn",
    DB=DEFAULT_DB,
    sel_by="tox_txrf",
    s0=0.1,
    simple: bool = True,  # can use fast lookup, don't need raw FP vectors etc.
    **kwargs,
) -> list:
    """High level nearest neighbors - handle hybrid, multi, etc.

    Args:
    ----
        chem_id (str): target chemical's id (DTXSID, DTXCID, SMILES, etc.). See
        ChemID module fp (str): FP type. See also hybrid fp_id formatting.
        DB (Pymongo.Database): Pymongo Database connection object. Defualt is
            CCTE_DEV_GENRA
        sel_by (str): Currently select by "tox_txrf" or "no_filter"
        s0 (float): Minimum similarity threshold for neighborhood
            consideration. See also below for bio_htpp.
        max_hits (int): size of neighborhood. NOTE: this includes the target chem too.
    """
    chem_id = multitarget.clean_id(chem_id_in)
    if multitarget.is_multi(chem_id):
        return multitarget.neighbors(chem_id)

    if (
        fp in FPGen.FPClass
        and (cutoff := FPGen.FPClass[fp].similarity_cutoff) is not None
        and cutoff < s0
    ):
        logger.warning(f"Overriding s0 {s0} to {cutoff} for {fp}.")
        s0 = cutoff

    target_chem_id, chem = ChemID.promote_id(chem_id_in)
    fps, weights = parse_fp(fp)
    if len(fps) > 1:  # NOTE: 2024-01-05 disabling broke mulitple tests
        simple = False

    # toxref size by last count: 1046
    # the initial search space needs to be large for hybrids, because
    # FP component similarities may be mildly/low inidivudally but high when summed.
    # So might as well make it as large as likely search space (sel_by=tox_txrf).
    # However, if not hybrid, we should utilize fp_info/precalc so set to 100.
    # NOTE: unless max_hits > ~1046, this is TOXREF_SIZE
    lower_bound = 100 if simple else TOXREF_SIZE
    # lower_bound = 100  # This is why we hit NotImplementedError
    max_hits_search = max(kwargs.get("max_hits", 0), lower_bound)

    neighborhoods_for_fps = []
    for fp in fps:
        col = COL.get(fp)
        ds = DS.get(fp)
        if not (ds and col):
            return []

        neighborhood_for_fp = searchColByFP(
            target_chem_id=target_chem_id,
            s0=-1,  # filter combined list not individual lists for hybrid case
            max_hits_search=max_hits_search,
            DB=DB,
            col=col,
            fpn=ds,
            fp=FPGen.FPClass[fp],
            sel_by=sel_by,
            simple=simple,
        )

        neighborhoods_for_fps.append(neighborhood_for_fp)

    neighborhood = get_neighborhood(
        target_chem_id=target_chem_id,
        neighborhoods_for_fps=neighborhoods_for_fps,
        fps=fps,
        weights=weights,
        s0=s0,
        **kwargs,
    )

    return neighborhood
