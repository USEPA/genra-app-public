"""A state object for GenRA."""
import enum

from genraweb.lib.fp.fputils import is_hybrid_fp
from genraweb.lib.logging import logger


class GenRAFlag(enum.IntFlag):
    # User defined neighborhood
    USERNN = enum.auto()
    usernn = USERNN
    # Multi-target
    MULTITARGET = enum.auto()
    multitarget = MULTITARGET


class GenRAState:
    """GenRA state variable"""

    defaults = dict(
        fp_id="chm_mrgn",
        s0=0.1,
        k0=10,
        sel_by="tox_txrf",
        fp_weight=[],
        pos_min=1,
        neg_min=1,
    )

    fp = property(lambda x: x.fp_id, lambda x, v: setattr(x, "fp_id", v))

    @property
    def flags(self):
        return self._flags

    @flags.setter
    def flags(self, value):
        self._flags = GenRAFlag(0)
        for flag in value.split(","):
            flag = flag.strip().upper()
            if flag in GenRAFlag.__members__:
                self._flags |= GenRAFlag.__members__[flag]
            else:
                logger.warning(f"Unknown flag {flag}")

    def __init__(self, data=None, **kwargs):
        self._flags = GenRAFlag(0)
        if data is None:
            data = {}
        # copy another GenRAState
        if isinstance(data, GenRAState):
            data = data.__dict__.copy()
        # set values
        defaults = kwargs.pop("defaults", {})
        for key, value in (self.defaults | defaults | data | kwargs).items():
            setattr(self, key, value)
        if not isinstance(self.k0, int):
            self.k0 = int(self.k0)
        if not isinstance(self.s0, float):
            self.s0 = float(self.s0)

    def __repr__(self):
        return str(self.__dict__)

    def get(self, attr, default=None):
        """Convenience check for presence of attribute."""
        return getattr(self, attr, default)

    def fp_str(self):
        """FP as a single string, 'chm_mrgn' or 'chm_mrgn_W2_and_bio_txct_W1'."""

        if is_hybrid_fp(self.fp_id):
            return self.fp_id

        fp_ids = self.fp_id.split(",") if isinstance(self.fp_id, str) else self.fp_id
        fp_weight = (
            self.fp_weight.split(",")
            if isinstance(self.fp_weight, str)
            else self.fp_weight
        )
        # fp_hybrid_name_from_lists probably needs updating so implement here
        # return fp_hybrid_name_from_lists(fp_ids, fp_weight)
        if len(fp_ids) == 1:  # no need for weights if only one
            return fp_ids[0]
        return "_and_".join(
            f"{fp_id}_W{weight}" for fp_id, weight in zip(fp_ids, fp_weight)
        )
