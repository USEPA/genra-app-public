"""
A fragile test but checks physprop property fetching code end to end for breakage.

Also PhysChem (=== PhysProp) FP related items.
"""

from genraweb.lib.properties import physprop
from tests.lib.misc import deep_diff

EXPECTED = {
    "DTXCID001771": {
        "mass": 164.248,
        "BP": 262.12,
        "wtrSol": 0.00102885,
        "vapPres": 0.00205254,
        "MP": 94.4421,
        "logKow": 3.49129,
        "HLC": 6.21129e-07,
        "HBA": 1,
        "HBD": 1,
    },
    "DTXCID30182": {
        "mass": 228.291,
        "wtrSol": 0.000745153,
        "vapPres": 6.77917e-08,
        "MP": 152.696,
        "logKow": 3.32044,
        "HLC": 1.25155e-07,
        "BP": 343.191,
        "HBA": 2,
        "HBD": 2,
    },
    "DTXCID602360": {
        "mass": 206.329,
        "logKow": 4.86708,
        "wtrSol": 8.74848e-05,
        "vapPres": 0.000486421,
        "MP": 84.2258,
        "HLC": 7.90096e-06,
        "BP": 263.348,
        "HBA": 1,
        "HBD": 1,
    },
    # FOOF has no OPERA predictions
    "DTXCID90150942": {
        "mass": 69.995,
        "HBA": 2,
        "HBD": 0,
    },
}


def test_physprop():
    print(physprop.chem_props(list(EXPECTED)))
    deep_diff(EXPECTED, physprop.chem_props(list(EXPECTED)))


"""
PhysChem notes

from scipy.spatial.distance import cosine

These are at fj_ level, should really test range in fp_info

db.fj_chm_phch_no_filter.aggregate([
  {$match: {chem_id: {$ne:null}}},
  {$addFields: {
    minScore: {$min: {$map: {input: "$sims", in: { $min: "$$this" }}}},
    maxScore: {$max: {$map: {input: "$sims", in: { $max: "$$this" }}}},
  }},
  {$project: {minScore:1, maxScore:1, chem_id:1}},
  {$out: "stat_phch"}
])

db.stat_phch.aggregate([{ $group: { _id: "no", minScore: { $min: "$minScore" },
maxScore: { $max: "$maxScore" } } }])

    minScore: 0.49940478801727295,
    maxScore: 0.5000001192092896

Also test that not all values are 0.5 or otherwise uniform.
"""
