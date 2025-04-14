"""GenraPred(PredEngine) class for the "2021" era GenRA web app engine, genrapred()"""

from .engine import PredEngine


class GenraPred(PredEngine):
    """The "2021" era GenRA web app engine, genrapred()"""

    engine_id = "genrapred"
    engine_name = "GenraPred"
    engine_description = "Legacy prediction engine, binary only, reports confidence"

    def is_supported(fp_id, sumrs_by):
        """Override from PredEngine. GenraPred does not support continuous
        predictions."""
        return "dosage" not in sumrs_by
