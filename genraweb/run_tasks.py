"""Handle running celery tasks"""

from genraweb.lib.db_connection import open_mongo_db
from genraweb.lib.logging import logger
from genraweb.task_utils import batches
from genraweb.tasks import fetch_records


def batch_test(max_batches=None):
    """Mostly useful for testing celery"""
    db = open_mongo_db()
    batch = 0
    # NOTE: building batches by incrementing batch in a loop like this:
    #     todo = (
    #         db.compounds.find({}, {'dsstox_cid': 1})
    #         .limit(BATCH_SIZE)
    #         .skip(batch * BATCH_SIZE)
    #     )
    # is increasingly slow, perhaps because of lack of an index.

    todo = db.compounds.find({"dsstox_cid": {"$exists": True}}, {"dsstox_cid": 1})

    done = 0
    for batch, subset in enumerate(batches(todo)):
        subset = [i["dsstox_cid"] for i in subset]
        logger.info("Items %s", len(subset))
        task = {"batch": batch, "todo": subset}
        fetch_records.delay(task)
        done += len(subset)
        logger.info("Queued %s, %s" % (batch, done))
        print("Queued %s, %s" % (batch, done))


if __name__ == "__main__":
    batch_test()
