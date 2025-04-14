"""Load API specs. and inject variable information like list of available FP types.

See context defined in inject_variables() for list of {{|KEY_NAME|}} substitutions,
currently just "ALLOWED_FPS".
"""

from pathlib import Path

import yaml

from genraweb import defs
from genraweb.lib.aggregator.aggregators import Aggregator
from genraweb.lib.fp.fpclass import FPGen


def api_spec_path(spec: str) -> str:
    """Get path to spec."""
    path = Path(__file__).parent / "specs"
    return str(path / (spec + ".yaml"))


def api_spec(spec: str, **kwargs) -> dict:
    """Get spec and modify it with kwargs."""
    path = Path(__file__).parent / "specs"
    path /= spec + ".yaml"
    spec = yaml.safe_load(path.read_text())
    spec |= kwargs
    return spec


def api_spec_components() -> dict:
    """Get the components section of the API spec."""
    spec = {
        "schemas": {
            "chem_id": {
                "type": "string",
                "default": "DTXCID30182",
                "description": "the ID of the input chemical",
            },
            "dsstox_cid": {
                "type": "string",
            },
            "chem_inc": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "tox_inc": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "k0": {
                "type": "integer",
                "description": "The number of nearest neighbours to return",
                "default": 12,
            },
            "S0": {
                "type": "number",
                "description": "The similarity threshold",
                "default": 0.1,
            },
            "pos0": {
                "type": "integer",
                "description": "The number positives for each "
                "toxicity classification",
                "default": 1,
            },
            "neg0": {
                "type": "integer",
                "description": "The number positives for each "
                "toxicity classification",
                "default": 1,
            },
            "fp": {
                "type": "string",
                "enum": list(FPGen.FPClass),
                "description": "the type of fingerprint to use "
                "for similarity searching",
                "default": "chm_mrgn",
            },
            "fp_weight": {
                "type": "string",
                "description": "If the fp ID is a comma separated list of "
                "FPs (hybrid), then fp_weight is a comma separated list of "
                "weights.",
                "default": "1",
            },
            "sel_by": {
                "type": "string",
                "enum": list(defs.FILTER),
                "description": "select only those chemicals that "
                "have the corresponding data",
                "default": "tox_txrf",
            },
            "engine": {
                "type": "string",
                "enum": ["genrapred", "genrapy"],
                "description": "The prediction engine to use.",
                "default": "genrapred",
            },
            "summarise": {
                # Note: enum add to schema at end of this file
                "type": "string",
                "description": "The type of information to be summarised.",
            },
            "sumrs_by": {
                # Note: enum add to schema at end of this file
                "type": "string",
                "description": "How the information will be summarised across the "
                "levels of biological organisation",
            },
            "file_type_response": {
                "type": "string",
                "enum": ["html", "svg", "json"],
                "description": "File type for plot",
                "default": "svg",
            },
            "rra_schema": {
                "allOf": [
                    {"$ref": "#/components/schemas/chem_id"},
                    {"$ref": "#/components/schemas/chem_inc"},
                    {"$ref": "#/components/schemas/tox_inc"},
                    {"$ref": "#/components/schemas/k0"},
                    {"$ref": "#/components/schemas/S0"},
                    {"$ref": "#/components/schemas/pos0"},
                    {"$ref": "#/components/schemas/neg0"},
                    {"$ref": "#/components/schemas/fp"},
                    {"$ref": "#/components/schemas/fp_weight"},
                    {"$ref": "#/components/schemas/sel_by"},
                    {"$ref": "#/components/schemas/summarise"},
                    {"$ref": "#/components/schemas/engine"},
                ],
            },
        },
        "parameters": {
            "search_text": {
                "name": "txt",
                "in": "query",
                "schema": {"type": "string"},
                "description": "a partial pattern containing chemical name, "
                "casrn, synonym, dtx sid, dtx cid.  sid/cid should start "
                "with DTXSID/DTXCID",
            },
            "filter_rows": {
                "name": "filt_rows",
                "in": "query",
                "schema": {"type": "string"},
                "required": False,
                "description": "text pattern to filter the row sumrs_by values",
            },
            "chem_id": {
                "name": "chem_id",
                "in": "query",
                "schema": {"$ref": "#/components/schemas/chem_id"},
                "required": True,
            },
            "k0": {
                "name": "k0",
                "in": "query",
                "schema": {"type": "integer", "default": 12},
                "description": "The number of nearest neighbors to return",
            },
            "s0": {
                "name": "s0",
                "in": "query",
                "schema": {"type": "number", "default": 0.1},
                "description": "The similarity threshold",
            },
            "fp": {
                "name": "fp",
                "in": "query",
                "schema": {
                    "type": "string",
                    "default": "chm_mrgn",
                    "enum": list(FPGen.FPClass),
                },
                "description": "the type of fingerprint to use "
                "for similarity searching",
            },
            "fp_weight": {
                "name": "fp_weight",
                "in": "query",
                "schema": {"type": "string", "default": "1"},
                "description": "If the fp ID is a comma separated list of FPs "
                "(hybrid), then fp_weight is a comma separated list of weights.",
            },
            "sel_by": {
                "name": "sel_by",
                "in": "query",
                "schema": {
                    "type": "string",
                    "default": "tox_txrf",
                    "enum": list(defs.FILTER),
                },
                "description": "Select only those chemicals that have "
                "the corresponding data",
            },
            "summarise": {
                "name": "summarise",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": [
                        "bio_txct",
                        "tox_txrf",
                    ],  # note these are overwritten below
                },
                "description": "The type of information to be summarised.",
            },
            "sumrs_by": {
                "name": "sumrs_by",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": [  # note these are overwritten below
                        "gene_name",
                        "gene_symbol",
                        "target_family",
                        "bio_process",
                        "cell",
                        "tissue",
                        "organ",
                        "organism",
                        "study",
                        "bio_fp",
                        "tox_fp",
                    ],
                },
                "description": "How the information will be summarised across the "
                "levels of biological organisation",
            },
            "minpos": {
                "name": "minpos",
                "in": "query",
                "schema": {"type": "number", "default": 0},
                "description": "Minimum positive observations to "
                "make a positive prediction",
            },
            "minneg": {
                "name": "minneg",
                "in": "query",
                "schema": {"type": "number", "default": 0},
                "description": "Minimum negative observations to "
                "make a negative prediction",
            },
            "engine": {
                "name": "engine",
                "in": "query",
                "schema": {"type": "string", "enum": ["genrapred", "genrapy"]},
                "description": "Prediction engine to use",
            },
            "graph_steps": {
                "name": "steps",
                "in": "query",
                "schema": {
                    "type": "integer",
                    "description": "The number of steps from the target to "
                    "take when building answer",
                    "default": 3,
                },
            },
            "graph_type": {
                "name": "graph_type",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": ["all_nhgbrs", "out_only"],
                    "description": "type of links to return",
                    "default": "all_nhgbrs",
                },
            },
            "graph_expanded": {
                "name": "expanded",
                "in": "query",
                "schema": {
                    "type": "string",
                    "description": "comma sep. list of chem_ids expanded in view",
                },
                "required": False,
            },
            "file_type_response_path": {
                "name": "ftype",
                "in": "path",
                "required": True,
                "schema": {"$ref": "#/components/schemas/file_type_response"},
            },
            "file_type_response": {
                "name": "ftype",
                "in": "query",
                "schema": {"$ref": "#/components/schemas/file_type_response"},
            },
            "file_type_table": {
                "name": "ftype",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": ["xlsx", "csv"],
                    "description": "File type for table",
                },
            },
            "chem_ids": {
                "name": "chem_ids",
                "in": "query",
                "schema": {"$ref": "#/components/schemas/chem_id"},
                # Override description
                "description": "List of chem_ids to run generation for. "
                "If 'MISSING', will run on detected candidates. "
                "If 'ALL', will run on all from scratch.",
            },
            "fp_or_nn": {
                "name": "fp_or_nn",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": ["fps", "nn"],
                    "description": "Generate FPs or nearest neighbor counts",
                },
            },
            "stop": {
                "name": "stop",
                "in": "query",
                "schema": {
                    "type": "string",
                    "enum": ["stop"],
                    "description": "Action to take",
                    "default": "stop",
                },
            },
            "collection_name": {
                "name": "collection_name",
                "in": "query",
                "schema": {
                    "type": "string",
                    "description": "Name of DB collection",
                },
            },
            "num_files": {
                "name": "num_files",
                "in": "query",
                "schema": {
                    "type": "integer",
                    "description": "number of most recently modified files",
                    "default": 5,
                },
            },
        },
    }

    summarise = set()
    sumrs_by = set()
    for key, agg in Aggregator.aggregator.items():
        summarise.add(key)
        sumrs_by.update(agg.groupings)
    spec["schemas"]["summarise"]["enum"] = sorted(summarise)
    spec["schemas"]["sumrs_by"]["enum"] = sorted(sumrs_by)
    spec["parameters"]["summarise"]["schema"]["enum"] = sorted(summarise)
    spec["parameters"]["sumrs_by"]["schema"]["enum"] = sorted(sumrs_by)
    # Copy descriptions from schemas to parameters  FIXME
    return spec
