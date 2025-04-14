"""
Download radial view plot

Uses genra-py drawing code but sub-classes the drawing class to use genraweb's nearest
neighbor calculation to support hybrid FPs.
"""

import math
import tempfile
from pathlib import Path

import matplotlib.pyplot as pl
import numpy as np
import pandas as pd
from genra.rax.viz.nn import GenRAViewNN

from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.mongofp_NN import searchFP
from genraweb.lib.state import GenRAState


class GenRAViewNNKnown(GenRAViewNN):
    """Input will be NN, not using genra-py's calc., to support hybrid"""

    def loadData(self, X, Y=[], Info=None):
        """Just store the data."""
        self._X = X

    def getKNN(self, cid, k):
        """Called in self.circLayout."""
        self._NNi = self._X


def nn_radial_image(state: GenRAState):
    """Return an PNG binary image of the radial plot."""
    nghbrs = searchFP(
        state.chem_id,
        fp=state.fp_str(),
        sel_by=state.sel_by,
        s0=state.s0,
        max_hits=state.k0 + 1,
    )
    nghbrs = pd.DataFrame(nghbrs)
    # columns needed by GenRAViewNNKnown
    nghbrs["ID"] = nghbrs["chem_id"]
    nghbrs["chemical_name"] = nghbrs["name"]
    nghbrs["sim"] = nghbrs["similarity"]
    nghbrs.set_index("chem_id", inplace=True)

    # from Imran's notebook genra-py/notebooks/app-note/010-genra-py-shah-2016.ipynb
    pl.figure(figsize=(10, 10))
    ax = pl.subplot(1, 1, 1)
    ax.set_axis_off()
    ax.set_xlim(-600, 600)
    ax.set_ylim(-600, 600)

    GV = GenRAViewNNKnown(
        rs=1.2,
        lw=0.2,
        ax=ax,
        th_tot=1.9 * math.pi,
        chm_name_font_size=10,
        chm_sz=(180, 180),
        r_min=200,
        dt=FPGen.FPClass[state.fp_id].similarity_tag
        if state.fp_id in FPGen.FPClass
        else "x",
    )
    GV.loadData(nghbrs, np.ones(nghbrs.shape[0]), Info=nghbrs)
    GV.draw(state.chem_id, k=state.k0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "tmp.png"
        pl.savefig(path)
        return path.read_bytes()
