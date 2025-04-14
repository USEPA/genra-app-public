"""Imports all the available aggregators.  Clients should do:

from genraweb.lib.aggregator.aggregatorss import Aggregator

for aggregator in Aggregator.values():
    ...
or

an_aggregator = Aggregator.aggregator_for(), see aggregator.py docstring.
"""

from .aggregator import Aggregator, METADATA  # METADATA for convenience.
from .devtest_agg import DevTestAgg, DevTestAgg2
from .toxcast_agg import ToxCastAgg
from .toxref_agg import ToxRefAggBinary, ToxRefAggDosage

(Aggregator, ToxRefAggBinary, ToxRefAggDosage, ToxCastAgg, DevTestAgg, DevTestAgg2)
