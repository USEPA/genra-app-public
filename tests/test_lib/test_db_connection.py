from collections import defaultdict

import pytest

from genraweb.lib import db_connection

EXPECT = [
    # minimum specified
    {
        "input": {"host": "pb.epa.gov", "db": "genradb_v1", "patience": 5000},
        "uri": "mongodb://pb.epa.gov/genradb_v1?serverSelectionTimeoutMS=5000",
        "params": {"host": "pb.epa.gov", "serverSelectionTimeoutMS": 5000},
    },
    # everything specified
    {
        "input": {
            "port": "33333",
            "host": "something.example.com",
            "username": "Joe",
            "password": "NotJoe",
            "db": "JoesDB",
            "patience": 5000,
            "connect_db": "admin",
            "kwargs": "thing=other thing",
        },
        "uri": "mongodb://Joe:NotJoe@something.example.com:33333/"
        "JoesDB?serverSelectionTimeoutMS=5000&thing=other+thing&authSource=admin",
        "params": {
            "port": 33333,
            "host": "something.example.com",
            "username": "Joe",
            "password": "NotJoe",
            "serverSelectionTimeoutMS": 5000,
        },
    },
]


@pytest.mark.parametrize("inputs", EXPECT)
def test_db_connection(inputs):
    """Test uri and params correctly constructed"""
    d = defaultdict(str)  # everything pulled in through os.environ.get(X, '')
    d.update(inputs["input"])

    assert (
        db_connection.get_param(
            d["username"], d["password"], d["port"], d["host"], d["patience"]
        )
        == inputs["params"]
    )
    assert (
        db_connection.get_uri(
            d["username"],
            d["password"],
            d["port"],
            d["host"],
            d["db"],
            d["kwargs"],
            d["patience"],
            d["connect_db"],
        )
        == inputs["uri"]
    )
