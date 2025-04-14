from functools import cache

from rdkit import Chem
from rdkit.Chem import AllChem

from genraweb.deploy_types import DeployType
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger


class FPMrgnhttr(FPGen):
    """Class responsible for both the Morgan and Torsion fingerprints"""

    description = (
        "Morgan fingerprints are also known as extended-connectivity fingerprint "
        "ECFP4.  These circular fingerprints are calculated within the RDKit python "
        "library as bit vectors with a radius of 3 and a length of 2048."
    )
    fp_fields = [FPGen.FP_fields("chms_fp", "mrgn")]
    fp_id = "chm_mrgn"
    fp_output_basename = "chms_fp"
    input_collection_name = "compounds"
    maxDepType = DeployType.PROD
    name = "Chem: Morgan Fgrprts"
    similarity_tag = "c"
    testForSmile = True
    on_the_fly = True
    mrgnhttr_bits = 2048  # Morgan / Torsion specific parameter.

    def _set_fail(self, fp_name, chem, fail):
        """To record that FP generation was run for all chems, store a document
        with a 'fail' key at the root level for failures.  For most FP this is
        trivial, but for Morgan and Torsion both FPs are stored in the same
        collection, so we need to be able to distinguish between them.
        """
        fail_value = chem.get("fail", {})
        fail_value["chm_" + fp_name] = fail
        chem["fail"] = fail_value

    def generate_fps(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.
        Assumes existing values already deleted from collection.
        """
        # look up smiles, and other info we want in same query
        chem_in_all = self.fp_core_fields(chem_ids)
        chem_in = list(chem_in_all)
        chem_in_n = len(chem_in)

        fails = 0
        for chem in chem_in:
            chem["Mol"] = Chem.MolFromSmiles(chem["smiles"])
            if not chem["Mol"]:
                fail = f"{chem['dsstox_cid']} no Mol from RDKit"
                self._set_fail("httr", chem, fail)
                self._set_fail("mrgn", chem, fail)
                fails += 1
                logger.info(fail)

        fp_funcs = dict(
            httr=AllChem.GetHashedTopologicalTorsionFingerprintAsBitVect,
            mrgn=lambda i: AllChem.GetMorganFingerprintAsBitVect(
                i, 3, self.mrgnhttr_bits
            ),
        )

        for fp_name, fp_func in fp_funcs.items():
            for chem in chem_in:
                if not chem["Mol"]:
                    continue
                V = fp_func(chem["Mol"])
                if V:
                    chem[fp_name] = {
                        "ds": [f"{fp_name}_{n}" for n, i in enumerate(V) if i],
                        "n": sum(V),
                    }
                else:
                    # never happens
                    self._set_fail(
                        fp_name, chem, f"{chem['dsstox_cid']} no FP from RDKit"
                    )
                    fails += 1

        for chem in chem_in:
            del chem["Mol"]

        logger.info(
            "Requested %s FP from RDKit, got %s", chem_in_n, len(chem_in) - fails
        )

        if chem_in and self.fp_coll_name:
            self.DB[self.fp_coll_name].insert_many(chem_in)
            # https://pymongo.readthedocs.io/en/stable/faq.html insert_many() adds _id
            # to list items passed to it.
            for chem in chem_in:
                del chem["_id"]

        return chem_in

    def all_chem_ids(self):
        """Return iterator of all chem. ids for this FP."""
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        return (
            i["dsstox_cid"]
            for i in self.DB[self.input_collection_name].find(
                {
                    "$and": [
                        {"dsstox_cid": {"$ne": None}},
                        {"smiles": {"$ne": None}},
                        # excluding | and * excludes *some* Markush structures
                        {"smiles": {"$not": {"$regex": "[|*]"}}},
                    ]
                },
                {"_id": False, "dsstox_cid": True, "smiles": True},
            )
            if i["smiles"].strip().upper() not in ("FAIL", "")
        )

    @classmethod
    @cache
    def bit_names(cls):
        """Names for the bits in the FP.  E.g. mrgn_0, mrgn_1, ... mrgn_2047"""
        return [f"{cls.fp_id[-4:]}_{i}" for i in range(cls.mrgnhttr_bits)]


class FPhttr(FPMrgnhttr):
    """FPMrgnhttr does all the work, this just holds info. for Torsion (httr) FPs."""

    description = (
        "Torsion fingerprints or hashed topological torsion descriptors are "
        "calculated as bit vectors using python's RDKit library. Developed by "
        "Nilakantan et al (1986), the topological torsion is defined as a linear "
        "sequence of 4 consecutively bonded non-hydrogen atoms, each described by its "
        "atomic type, the number of non-hydrogen branches attached to it and its "
        "number of pi electron pairs."
    )
    fp_id = "chm_httr"
    fp_fields = [FPGen.FP_fields("chms_fp", "httr")]
    fp_output_basename = "chms_fp"
    maxDepType = DeployType.PROD
    name = "Chem: Torsion Fgrprts"
    similarity_tag = "c"
    on_the_fly = True
