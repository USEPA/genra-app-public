import os
from dataclasses import dataclass
from functools import cache

from genraweb.deploy_types import DeployType
from genraweb.genra_celery import app as celery_app
from genraweb.lib.chem_id import ChemID
from genraweb.lib.logging import logger
from genraweb.lib.registerable import Registerable
from genraweb.task_utils import batches

# would be circular to import from fputils as clients are expected to do
FP_INFO = os.getenv("GENRA_FP_INFO_COLLECTION", "fp_info")


@celery_app.task
def task_generate_fp(fp_id, fp_coll_name, chem_ids):
    "Celery binding for FP generation."
    from genraweb.resources import DB  # avoid import before worker forked

    fp_gen = FPGen.FPClass[fp_id](DB, fp_coll_name)
    logger.info(
        "Start FP gen. task: %s->%s for %s with %s",
        fp_id,
        fp_coll_name,
        len(chem_ids),
        fp_gen,
    )
    return fp_gen.generate_fps(chem_ids)  # return needed for synchronous on the fly


class BatchProcess:
    """Manage batch processing. Used by GenerateFPs, CountNNs, GenerateProps, etc."""

    def __init__(self, DB, chem_ids_in):
        self.DB = DB
        self.chem_ids_in = chem_ids_in

    def queue_batches(self):
        """Create batches for self.chem_id_in."""
        chem_ids = self.get_chem_ids()  # sub-class specific handling
        total = 0
        seen_ids = set()
        for batch_i, batch in enumerate(
            batches(
                chem_ids,
                batch_size=self.get_batch_size(),
                max_batches=int(os.environ.get("GENRA_MAX_FP_BATCHES", 0)) or None,
            )
        ):
            # At the batch level, we assume we don't need to avoid lists in favor of
            # iterables.
            chem_ids = list(batch)  # to be sure it's not an iterator

            ids = set(chem_ids)
            assert ids
            assert len(ids) == len(chem_ids)
            assert not (seen_ids & ids)
            seen_ids |= ids

            total += len(batch)
            result = self.queue_batch(batch)

        logger.info(
            "Queued %s chem. in %s batches for %s",
            total,
            batch_i + 1,
            self.get_queue_message(),
        )
        return result  # for on the fly (single batch)

    def get_chem_ids(self):
        """Sub-class specific chem_ids."""
        raise NotImplementedError

    def get_batch_size(self):
        """Sub-class specific batch size."""
        raise NotImplementedError

    def queue_batch(self, batch):
        """Sub-class specific batch queueing."""
        raise NotImplementedError

    def get_queue_message(self):
        """Sub-class specific log message for queue_batches."""
        raise NotImplementedError


class FPBatchProcess(BatchProcess):
    """Manage batch processing of FP related stuff."""

    def __init__(self, DB, chem_ids, fp_id, fp_coll_name):
        super().__init__(DB, chem_ids)
        self.fp_gen = FPGen.FPClass[fp_id](DB, fp_coll_name)

    def get_chem_ids(self):
        """Get final list of chem_ids.

        **SEE NOTE** on FPGen.get_chem_ids(), this is for creating FPs, not iterating
        chems. with FPs, for that see re-implementation in CountNNs.
        """
        self.init_for_chem_ids()

        # handle different chem_ids_in types
        if self.chem_ids_in == "ALL":
            chem_ids = self.fp_gen.all_chem_ids()
        elif self.chem_ids_in == "MISSING":
            chem_ids = self.fp_gen.missing_chem_ids()
        elif isinstance(self.chem_ids_in, str):
            chem_ids = self.chem_ids_in.split(",")
        else:
            chem_ids = self.chem_ids_in

        return chem_ids

    def get_queue_message(self):
        """Convey FP type"""
        return f"{self.fp_gen.fp_id} FP"

    def init_for_chem_ids(self):
        """Sub-class specific one time init."""
        raise NotImplementedError


