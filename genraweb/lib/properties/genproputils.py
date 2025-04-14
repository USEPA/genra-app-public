from pymongo import UpdateOne
from rdkit import Chem
from rdkit.Chem import Descriptors

from genraweb.genra_celery import app as celery_app
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.genfputils import BatchProcess
from genraweb.lib.logging import logger
from genraweb.lib.properties.physprop import PHYSPROP


@celery_app.task
def task_gen_props(chem_ids):
    """ "Celery binding for generating (physchem) props.

    NOTE: see/adjust gen_local_physprop too if any calculation adjustments made"""
    from genraweb.resources import DB  # avoid import before worker forked

    logger.info(f"Start GenProps task: {len(chem_ids)}")
    query = ChemID.chem_id_search(chem_ids, index=True)
    proj = ChemID.chem_id_proj()
    proj["smiles"] = 1
    updates = []
    for chem in DB.compounds.find(query, proj):
        smile = chem["smiles"]
        mol = Chem.MolFromSmiles(smile)
        if mol is None:
            continue
        hba = Descriptors.NumHAcceptors(mol)
        hbd = Descriptors.NumHDonors(mol)
        # should we just stick to CIDs?
        chem_id_match = ChemID.chem_id_search(chem["chem_id"])
        updates.append(
            UpdateOne(
                ChemID.chem_id_search(chem["chem_id"], index=True),
                {"$set": {"HBA": hba, "HBD": hbd}},
                upsert=True,
            )
        )
    DB.compounds.bulk_write(updates)


class GenerateProps(BatchProcess):
    """Batch management for properties generation.
    Modeled after genraweb.lib.fp.genfputils.GenerateFPs class.
    Currently it's hard-coded to work on SMILEs only, since physchem only exists for structured chems."""

    def __init__(self, DB, chem_ids):
        super().__init__(DB, chem_ids)
        self.pps = [pp for pp in PHYSPROP if pp.id in ["HBD", "HBA"]]

    def queue_batch(self, batch):
        """No need to support on the fly here."""
        task_gen_props.delay(batch)

    def get_chem_ids(self):
        query = {"smiles": {"$ne": None}}
        if self.chem_ids_in == "MISSING":
            # require one of the fields to be empty/null
            query = {"$and": [query, {"$or": [{pp.path: None} for pp in self.pps]}]}
        # should we stick to CIDs?
        proj = ChemID.chem_id_proj()
        return list([doc["chem_id"] for doc in self.DB.compounds.find(query, proj)])

    def get_batch_size(self):
        """Sub-class specific batch size."""
        return 50000

    def get_queue_message(self):
        return "physchem poperties"
