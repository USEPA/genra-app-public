import pytest

from genraweb.lib.chem_id import ChemID

EXPECTED = [
    # All names are treated as SMILES as well in case they're SMILES RDKit doesn't
    # recognize.
    ("BPA", {"$or": [{"name": "BPA"}, {"smiles": "BPA"}]}),
    (["BPA"], {"$or": [{"name": "BPA"}, {"smiles": "BPA"}]}),
    (
        ["BPA", "Atrazine"],
        {
            "$or": [
                {"name": {"$in": ["BPA", "Atrazine"]}},
                {"smiles": {"$in": ["BPA", "Atrazine"]}},
            ]
        },
    ),
    (
        ["BPA", "Atrazine", "DTXCID30182"],
        {
            "$or": [
                {"name": {"$in": ["BPA", "Atrazine"]}},
                {"smiles": {"$in": ["BPA", "Atrazine"]}},
                {"dsstox_cid": "DTXCID30182"},
                {"dtxcid": "DTXCID30182"},
            ]
        },
    ),
    (
        ["BPA", "Atrazine", "DTXCID30182", "CCC", "FOOF", "C1=CC=CN=C1"],
        {
            "$or": [
                {"name": {"$in": ["BPA", "Atrazine"]}},
                # SMILES converted to canonical form
                {
                    "smiles": {
                        "$in": [
                            "BPA",
                            "Atrazine",
                            "CCC",
                            "FOOF",
                            "C1=CC=CN=C1",
                            "C1=CC=NC=C1",
                        ]
                    }
                },
                {"dsstox_cid": "DTXCID30182"},
                {"dtxcid": "DTXCID30182"},
            ]
        },
    ),
    ("2222-22-2", {"casrn": "2222-22-2"}),
    (
        "DTXSID30182",
        {"$or": [{"dsstox_sid": "DTXSID30182"}, {"dtxsid": "DTXSID30182"}]},
    ),
]


@pytest.mark.parametrize("expected", EXPECTED)
def test_chem_id_search(expected):
    """Just check results against expected."""
    search, result = expected
    print(search, result)
    assert ChemID.chem_id_search(search) == result
