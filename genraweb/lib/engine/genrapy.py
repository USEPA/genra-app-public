"""GenraPred(PredEngine) class for the "2021" era GenRA web app engine, genrapred()"""

from genraweb.lib.fp.fputils import is_hybrid_fp

from .engine import PredEngine


class GenraPy(PredEngine):
    """The "2021" era GenRA web app engine, genrapred()"""

    engine_id = "genrapy"
    engine_name = "GenraPy"
    engine_description = (
        "Pip installable genra-py package built on scikit learn"
        "\nBinary and continuous predictions"
    )

