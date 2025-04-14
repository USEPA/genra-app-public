from genraweb.genra_celery import app as celery_app
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.precalc_hpc.fast_jaccard import fp_query_info
from genraweb.lib.logging import logger
from genraweb.lib.mongofp_NN import searchFP

from .genfputils import FPBatchProcess


@celery_app.task
def task_count_nn(fp_id, chem_ids, sel_by):
    "Celery binding for NN counting."
    from genraweb.resources import DB  # avoid import before worker forked

    fp_gen = FPGen.FPClass[fp_id](DB, None)
    fp_gen.searchFP = searchFP
    logger.info(
        "Start NN count task: %s for %s with %s",
        fp_id,
        len(chem_ids),
        fp_gen,
    )
    fp_gen.count_nn(chem_ids, sel_by)


class CountNNs(FPBatchProcess):
    """Batch management for nearest neighbor counting."""

    def __init__(self, DB, chem_ids, fp_id, sel_by):
        super().__init__(DB, chem_ids, fp_id, None)
        self.sel_by = sel_by

    def queue_batch(self, batch):
        """No need to support on the fly here."""
        task_count_nn.delay(self.fp_gen.fp_id, batch, self.sel_by)

    def init_for_chem_ids(self):
        """The collection is used for all FP types, so *don't* delete it when processing
        ALL like GenerateFPs.init_for_chem_ids().
        """
        pass

    def get_chem_ids(self):
        """Get list of chem_ids.

        **SEE NOTE** on FPGen.get_chem_ids(), this is for iterating
        chems. with FPs, different from chems. in input collection.
        """
        self.init_for_chem_ids()

        if self.chem_ids_in == "ALL":
            fpqi = fp_query_info(self.fp_gen.fp_id)
            proj = {"_id": 0, "dsstox_sid": 1, "dsstox_cid": 1}
            chem_ids = [
                i.get("dsstox_cid") or i["dsstox_sid"]
                for i in self.DB[self.fp_gen.fp_output_basename].find(
                    fpqi.query, proj
                )
            ]
            logger.info(
                "Found %s chem. for %s %s",
                len(chem_ids),
                self.fp_gen.fp_output_basename,
                fpqi.query,
            )
        elif self.chem_ids_in == "MISSING":
            raise NotImplementedError
        elif isinstance(self.chem_ids_in, str):
            chem_ids = self.chem_ids_in.split(",")
        else:
            chem_ids = self.chem_ids_in

        return chem_ids

    def get_batch_size(self):
        """Sub-class specific batch size."""
        return self.fp_gen.batch_size
