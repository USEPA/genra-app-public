from genraweb.deploy_types import DeployType
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger
from genraweb.lib.properties.physprop import chem_props


class FPPhysChem(FPGen):
    """Phys. Chem. FP"""

    description = "Phys. Chem. FP see https://doi.org/10.1016/j.comtox.2018.07.001"
    fp_id = "chm_phch"
    fp_output_basename = "physchem_fp"
    fp_fields = [FPGen.FP_fields(fp_output_basename, "phch")]
    input_collection_name = "compounds"
    maxDepType = DeployType.PROD
    name = "Chem: PhysChem"
    similarity_tag = "c"
    nn_distance = "euclid"
    testForSmile = True
    on_the_fly = False  # logKow from OPERA model not on the fly
    ds_type = dict

    properties = ("mass", "HBD", "HBA", "logKow")

    @classmethod
    def bit_names(cls):
        """Names for the bits in the FP.  E.g. mrgn_0, mrgn_1, ... mrgn_2047"""
        # Used even for this Euclidean similarity FP, see fast_jaccard.py data_func()
        return cls.properties

    def generate_fps(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.
        Assumes existing values already deleted from collection.
        """
        chem_in = self.fp_core_fields(chem_ids)
        chem_in = {i["dsstox_cid"]: i for i in chem_in}
        chem_prop = chem_props(chem_in)

        results = []  # for bulk mongo insert

        for chem_id, chem in chem_in.items():
            if chem_id not in chem_prop:
                # logger.warn("No properties for %s", chem_id)
                continue
            bits = {prop: chem_prop[chem_id].get(prop) for prop in self.properties}
            if any(i is None for i in bits.values()):
                # logger.warn("Missing property for %s, %s", chem_id, bits)
                continue
            results.append(
                chem_in[chem_id]
                | {self.fp_fields[0].path: {"ds": bits, "n": len(bits)}}
            )

        if results:
            self.DB[self.fp_coll_name].insert_many(results)

    def all_chem_ids(self):
        """Return all chem. ids for this FP."""
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        # This is tricky.  We don't have OPERA's HBA/HBD "predictions", so possible is
        # intersection of OPERA's LogP data and the records in the compounds collection
        # for which we've added HBA/HBD values.  But looking at just OPERA's LogP values
        # in physprop allows us to detect missing HBA/HBD data in compounds.  But...
        # RDKit and OPERA have different views of valid SMILES, so 100% HBA/HBD coverage
        # isn't possible.  2024-01-05 running `flask commands genprops` reduced the LogP
        # but no HBA/HBD gap from about 55k to 10k.  BUT... there are CIDS in physchem
        # not present in compounds, which should not happen.  10k = 136 missing HBA/HBD
        # plus 9895 mystery CIDs.
        logp = set(
            i["dsstox_cid"]
            for i in self.DB["physprop"].find(
                {
                    "dsstox_cid": {"$ne": None},
                    "predicted_props.OPERA_LogP": {"$ne": None},
                },
                {"_id": False, "dsstox_cid": True},
            )
        )
        hbad = set(
            i["dsstox_cid"]
            for i in self.DB["compounds"].find(
                {
                    "dsstox_cid": {"$ne": None},
                    "HBA": {"$ne": None},
                    "HBD": {"$ne": None},
                    # mol_weight for DTXCID201324011, a Markush with logP, HBA/HBD, but
                    # no mass
                    "mol_weight": {"$ne": None},
                },
                {"_id": False, "dsstox_cid": True},
            )
        )
        return logp & hbad
