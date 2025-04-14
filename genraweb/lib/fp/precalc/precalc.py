"""
Script that populates fp_info. Various docker setting adjustments
will be needed. See `genraweb/commands.py` for such docker settings.

Approaches to invocation:
(1) Inside a separate container, invocating something like e.g.
`precalculate(["chm_aim"], ["no_filter"])` through a script precalc_chm_aim.py and
docker compose run --rm -d -u `id -u` --name precalc_chm_aim \
  -e PYTHONPATH=/genra -v $PWD/models:/genra/models genra_api bash -c \
  "cd /genra && python3 misc/tickets/GEN-1034-re-pre-calc-aim-fp/precalc.py"
Use for chemical FPs + no_filter combination, since this
allows attachment/detachment to separate docker container with its own logs.
(2) `flask commands precalculate` command inside the docker container/shell.  Use for
other combinations, to leave running for 0-6 hours
"""

import functools
import itertools
import multiprocessing
import pathlib
import statistics
import time

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO
from genraweb.lib.logging import logger
from genraweb.resources import DB

from .utils import (calc_nns, calc_nns_graph, chunkify, fit_model, get_FP_df,
                    read_pickle, runtime_str, save_model, update_fp_info)

USE_SCIKIT_MULTIPROCESSING = False
# If USE_SCIKIT_MULTIPROCESSING is False, recommend to keep it below 5K
NO_FILTER_CHUNK_SIZE = 2500
# If USE_SCIKIT_MULTIPROCESSING is True, this variable is irrelevant, see N_JOBS in
# precalc/utils.py
N_PRECALC_JOBS = 32


def get_target_chunks(fp_id, sel_by, df_no_filter):
    """Gets a list of chem_id remaining for precalculation, sorts them for priority, and
    returns chunkified subsets of df_no_filter for those chems along with size of
    remaining work.

    Assumes that chem_id information consistent across collections - e.g., no "CID
    missing for BPA in toxref collection but not in chemotypes collection".

    Parameters
    ----------
    fp_id : str
        FP ID
    sel_by : str
        Filter, should be no_filter
    df_no_filter : pandas.DataFrame
        Rows of all chems' (>1.5M) FP vector
    """

    assert sel_by == "no_filter", "Only designed for no_filter, as assumptions are made"

    chunk_size = NO_FILTER_CHUNK_SIZE

    # get set of eligible chem_ids
    all_chem_ids = set(df_no_filter.index)

    # then get set of already calculated chem_ids
    proj = ChemID.chem_id_proj()
    chem_ids_done = set(
        doc["chem_id"]
        for doc in DB[FP_INFO].find({f"{fp_id}.{sel_by}": {"$ne": None}}, proj)
    )

    # unsorted list of chem_ids remaining
    todo = all_chem_ids - chem_ids_done

    # Here, we obtain a list version of `todo` chem. IDs that is ordered in priority.
    # We assume chemicals in smaller FP collection sizes are more important. This adds
    # certain priorities that make sure toxcast chems and toxref chems are calculated
    # first.  sort FP collections by their size, e.g. {..., "htpp_MCF7_fp": 200,
    # "toxref_tr_fp": 1000, "toxcast_fp": 9000}
    counts = {
        fp_class.fp_output_basename: DB[fp_class.fp_output_basename].count_documents({})
        for fp_class in FPGen.FPClass.values()
    }
    counts = dict(sorted(counts.items(), key=lambda item: item[1]))
    # list of sets
    priorities = [todo & set(ChemID.chem_ids_in_collection(col)) for col in counts]
    # using dict as ordered set
    chem_ids = list(dict.fromkeys(itertools.chain(*priorities)))

    # this puts priority chems at top of dataframe
    target_df = df_no_filter.loc[chem_ids]

    # top rows are in first chunk
    return chunkify(target_df, chunk_size), len(target_df.index)


