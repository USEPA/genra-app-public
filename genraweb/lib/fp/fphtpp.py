"""High Throughput Phenotypic Profiling (HTPP, cell painting) fingerprint."""
import json
import os
from collections import defaultdict
from functools import cache
from itertools import chain

import numpy as np
import pandas as pd

from genraweb.deploy_types import DeployType
from genraweb.genraservice.db.htpp import getChemHtppHits
from genraweb.lib.chem_id import ChemID
from genraweb.lib.db_connection import open_mongo_db
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger

# HTPP upstream data is spread over these DBs
UPSTREAM_SRC = {
    "MCF7": [
        dict(db="res_htpp_mcf7_pfas_1", cell="MCF7", study="PFAS S1 MCF7", query=None),
        dict(
            db="res_htpp_refchem120",
            cell="MCF7",
            study="RefChem 120",
            query=dict(cell_type="MCF7"),
        ),
    ],
    "U2OS": [
        dict(
            db="res_htpp_u2os_pfas_1",
            cell="U2OS",
            study="PFAS 1 U2OS low density",
            query=None,
        ),
        dict(
            db="res_htpp_u2os_pfas_2",
            cell="U2OS",
            study="PFAS 1 U2OS high density",
            query=None,
        ),
        dict(db="res_htpp_u2os_toxcast", cell="U2OS", study="ToxCast U2OS", query=None),
        dict(db="res_htpp_u2os_apcra", cell="U2OS", study="ACPRA U2OS", query=None),
        dict(
            db="res_htpp_refchem120",
            cell="U2OS",
            study="RefChem 120",
            query=dict(cell_type="U2OS"),
        ),
    ],
}


