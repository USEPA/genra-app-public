"""ChemoType (ToxPrint, AIM, PFAS) based FPs."""

from functools import cache
from pathlib import Path
from random import shuffle
from subprocess import TimeoutExpired

from genraweb.deploy_types import DeployType
from genraweb.lib.fp.fp_gen_chemotype import (
    CORINA,
    get_csrml_names,
    preferred_id,
    run_corina,
)
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.logging import logger


class FPChem(FPGen):
    """ToxPrint chemotype fingerprint."""

    description = (
        "ToxPrint Chemotypes are a fixed set of structural features targeted to cover "
        "chemical structures from the large toxicity databases and regulatory "
        "inventories (Yang et al 2015). Chemotypes use CSRML (chemical substructure "
        "and reaction mark-up) language to represent atom-bond connectivity as well as "
        "their properties such as pi-systems. The generic structural fragments are "
        "organised by atom, bond, chain, ring types as well as chemical groups "
        "including amino acids, carbohydrates, ligands and nucleobases based on 729 "
        "essential chemotypes of the ToxPrint v2.0_r711.xml."
    )
    fp_fields = [FPGen.FP_fields("chemotypes_fp", "chemotypes")]
    fp_id = "chm_ct"
    fp_output_basename = "chemotypes_fp"
    input_collection_name = "compounds"
    maxDepType = DeployType.PROD
    name = "Chem: ToxPrints"
    similarity_tag = "c"
    testForSmile = True
    on_the_fly = Path(CORINA).is_file()
    batch_size = 1000
    # Chemotype specific param
    corina_xml = "toxprint_V2.0_r711.xml"
    prepend_subgraph_id = False

    def generate_fps(self, chem_ids):
        """Generate fingerprints."""
        try:
            return self.generate_fps_int(chem_ids)
        except Exception as exp:
            logger.error(str(exp))
            return str(exp.__class__.__name__)
        return True

    def generate_fps_int(self, chem_ids):
        """Generate and store FPs for the chems. listed in chem_ids.

        Assumes existing values already deleted from collection.
        """
        # look up smiles, and other info we want in same query
        corina_in = self.fp_core_fields(chem_ids)
        # filter for non-missing smiles
        corina_in = [i for i in corina_in if i.get("smiles") and i["smiles"] != "FAIL"]
        try:
            fprints = run_corina(
                corina_in, self.corina_xml, prepend_subgraph_id=self.prepend_subgraph_id
            )
        except TimeoutExpired:
            # dict with ("fail", key) tuples as keys
            fprints = {("fail", i["dsstox_cid"]): "CORINA timeout" for i in corina_in}
            logger.warning("CORINA timeout")
        real = sum(1 for i in fprints if isinstance(i, str))  # non-tuple keys
        logger.info("Requested %s FP from Corina, got %s", len(corina_in), real)
        id_to_fp = {preferred_id(i): i for i in corina_in}
        # copy chemotypes into dicts in corina_in
        output = self.fp_fields[0].path
        for chem_id, fp in fprints.items():
            if chem_id == ("characteristics", None):
                # The list of characteristics / bits from the top row of output
                if corina_in and self.fp_coll_name:
                    self.DB[self.fp_coll_name].insert_one({"characteristics": fp})
            elif isinstance(chem_id, str):
                try:
                    id_to_fp[chem_id][output] = {"n": len(fp), "ds": fp}
                    id_to_fp[chem_id]["bitstring"] = fprints[("bs", chem_id)]
                except KeyError:
                    logger.info("FP for unknown chem '%s' %s", chem_id, fp)
                    # Nothing to record here.
            elif chem_id[0] == "fail":
                try:
                    id_to_fp[chem_id[1]]["fail"] = fp
                except KeyError:
                    logger.info("Failed FP for ~unknown chem '%s' %s", chem_id, fp[-1])
                    rec = {"no_id": 1, "fail": fp}
                    if len(corina_in) == 1:
                        # No ID but we know what it was.
                        logger.info(
                            "Failed FP for ~unknown chem '%s'",
                            corina_in[0]["dsstox_cid"],
                        )
                        corina_in[0].update(rec)
                    else:
                        corina_in.append(rec)

        for chem in corina_in:  # remove _id
            chem.pop("_id", None)
        if corina_in and self.fp_coll_name:
            self.DB[self.fp_coll_name].insert_many(corina_in)
            return True
        else:
            return corina_in

    def all_chem_ids(self):
        """Return iterator of all chem. ids for this FP.

        NOTE: same implementation used in ./fpmrgnhttr.py (Morgan/Torsion)
        """
        logger.info(
            "Getting all candidates from %s for %s",
            self.input_collection_name,
            self.fp_id,
        )
        return (
            i["dsstox_cid"]
            for i in self.DB[self.input_collection_name].find(
                # excluding | and * excludes *some* Markush structures
                {
                    "$and": [
                        {"dsstox_cid": {"$ne": None}},
                        {"smiles": {"$ne": None}},
                        {"smiles": {"$not": {"$regex": "[|*]"}}},
                        {"smiles": {"$ne": "FAIL"}},
                    ]
                },
                {"_id": False, "dsstox_cid": True},
            )
        )

    def missing_chem_ids(self):
        """What's missing?"""
        # ASSUMES presence in output coll. indicates it exists
        # can't use $nin: list query because can exceed 16 Mb mongo limit.
        possible = set(self.all_chem_ids())
        existing = set(
            i["dsstox_cid"]
            for i in self.DB[self.fp_coll_name].find(
                {
                    "dsstox_cid": {"$ne": None},
                },
                {"_id": False, "dsstox_cid": True},
            )
        )
        missing = list(possible - existing)
        shuffle(missing)
        logger.info(
            "Possible %s, existing %s, missing %s",
            len(possible),
            len(existing),
            len(missing),
        )
        return missing

    @classmethod
    @cache
    def bit_names(cls):
        """Names for the bits in the FP.  E.g. mrgn_0, mrgn_1, ... mrgn_2047."""
        path = Path(__file__).with_name(cls.corina_xml)
        return get_csrml_names(path, cls.prepend_subgraph_id)


class FPAIM(FPChem):
    """AIM fingerprint."""

    description = (
        "AIM fingerprints are a reimplementation of the EPA Analog "
        "Identification Methodology (AIM) features."
    )
    fp_fields = [FPGen.FP_fields("aim_fp", "chemotypes")]
    fp_id = "chm_aim"
    fp_output_basename = "aim_fp"
    maxDepType = DeployType.PROD
    name = "Chem: AIM"
    # Chemotype specific param
    corina_xml = "AIM_V1.1_Sep_07_22.xml"
    prepend_subgraph_id = True


class FPPFAS(FPChem):
    """PFAS fingerprint."""

    description = (
        "Structural features fingerprint for PFAS8a7v3 list chemicals. "
        "DOI:10.1021/acs.chemrestox.2c00403"
    )
    input_collection_name = "PFAS8a7v3_list"
    fp_fields = [FPGen.FP_fields("pfas_fp", "pfas")]
    fp_id = "chm_pfas"
    fp_output_basename = "pfas_fp"
    maxDepType = DeployType.PROD
    name = "Chem: PFAS"
    # Chemotype specific param
    corina_xml = "TxP_PFAS_v1.0.4.xml"
    prepend_subgraph_id = False
