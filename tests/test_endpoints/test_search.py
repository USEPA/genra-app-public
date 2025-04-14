"""Test search endpoint"""
from dataclasses import dataclass

import pytest
import requests

from tests.lib.check_response import check_response_basics

# Multiple entries for these, we want the ones with a SID
AMBIGUOUS_SMILES = [
    "[Fe].c1cccc1.CCCCc1cccc1",
    "CC1=CC=CC=CC=CC=CC=C1C",
    "C1C2=C1C=CC=CC=C2",
    "CCCCCSC(CCC)=C=C=C(CCC)SCCCCC",
    "CCCCCCC(C)OC(=O)C(C)C",
    "N1C=CC2=C1C=CN=CC=C2",
]


# These common searches should return the chemical people are looking for first. Except
# Trazine, in which case Atrazine should be in third place, not first.
# "DTXSID8027959" is not a common search but tests strings with [ in them.
@dataclass
class FirstFind:
    """Test params for first result / unique result tests"""

    search_txt: str  # text to search
    sid: str  # sid of correct first result
    first: bool  # expect sid to be first answer
    unique: bool = False  # expect sid to be only answer

    def __str__(self):
        """For pytest parametrize listing"""
        return ":".join([str(i) for i in self.__dict__.values()])


FIRST_FINDS = [
    FirstFind("atrazine", "DTXSID9020112", True),
    # can't do this, two chem. with PFOS as synonym
    # FirstFind("pfos", "DTXSID3031864", True),
    FirstFind("BPA", "DTXSID7020182", True),
    FirstFind("dioxin", "DTXSID2021315", True),
    FirstFind("trazine", "DTXSID9020112", False),
    FirstFind("ethanol", "DTXSID9020584", True),
    FirstFind("1-[(1-Butoxy-2-propanyl)oxy]-2-propanol", "DTXSID8027959", True),
    # searches by sid, cid, or casrn should give single results
    FirstFind("DTXSID9020112", "DTXSID9020112", True, True),
    FirstFind("DTXCID30182", "DTXSID7020182", True, True),
    # atrazine by casrn
    FirstFind("1912-24-9", "DTXSID9020112", True, True),
]


def _get_response(resp):
    response = check_response_basics(resp)
    assert "hits" in response
    return response


@pytest.mark.slow_api
def test_searchChems(api_url):
    # single result for CID
    resp = requests.get(f"{api_url}/api/genra/v3/searchChems/?txt=DTXCID30182")
    response = _get_response(resp)
    assert len(response["hits"]) == 1
    # can check SID here ok
    assert response["hits"][0]["dsstox_sid"] == "DTXSID7020182"
    # single result for SID
    resp = requests.get(f"{api_url}/api/genra/v3/searchChems/?txt=DTXSID7020182")
    response = _get_response(resp)
    assert len(response["hits"]) == 1
    assert response["hits"][0]["dsstox_sid"] == "DTXSID7020182"
    # multiple results, use Bisphenol-A to get >> 1 but <= 100 so BPA is
    # included in results (100 result limit)
    resp = requests.get(f"{api_url}/api/genra/v3/searchChems/?txt=Bisphenol-A")
    response = _get_response(resp)
    assert len(response["hits"]) > 10
    assert any(i["dsstox_sid"] == "DTXSID7020182" for i in response["hits"])


@pytest.mark.slow_api
@pytest.mark.parametrize("find", FIRST_FINDS, ids=[str(i) for i in FIRST_FINDS])
def test_search_order(api_url, find):
    """Test that common seach targets sort to top of hits"""
    resp = requests.get(f"{api_url}/api/genra/v3/searchChems/?txt={find.search_txt}")
    response = _get_response(resp)
    if find.first:
        assert response["hits"][0]["dsstox_sid"] == find.sid
    else:
        assert response["hits"][0]["dsstox_sid"] != find.sid
    if find.unique:
        assert len(response["hits"]) == 1


@pytest.mark.parametrize(
    "smile", AMBIGUOUS_SMILES, ids=[str(i) for i in AMBIGUOUS_SMILES]
)
def test_search_ambiguous(api_url, smile):
    """Test that ambiguous smiles return a result with a SID"""
    resp = requests.get(f"{api_url}/api/genra/v3/searchChems/", params={"txt": smile})
    response = _get_response(resp)
    hits = [i for i in response["hits"] if i.get("smiles") == smile]
    assert len(hits) > 1
    assert bool(hits[0].get("dsstox_sid"))
    # Check we have more results for this smile
    assert any(i.get("smiles") == smile for i in hits[1:])
    # And that none of them have the same SID, which means the test is valid.
    # An unparsable smile might include other SIDs from substring matches.
    assert not any(
        bool(i.get("dsstox_sid")) and i.get("smiles") == smile for i in hits[1:]
    )