class GenerateFPs(FPBatchProcess):
    """Batch management for FP generation."""

    def init_for_chem_ids(self):
        """Drop the collection when processing 'ALL'."""
        if self.chem_ids_in == "ALL":
            self.fp_gen.delete_fps("ALL")

    def queue_batch(self, batch):
        """Delete existing if needed, heuristic to pick sync. or async."""
        if self.chem_ids_in != "ALL":
            self.fp_gen.delete_fps(batch)
        if not self.fp_gen.fp_coll_name or self.fp_gen.fp_coll_name.endswith("_test"):
            logger.info("Synchronous task_generate_fp for testing / on the fly")
            generate_fp = task_generate_fp
        else:
            generate_fp = task_generate_fp.delay
        # return value required for sync. calc.
        return generate_fp(self.fp_gen.fp_id, self.fp_gen.fp_coll_name, batch)

    def get_batch_size(self):
        """FPGen-specific batch size."""
        return 1
        return self.fp_gen.batch_size


class FPGen(
    metaclass=Registerable,
    _reg_id="fp_id",
    _reg_class="FPClass",
    _reg_order="_FPClasses",
):
    """This class implements the generic fingerprinting functions.

    Sub-classes will be registered in FPGen.FPClass (a dict) with key <subclass>.fp_id
    with initial order in FPGen._FPClasses.
    """

    @dataclass
    class FP_fields:
        """Collection and field path to FP {n:123, ds:[]} objects, most FP have a single
        collection with a single {n:123, ds:[]} component, but toxref has {n:123, ds:[]}
        components on multiple paths in multiple collections.
        """

        collection: str  # name a collection holding FP data for the FP type
        path: str  # dotted.path to {n:123, ds:[]} object, e.g. httr or tox_fp2.fp_pos

    # Fingerprint definition attributes

    # parallel process FPs in batches this size, smaller for smaller FP collections
    batch_size = 10_000
    description = "Description of this fingerprint type"
    fp_fields = []  # list of FP_fields
    fp_id = "unique_key_for_fp_subclass"
    fp_output_basename = "basename_of_default_output_fp_collection"
    input_collection_name = "name_of_input_collection"
    name = "Human readable name of FP, 20 char.s max"
    similarity_tag = "x"  # b/c/t bio. / chem. / tox., 'x' for hybrid
    nn_distance = "jaccard"  # Nearest neighbor similarity metric
    similarity_cutoff = None  # "s0" similarity limit adjustment used in searchFP()
    testForSmile = False
    maxDepType = DeployType.DEV  # only expose in UI up to this deployment level
    on_the_fly = False  # can this FP be calculated on the fly
    ds_type = list  # ["mrgn_1", "mrgn_77"], vs chm_physchem dict {"HBD":2, "HBA":7}

    # Preferred ordering, note this exposes the *ID* of FP types that may not be
    # registered at the current deployment level, so use sparingly internally, and
    # iterate FPClass.values() instead where possible.
    _FPClasses = [
        "chm_mrgn",
        "chm_httr",
        "chm_ct",
        "chm_aim",
        "chm_pfas",
        "chm_phch",
        "bio_txct",
        "bio_txct_ATG",
        "bio_txct_BSK",
        "bio_txct_NVS",
        "bio_txct4",
        "bio_pest",
        "tox_txrf",
        "bio_htpp_MCF7",
        "bio_htpp_U2OS",
    ]

    @classmethod
    def _reg_check_register(cls, fp_class) -> bool:
        """See Registerable - check if fp_class should be registered."""
        deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]
        return deployment_type <= fp_class.maxDepType

    def __init__(self, DB, fp_coll_name):
        self.DB = DB
        self.fp_coll_name = fp_coll_name
        self.inputCol = DB[self.input_collection_name]

    def fp_core_fields(self, chem_ids):
        """Convert a list of chem. IDs to richer records with name, weight, etc.
        These are the core base fields to include in all FP results.  Uses the
        compounds collection.

        NOTE: return list assuming this is used for batches, less surprising for caller.

        Args:
        ----
            chem_ids (list): Chem. IDs to look up.

        Returns:
        -------
            list: expanded records
        """
        chems = list(
            self.DB["compounds"].find(
                ChemID.chem_id_search(chem_ids),
                ChemID.core_fields(),
            )
        )

        for chem_id in chem_ids:  # handle chem_id if SMILES not in DB
            if ChemID.id_type(chem_id) == ChemID.SMILES:
                canonical = ChemID.canonical_smile(chem_id)
                if not any(i.get("smiles") in (chem_id, canonical) for i in chems):
                    chems.append({"chem_id": chem_id, "smiles": chem_id})

        return chems

    def delete_fps(self, chem_ids):
        """Delete FPs listed in chem_ids

        Args:
        ----
            chem_ids (str|list): list of chem. or "ALL"
        """
        if not self.fp_coll_name:
            return
        if chem_ids == "ALL":
            self.DB[self.fp_coll_name].drop()
            logger.info("Dropping %s", self.fp_coll_name)
        else:
            self.DB[self.fp_coll_name].delete_many(ChemID.chem_id_search(chem_ids))

    def all_chem_ids(self):
        """Return iterator of all chem. ids for this FP.

        **NOTE:** this returns all possible chem. based on input collection, *NOT*
        the same as all chem. for which there are FPs, which should come from the
        relevant _fp collection and exclude fail: records.
        """
        # FPs need to define their own
        raise NotImplementedError

    def missing_chem_ids(self):
        """Find chems. missing IDs, not heavily tested"""
        # If doing this in memory becomes a problem, could (a) maybe use $lookup, or (b)
        # add a missing_only flag to generate_fps to do this at the batch level.
        existing = set(
            i["dsstox_cid"]
            for i in self.DB[self.fp_coll_name].find(
                {}, {"_id": False, "dsstox_cid": True}
            )
        )
        # Passing this missing_filter below can generate mongo BSON DocumentTooLarge
        # missing_filter = {"dsstox_cid": {"$nin": existing}}, so do possible - existing
        # in Python memory.
        missing_filter = {}
        if self.testForSmile:
            missing_filter["smiles"] = {"$exists": True, "$ne": "FAIL"}
        possible = set(
            i["dsstox_cid"]
            for i in self.DB[self.input_collection_name].find(
                missing_filter, {"_id": False, "dsstox_cid": True}
            )
        )
        return possible - existing

    def skip_nulls(self, X):
        return {k: v for k, v in X.items() if v and v == v}

    @classmethod
    def output_collection_name(cls):
        """Get the collection name FP results will be written to.  Each class has its
        own default, this adds an extension from an environment variable if set.

        Returns
        -------
            str: name of collection
        """
        collection = cls.fp_output_basename + os.environ.get("GENRA_FPCOL_SUFFIX", "")
        return collection

    @staticmethod  # keywords only
    def fp_info_key(*, fp_id: str, sel_by: str) -> str:
        """Mongo $key for fp_id filtered by sel_by, e.g. 'chm_mrgn.tox_txrf'."""
        return f"{fp_id}.{sel_by}"

    def count_nn(self, chem_ids, sel_by="tox_txrf"):
        """Count NN for each chem."""
        for chem_id in chem_ids:
            # s0=0 to include all possible neighbors, let client filter on similarity
            # must not use simple mode, that's what we're pre-calcing for here
            neighbors = self.searchFP(
                chem_id, self.fp_id, self.DB, sel_by=sel_by, s0=0, simple=False
            )
            # searchFP result includes self, but some htpp_MCF7 chem. have no htpp_U2OS
            # FP, and when there's no FP searchFP returns [], so:
            neighbors_n = max(0, len(neighbors) - 1)
            data = dict(
                n=neighbors_n,
                chem_ids=[i["chem_id"] for i in neighbors[1:]],
                similarities=[min(1, i["similarity"]) for i in neighbors[1:]],
            )
            key = self.fp_info_key(fp_id=self.fp_id, sel_by=sel_by)
            _, chem = ChemID.promote_id(chem_id)
            # For precalc., one of these must exist.  To avoid having to look up chem
            # from compounds later, store as dsstox_Xid now, not "chem_id".
            query = {
                k: chem[k]
                for k in ("dsstox_cid", "dsstox_sid")
                if k in chem and chem[k]
            }
            # 2024 update - fast jaccard stores by CID only, so use CID only if present
            # But better to use `flask commands precalculate` anyway.
            if "dsstox_cid" in query:
                query.pop("dsstox_sid", None)
            self.DB[FP_INFO].update_one(query, {"$set": {key: data}}, upsert=True)

    @staticmethod
    def fp_collection_names() -> dict:
        """Map fp_ids to Mongo collection names."""
        names = {k: v.fp_output_basename for k, v in FPGen.FPClass.items()}
        # add positive and negative flavors
        # Toxref
        names["toxp_txrf"] = names["tox_txrf"]
        names["toxn_txrf"] = names["tox_txrf"]
        # Toxcast
        names["biop_txct"] = names["bio_txct"]
        names["bion_txct"] = names["bio_txct"]
        return names

    @staticmethod
    def fp_collection_paths() -> dict:
        """Map fp_ids to Mongo collection paths."""
        paths = {k: v.fp_fields[0].path for k, v in FPGen.FPClass.items()}
        # add positive and negative flavors
        # Toxref
        paths["toxp_txrf"] = FPGen.FPClass["tox_txrf"].fp_fields[0].path
        paths["toxn_txrf"] = FPGen.FPClass["tox_txrf"].fp_fields[1].path
        # Toxcast
        paths["biop_txct"] = FPGen.FPClass["bio_txct"].pred_fields[0].path
        paths["bion_txct"] = FPGen.FPClass["bio_txct"].pred_fields[1].path
        return paths

    @staticmethod
    def allowed_fps(fps):
        """Filter list of FPs to be allowed values only.

        According to GENRA_DEPLOYMENT_TYPE.
        """
        if isinstance(fps, str):
            if "_and_" in fps and "_W" in fps:
                # importing is_hybrid_fp here would be circular :-/
                return fps  # filtering done after hybrids parsed
            # some downstream assume string, so return string not None
            return (
                fps
                if fps in FPGen.FPClass or fps in ("multitarget", "user-defined")
                else "FP_INVALID"
            )
        return [i for i in fps if i in FPGen.FPClass]

    @classmethod
    @cache
    def bit_names(cls):
        """Names for the bits in the FP.  E.g. mrgn_0, mrgn_1, ... mrgn_2047"""
        return get_ds_order(cls, cls.fp_fields[0].collection, cls.fp_fields[0].path)


def get_ds_order(fp_class: FPGen, collection: str, path: str) -> list[str]:
    """Given a collection and fpds path, returns a list FP bits.

    String of all of the FP vector bits/ds, sorted by Python. Used to make sure column
    headers match up in ordering and dimension for FP dataframes.
    E.g., ["mrgn_1", "mrgn_2, ...]
    """
    from genraweb.resources import DB  # avoid import before worker forked

    # Typical case when .ds is a list
    query = [
        {"$project": {"fpds": f"${path}.ds", "_id": False}},
        {"$unwind": "$fpds"},
        {"$group": {"_id": "$fpds"}},
    ]
    if fp_class.ds_type == dict:
        # https://stackoverflow.com/a/68404822
        query = [
            {"$project": {"fpds": {"$objectToArray": f"${path}.ds"}, "_id": False}},
            {"$unwind": "$fpds"},
            {"$group": {"_id": None, "fpds": {"$addToSet": "$fpds.k"}}},
        ]
    docs = DB[collection].aggregate(query, allowDiskUse=True)
    return sorted([doc["_id"] for doc in docs])
