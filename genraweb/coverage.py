# from genraweb.lib.misc import GenRA_Coverage

from pathlib import Path

import coverage
from genraweb.lib.logging import logger


class GenRA_Coverage:
    """Code coverage control functions.

    Don't use multi-threading in API container (GUNICORN_CMD_ARGS) while calculating
    coverage.
    """

    def __init__(self):
        pass

    def start(self):
        self.cov = coverage.Coverage(
            data_file="/genra/coverage/coverage2", source=[str(Path(__file__).parent)]
        )
        self.cov.start()
        logger.info("Starting code coverage data collection")

    def stop(self):
        logger.info("Stopping code coverage data collection")
        self.cov.stop()
        logger.info("Saving code coverage data")
        self.cov.save()
        logger.info("Saving code coverage HTML report")
        self.cov.html_report()


cov = GenRA_Coverage()
