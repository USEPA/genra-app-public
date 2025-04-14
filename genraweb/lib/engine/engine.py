"""Base class for predicion engines.  See also ./engines.py"""

from genraweb.lib.registerable import Registerable


class PredEngine(
    metaclass=Registerable,
    _reg_class="engine",
    _reg_id="engine_id",
    _reg_order="_engine_order",
):
    """See Registerable for docs. on sub-class registration."""

    _engine_order = ["GenraPy", "GenraPred"]

    def is_supported(*args, **kwargs):
        """By default, engine is available. Override for customization."""
        return True
