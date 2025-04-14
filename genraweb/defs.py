"""Pure data definitions"""

# "aggregator" is the defaut Aggregator ID from .../aggregator/*.py
FILTER = {
    "tox_txrf": {
        "description": "Only chemicals with ToxRef in vivo data.",
        "name": "ToxRef data",
        "aggregator": "tox_txrf",
    },
    "tox_etaq": {
        "description": "Only chemicals with Aquatic EcoTox data.",
        "name": "Aquatic EcoTox data",
        "aggregator": "tox_txrf", # (for now)
    },
    "bio_txct": {
        "description": "Only chemicals with ToxCast HTS data.",
        "name": "ToxCast data",
        "aggregator": "bio_txct",
    },
    "bio_pest": {
        "description": "Only chemicals considered pesticides.",
        "name": "Pesticides",
        "aggregator": "tox_txrf",
    },
    "chm_pfas": {
        "description": "PFAS chemicals in the PFAS8a7v3 list.",
        "name": "PFAS8a7v3 list",
        "aggregator": "tox_txrf",
    },
    "no_filter": {
        "description": "All chemicals by fingerprint.",
        "name": "No filter (all data)",
        "aggregator": "tox_txrf",
    },
    "multitarget": {
        "description": "User specified multi-chemical target, no filtering.",
        "name": "N/A (multitarget)",
        "aggregator": "tox_txrf",
        "skip": True,  # Need to be able to look this up, but don't offer to user.
        "data_exists": True,
    },
    "user-defined": {
        "description": "User specified neighborhood, no filtering.",
        "name": "N/A (user-defined)",
        "aggregator": "tox_txrf",
        "skip": True,  # Need to be able to look this up, but don't offer to user.
        "data_exists": True,
    },
}

# Extra allowed values in lists of FP IDs
EXTRA_FP_IDS = {"multitarget", "user-defined", "hybrid"}

# list of distinct colors from https://sashamaps.net/docs/resources/20-colors/
# the distinctness and appeal decreases as you go down the list, so zip()ing with
# a fixed order list of fp_ids is probably fine.
COLORS = [
    "#e6194B",  # Red
    "#3cb44b",  # Green
    "#ffe119",  # Yellow
    "#4363d8",  # Blue
    "#f58231",  # Orange
    "#911eb4",  # Purple
    "#42d4f4",  # Cyan
    "#f032e6",  # Magenta
    "#bfef45",  # Lime
    "#fabed4",  # Pink
    "#469990",  # Teal
    "#dcbeff",  # Lavender
    "#9A6324",  # Brown
    "#fffac8",  # Beige
    "#800000",  # Maroon
    "#aaffc3",  # Mint
    "#808000",  # Olive
    "#ffd8b1",  # Apricot
    "#000075",  # Navy
    "#a9a9a9",  # Grey
]
