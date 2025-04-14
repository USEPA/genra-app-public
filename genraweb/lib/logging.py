"""Single place form which to import a properly configured logger."""
import logging

logger = logging.getLogger("genra_top")
logger.setLevel(logging.DEBUG)
console = logging.StreamHandler()
console.setFormatter(
    logging.Formatter(
        "%(asctime)s:%(filename)s:%(lineno)d %(message)s", datefmt="%m%d-%H%M%S"
    )
)
logger.addHandler(console)
