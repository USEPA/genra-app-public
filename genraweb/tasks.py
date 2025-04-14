import time

from genraweb.genra_celery import app
from genraweb.lib.db_connection import open_mongo_db


@app.task
def fetch_records(task):
    db = open_mongo_db()
    """For testing Celery.  Get records for list of dsstox_cids and see if they
    all have smiles.
    """
    todo = db.compounds.find(
        {"dsstox_cid": {"$in": task["todo"]}}, {"dsstox_cid": 1, "smiles": 1}
    )
    ans = {
        "batch": task["batch"],
        "smiles": all(i.get("smiles") for i in todo),
        "n": len(task["todo"]),
    }
    time.sleep(task.get("delay", 5))
    return ans