def _precalc_worker(
    df_target_chunk,
    fp_id,
    sel_by,
    model,
):
    """
    Method for precalc that gets distributed to each worker for a given chunk in
    multiprocessing, for chemical FP + no_filter combos.

    Parameters
    ----------
    df_target_chunk : pandas.DataFrame
        Rows of target chems' FP vector
    fp_id : str
        FP ID
    sel_by : str
        Filter, should be no_filter
    model : scikit.NearestNeighbors
        Model fitted with entire chemical FP
    """

    curr_proc = multiprocessing.current_process()
    idx = curr_proc.pid

    start = time.time()
    # calculate neighborhoods
    nns, _ = save_model(
        "nns",
        fp_id,
        sel_by,
        calc_nns,
        model,
        df_target_chunk,
        redo=True,
        suffix=str(idx),
    )
    calc_rt = time.time() - start
    # write to mongo
    start = time.time()
    update_fp_info(
        fp_id, sel_by, df_target=df_target_chunk, suffix=str(curr_proc.pid), nns=nns
    )
    write_rt = time.time() - start

    # true value could/should be passed on from parent/caller
    n_chunks = (1.6 * 1000000) / NO_FILTER_CHUNK_SIZE
    # TODO: get livefeed of how many chunks already completed to calculate/predict
    # remaining run-time, for better stats
    n_chunks = (1.6 * 1000000) / NO_FILTER_CHUNK_SIZE
    logger.info(
        f"\n({fp_id}) Took {runtime_str(calc_rt + write_rt)} "
        f"(calc={runtime_str(calc_rt)}, write={runtime_str(write_rt)}) "
        f"for process {str(curr_proc)}\n"
        "For this rate, expect "
        f"{runtime_str(round(n_chunks*(calc_rt + write_rt)/N_PRECALC_JOBS))} "
        "(NOTE: total. If X time has passed beginning this program, "
        "subtract X to get remaining runtime.)"
    )
    return (calc_rt, write_rt)


