"""Set up celery or fake celery if not using.

NOTE: this is started from start.sh (Dockefile).
"""
import multiprocessing
import os

from genraweb.deploy_types import DeployType

deployment_type = DeployType[os.environ.get("GENRA_DEPLOYMENT_TYPE")]

if deployment_type >= DeployType.DEV and not os.environ.get("GENRA_CELERY_IN_GENRA"):

    class FakeCelery:
        """Fake do nothing celery replacement when not using celery."""

        @staticmethod
        def task(func):
            """So client code can do @app.task without impact."""
            return func

    app = FakeCelery()

else:
    from celery import Celery

    from genraweb.lib.logging import logger

    logger.info("Using Celery broker: %s" % os.environ.get("GENRA_CELERY_BROKER"))

    app = Celery(
        "genra",
        broker=os.environ.get("GENRA_CELERY_BROKER"),
        backend="rpc://",
        # FP generataion task is defined in genfputils, but fpchem etc. need importing
        # to register the FP classes in the worker's FPGen class.
        include=[
            "genraweb.tasks",  # demo task
            # pulls in all the FP classes and task_generate_fp (from genfputils.py)
            "genraweb.lib.fp.fpclass",
            "genraweb.lib.fp.nn_calc",  # task_count_nn
            "genraweb.lib.properties.genproputils",
            "genraweb.lib.genrapred",
            "genraweb.lib.genrapy_multiprocess",
        ],
        result_backend_transport_options={"visibility_timeout": 3600 * 24},
        max_retries=0,
        broker_connection_retry_on_startup=True,
    )
    # Optional configuration, see the application user guide.
    app.conf.update(
        result_expires=3600,
        # GenRA's celery use is CPU, not IO, bound, so we need to use workers
        # (processes), not threads.
        worker_concurrency=int(
            os.environ.get("GENRA_CELERY_WORKERS", min(8, multiprocessing.cpu_count()))
        ),
        concurrency=int(os.environ.get("GENRA_CELERY_THREADS_PER_WORKER", 1)),
    )
    if (os.environ.get("GENRA_CODE_COVERAGE") or "").lower() in (
        "1",
        "y",
        "yes",
        "t",
        "true",
    ):
        # No env. vars. seem to work directly, tried CELERY_TASK_ALWAYS_EAGER,
        # CELERY_ALWAYS_EAGER, CELERY__task_always_eager
        app.conf.update(task_always_eager=True)

if __name__ == "__main__":
    app.start()
