"""Imports all the available prediction engines.  Clients should do:

from genraweb.lib.engine.engines import PredEngine

for engine in PredEngine.values():
    ...
or

pred_engine = PredEngine.engine[engine_id]
"""

from .engine import PredEngine
from .genrapred import GenraPred
from .genrapy import GenraPy

(PredEngine, GenraPred, GenraPy)