def precalculate(fp_ids, filters):
    """For each fp_id, precalculates nearest neighbors for each sel_by filters.

    There are two approaches used in this method:

     -  Chunkified, used for no_filter precalculation on chemical fingerprints. This
     uses multiprocessing to distribute workload.
        Two multiprocessing strategies have been developed, which is controlled by
        USE_SCIKIT_MULTIPROCESSING:
         -  If USE_SCIKIT_MULTIPROCESSING=True, it uses the N_JOBS variable defined
         top-level in precalc/utils.py to set scikit's `n_jobs` model parameter. It's
         not entirely clear how multiprocessing occurs, and scikit does not have clear
         documentation (https://scikit-learn.org/stable/computing/parallelism.html).
         E.g., it could be parallelizing the traversal of ball tree for every target
         chemical, multiple workers per target chem, or it could just be parallelizing
         across multiple target chemicals, one worker per target chem. However, the
         chunks are being worked on linearly - the benefit of chunkifying being the
         ability to intermittenly save results.
            (The lack of scikit documentation, combined with the observation that
            adjusting N_JOBS=15 to N_JOBS=30 -- on a 32 core server, when it was quiet
            -- didn't result in significant peroformance increase, prompted the first
            draft development of second approach, described next below.)
         -  Otherwise, it distributes the chunks to workers for parallelization, using
         the N_PRECALC_JOBS variable and multiprocessing package.
     -  All-at-once. To complate all other FP/filter combinations (incl. chemical FPs +
     filters), takes 4-6 hours to do  on 32 core machine.  It does not need to split
     target chems because it's sufficiently fast to find neighbors for each target chem.

    Note that there are docker settings and user settings that will need to be set in
    order to make this work in a dockerized environment. See `genraweb/commands.py`.
    (May also consider: commenting out log statements in db_connection file.)

    Parameters
    ----------
    fp_ids : list
        FP IDs to precalculate for

    sel_bys : list
        filters to precalculate for each fp_id
    """

    for fp_id in fp_ids:
        fp_class = FPGen.FPClass[fp_id]
        pathlib.Path(f"models/{fp_id}").mkdir(parents=True, exist_ok=True)

        try:
            df_no_filter, _ = read_pickle(f"models/{fp_id}/df_no_filter.pkl")
        except FileNotFoundError:
            # first need no_filter dataframe since that gets for chem_id/index mapping
            df_no_filter, _ = save_model(
                "df", fp_id, "no_filter", get_FP_df, "no_filter", fp_class
            )

        # query/read all necessary data and save first, so that
        # if interrupted can have some things saved
        for sel_by in filters:
            if sel_by in FPGen.FPClass:
                df, _ = save_model("df", fp_id, sel_by, get_FP_df, sel_by, fp_class)
                model, _ = save_model("model", fp_id, sel_by, fit_model, df, fp_class)

        for sel_by in filters:
            if sel_by not in FPGen.FPClass:
                continue

            model, _ = read_pickle(f"models/{fp_id}/model_{sel_by}.pkl")

            if "chm" in fp_id and sel_by == "no_filter":
                # Chunkified approach to precalculation, used for chemical fingerprints
                # + no_filter
                # It works by:
                #   - Obtaining list of chemicals to precalculate (by querying fp_info
                #   to look for eligible chems with no_filter neighborhoods missing),
                #   and splitting them into chunks (To see details on ordering, see
                #   get_target_chunks method)
                #   - For each chunk, calculating neighborhoods, saving it locally, and
                #   uploading them to mongo.
                # Multiprocessing strategy is set by USE_SCIKIT_MULTIPROCESSING
                # variable.  Recommended to run with docker(-compose) run (as opposed to
                # from shelling inside container) so that they can be checked up on with
                # docker logs and monitored as separate container.

                logger.info("\nChunkifying all chemicals...")
                now = time.time()
                df_target_chunks, size_target = get_target_chunks(
                    fp_id, sel_by, df_no_filter
                )
                n_chunks = len(df_target_chunks)
                rt = time.time() - now
                logger.info(
                    f"...finished, took {runtime_str(rt)}, "
                    f"{size_target}/{len(df_no_filter.index)} chemicals left "
                    f"in {n_chunks} chunks\n"
                )

                if USE_SCIKIT_MULTIPROCESSING:
                    # use scikit's n_jobs modeling parameter
                    runtimes = []
                    for idx, df_target_chunk in enumerate(df_target_chunks, 1):
                        start = time.time()
                        # calculate neighborhoods
                        nns, _ = save_model(
                            "nns",
                            fp_id,
                            sel_by,
                            calc_nns,
                            model,
                            df_target_chunk,
                            redo=True,
                        )
                        calc = time.time()
                        # write to mongo
                        update_fp_info(fp_id, sel_by, df_target=df_target_chunk)
                        write_rt = time.time() - calc
                        calc_rt = calc - start
                        runtimes.append(calc_rt + write_rt)

                        _n = len(runtimes)
                        avg = statistics.mean(runtimes)
                        weighted = functools.reduce(
                            lambda accum, rt: (
                                accum[0] + 1,
                                accum[1] + (accum[0] + 1) * rt,
                            ),
                            runtimes,
                            (0, 0),
                        )
                        recent_avg = weighted[1] / (_n * (_n + 1) / 2)
                        n_remain = len(df_target_chunks) - _n
                        logger.info(
                            f"\n({fp_id}) Took {runtime_str(calc_rt + write_rt)} "
                            f"(calc={runtime_str(calc_rt)}, "
                            f"write={runtime_str(write_rt)}) "
                            f"for chunk #{idx}/{len(df_target_chunks)}"
                            f"\n{(size_target - (NO_FILTER_CHUNK_SIZE * _n))//1000:,}K "
                            "chemicals left\nPredicted remaining runtime: "
                            f"avg={runtime_str(n_remain * avg)}, recent weighted "
                            f"avg={runtime_str(n_remain * recent_avg)}\n"
                        )

                else:
                    # use multiprocessing.Pool
                    runtimes = []
                    with multiprocessing.Pool(N_PRECALC_JOBS) as pool:
                        runtimes = pool.starmap(
                            _precalc_worker,
                            zip(
                                df_target_chunks,
                                itertools.repeat(fp_id),
                                itertools.repeat(sel_by),
                                itertools.repeat(model),
                            ),
                        )

            else:
                # All-at-once approach. Does not split the target chems.
                nns, _ = save_model("nns", fp_id, sel_by, calc_nns, model, df_no_filter)
                # sparse matrix that represents the whole graph (not limited to 100, but
                # whole fp space)
                nns_graph, _ = save_model(
                    "nns_graph", fp_id, sel_by, calc_nns_graph, model, df_no_filter
                )
                # write to mongo
                update_fp_info(fp_id, sel_by, df_target=df_no_filter)