class FPHTPP_MCF7(FPGen):
    """High Throughput Phenotypic Profiling (HTPP, cell painting) fingerprint.

    Based on https://github.com/i-shah/genra-service/ 013-make-htpp-fp.ipynb / fd3e9d0

    The HTPP data uses a `chem_id` (ChemTrack ID?) which is not a SID/CID.  So we
    map back and forth a bit.

    HTPP upstream data is spread across several DB per UPSTREAM_SRC.
    """

    batch_size = 1_000_000_000
    # Very high batch_size because this is a two step process and simplest to do in a
    # single batch as total time is not high.
    cell = "MCF7"  # an HTPP specific FP subclass
    description = (
        "High Throughput Phenotypic Profiling (HTPP, cell painting). "
        "This is a fingerprint representation of 1300 features in one of two cell "
        "types U2OS or MCF7. Morphological information for each cell, intensity, "
        "texture captured as each fluorescent label gives rise to 1300 features. This "
        "representation provides a profile/fingerprint that can be used to compare "
        "substances with annotated reference chemicals to elucidate potential "
        "mechanisms."
    )
    fp_fields = [FPGen.FP_fields("htpp_MCF7_fp", "fp.MCF7_lt100_50")]
    fp_id = "bio_htpp_MCF7"
    fp_output_basename = "htpp_MCF7_fp"
    input_collection_name = "htpp_tcpl"
    maxDepType = DeployType.DEV
    name = "Biology: HTPP_MCF7"
    similarity_tag = "b"
    similarity_cutoff = 0.005  # known to be lower than 0.1 used for most FP
    testForSmile = False
    on_the_fly = False

    def generate_fps(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.
        Assumes existing values already deleted from collection.

        chem_ids is a list of "regular (sid, cid, maybe casrn, smiles) IDs.

        We know on_the_fly is False, so don't bother with fp_coll_name is None test.
        """
        from genraweb.resources import DB  # to avoid pre-fork import in workers

        chem_in = self.fp_core_fields(chem_ids)
        chem_in = {i["dsstox_sid"]: i for i in chem_in}  # all HTPP chem. have SID
        if len(chem_in) != len(chem_ids):
            logger.info("Some HTPP chem not found %s", set(chem_ids) - set(chem_in))
        else:
            logger.info("Found %s HTPP chem. ok", len(chem_in))
        # map HTPP chem_id to HTPP htpp_chem records
        htpp_to_chem = self._union_htpp_chem()
        # and from there to SIDs
        # FIXED: multiple HTPP chem_id values for the same SID
        # db.htpp_cr_fp_1.find({dtxsid: "DTXSID70880230"}, {dtxsid:1, cell:1, db:1,
        # study:1, chem_id:1, _id:0, stype:1})
        sid_to_chem_ids = defaultdict(set)
        for chem_id, chem in htpp_to_chem.items():
            sid_to_chem_ids[chem["dtxsid"]].add(chem_id)
        # finally, list of HTPP chem_ids from the SIDs of the regular chem_ids param.
        htpp_chem_ids = list(
            set(
                chain.from_iterable(
                    sid_to_chem_ids[i["dsstox_sid"]] for i in chem_in.values()
                )
            )
        )

        results = []
        for src in UPSTREAM_SRC[self.cell]:
            logger.info("Processing %s", src["db"])
            os.environ["GENRA_DB_HTPP_DB"] = src["db"]
            db = open_mongo_db(which="HTPP")
            query = dict(chem_id={"$in": htpp_chem_ids}, **(src.get("query") or {}))
            for result in getChemHtppHits(hitcall=0.9, Q=query, col=db.htpp_tcpl):
                result = {**chem_in[result["dtxsid"]], **src, **result}
                # del result["dtxsid"] - left for use by merge_results()
                # if "chem_name" in result:
                #     del result["chem_name"]
                # `name` is needed in genraPred, elsewhere we pull from chem_in expanded
                # with core_fields() as above, for simplicity here take the HTPP name.
                result["name"] = result.get("name", result["chem_name"])
                if result.get("stype") == "test sample":
                    result["stype"] = "test chemical"  # from notebook
                results.append(result)
                if len(results) >= 10_000:
                    DB[self.fp_coll_name].insert_many(results)
                    logger.info("Wrote %s %s FPs", len(results), self.fp_id)
                    results = []
        if results:
            logger.info("Wrote %s %s FPs", len(results), self.fp_id)
            DB[self.fp_coll_name].insert_many(results)

        self.merge_results()

    def merge_results(self):
        """Same chem.+cell seen in multiple studies, take median.

        From genra-service 013-make-htpp-fp.ipynb
        """
        from genraweb.resources import DB  # to avoid pre-fork import in workers

        step1_name = self.fp_coll_name + "_step1"
        DB[self.fp_coll_name].rename(step1_name, dropTarget=True)
        step1 = DB[step1_name]
        SID = step1.distinct("dtxsid")
        FAIL = []
        Nf = [50, 100, 200, 300]
        Cf = [50, 100]
        if None in SID:
            SID.remove(None)
        for sid in SID:
            Hits = []
            FP = {}
            R = dict(dtxsid=sid)
            dtx_cid = None
            for X in step1.find(dict(dtxsid=sid), dict(_id=0)):
                if not dtx_cid:
                    dtx_cid = X.get("dsstox_cid")
                H = pd.DataFrame(X["hits"])
                # TNB X[k] -> X.get(k), KeyError on host 2021-11-18
                I = {k: X.get(k) for k in ["db", "cell", "study", "host"]}
                H = H.join(pd.DataFrame(I, index=H.index))
                Hits.append(H)
                R.update({k: X[k] for k in ["chem_name", "casrn", "stype"]})
            # print("{chem_name}".format(**R))
            Hits = pd.concat(Hits)
            for cell, H_i in Hits[Hits.approach == "feature"].groupby(["cell"]):
                # Ch = H_i.endpoint.unique().tolist()
                # FP[cell]=dict(ds=Ch,n=len(Ch))
                H_cell = (
                    H_i.groupby("endpoint")
                    .aggregate(dict(top=lambda x: np.abs(np.median(x)), bmd="median"))
                    .reset_index()
                    .sort_values("top", ascending=False)
                )
                # nh = H_cell.shape[0]
                for n, bmd0 in [(i, j) for i in Nf for j in Cf]:
                    Ch_n = (
                        H_cell[(H_cell["bmd"] <= bmd0)]
                        .head(n)
                        .endpoint.unique()
                        .tolist()
                    )
                    FP["{}_lt{}_{}".format(cell[0], bmd0, n)] = dict(
                        ds=Ch_n, n=len(Ch_n)
                    )
            # R['hits']=Hits.to_dict('records')
            R["fp"] = FP
            R["dsstox_sid"] = R["dtxsid"]  # TNB
            if dtx_cid:
                R["dsstox_cid"] = dtx_cid  # TNB
            # `name` is needed in genraPred, elsewhere we pull from chem_in expanded
            # with core_fields() as above, for simplicity here take the HTPP name.
            R["name"] = R.get("name", R["chem_name"])
            try:
                DB[self.fp_coll_name].insert_one(R)
            except Exception:
                FAIL.append(sid)
                logger.info("HTPP merge_results() insert fail")

    def _union_htpp_chem(self):
        """Combine htpp_chem collections from all HTPP DBs"""
        all_chem = {}
        for src in UPSTREAM_SRC[self.cell]:
            old_len = len(all_chem)
            os.environ["GENRA_DB_HTPP_DB"] = src["db"]
            db = open_mongo_db(which="HTPP")
            for chem in db.htpp_chem.find():
                all_chem[chem["chem_id"]] = chem
            logger.info(
                "Added %s chem. from %s for %s",
                len(all_chem) - old_len,
                src["db"],
                self.fp_id,
            )
        return all_chem

    def all_chem_ids(self):
        """Return iterator of all chem. ids for this FP"""
        all_chem = self._union_htpp_chem().values()
        sids = [i["dtxsid"] for i in all_chem if "dtxsid" in i]
        logger.info("%s of %s HTPP chem. have a SID", len(sids), len(all_chem))
        return set(sids)  # set() correct for this method, dupes need handling elsewhere

    @classmethod
    @cache
    def bit_names(cls):
        """Names for the bits in the FP.  E.g. mrgn_0, mrgn_1, ... mrgn_2047

        Do sort for f_1, f2, ... not f1, f_10, ...
        """
        return sorted(super().bit_names(), key=lambda x: int(x.split("_")[1]))


class FPHTPP_U2OS(FPHTPP_MCF7):
    """U2OS version of FPHTPP_MCF7"""

    cell = "U2OS"  # an HTPP specific FP subclass
    fp_fields = [FPGen.FP_fields("htpp_U2OS_fp", "fp.U2OS_lt100_50")]
    fp_id = "bio_htpp_U2OS"
    fp_output_basename = "htpp_U2OS_fp"
    input_collection_name = "htpp_tcpl"
    maxDepType = DeployType.DEV
    name = "Biology: HTPP_U2OS"


def main():
    """Get lists of CIDs SIDs for testing.  Run once (already done) to generate
    chemicals_ids.json for HTPP tests."""
    import random

    ref_db = open_mongo_db(which="RES")  # htpp_cr_fp_1 has expected answers

    ans = {"comment": "Cover all HTPP DBs and cell types.", "includes": []}
    # includes is used to list countds from each DB / cell type for reference,
    # <cell_type>, <db>, <sid_only_IDs_found>, <cids_found>
    # not all cell type / db combinations have SID only chem.
    for cell_type in UPSTREAM_SRC:
        expected = [
            i["chem_id"]
            for i in ref_db.htpp_cr_fp_1.find(
                {}, {"chem_id": 1, "cell": cell_type, "_id": 0}
            )
        ]
        ans[cell_type] = {"sids": [], "cids": []}
        for source in UPSTREAM_SRC[cell_type]:
            os.environ["GENRA_DB_HTPP_DB"] = source["db"]
            db = open_mongo_db(which="HTPP")
            # all IDs in study collection, a lot of EPAxxx etc.
            htpp_ids = set(
                i["chem_id"] for i in db.htpp_tcpl.find({}, {"chem_id": 1, "_id": 0})
            )
            # mapping to SID, all HTPP chems have SID
            trans = {
                i["chem_id"]: i["dtxsid"]
                for i in db.htpp_chem.find({}, {"chem_id": 1, "dtxsid": 1, "_id": 0})
            }
            # translate to SID
            htpp_ids = [trans[i] for i in htpp_ids if i in trans]
            # check that answers exist in reference collection
            expected_ids = [trans[i] for i in expected if i in trans]
            htpp_ids = [i for i in htpp_ids if i in expected_ids]
            # promote to CID were possible, so remainins SIDs are SID only chem
            htpp_ids = [ChemID.promote_id(i)[0] for i in htpp_ids]
            sids = [i for i in htpp_ids if i.startswith("DTXSID")]
            cids = [i for i in htpp_ids if i.startswith("DTXCID")]
            sids = random.sample(sids, min(4, len(sids)))
            cids = random.sample(cids, min(4, len(cids)))
            ans[cell_type]["sids"].extend(sids)
            ans[cell_type]["cids"].extend(cids)
            ans["includes"].append((cell_type, source["db"], len(sids), len(cids)))
        # don't trigger test for uniqueness in FP gen.
        ans[cell_type]["sids"] = list(set(ans[cell_type]["sids"]))
        ans[cell_type]["cids"] = list(set(ans[cell_type]["cids"]))

    print(json.dumps(ans, indent=4))


if __name__ == "__main__":
    main()
