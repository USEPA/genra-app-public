import re
import xml.etree.ElementTree as ET

import pytest
import requests

CID_BIG = [
    ("DTXCID70223961", True),
    ("DTXCID30182", False),
]


@pytest.mark.parametrize("cid,big", CID_BIG)
def test_svg_squares(api_url, cid, big):
    """This test was written so initially it tested its own ability to detect red
    squares and their absence in SVG results.  Now red squares are supressed, it just
    tests for absence.
    """
    resp = requests.get(f"{api_url}/api/genra/v3/viewChem/{cid}.svg")
    assert resp.ok
    svg = resp.content.decode("utf8")
    red_squares = re.search(r"rgb\(100%,0%,0%\).*M(\s[-0-9.]+\s[-0-9.]+\sL){3}", svg)
    # uncomment the next line to test the test, but only if viewChem is returning red
    # squares
    # assert red_squares if big else not red_squares
    # comment the next line if testing the test
    assert red_squares is None


def test_viewChem(api_url):
    """This tests that viewChem endpoint is working and returning an SVG"""
    resp = requests.get(f"{api_url}/api/genra/v3/viewChem/DTXCID30182.svg")
    assert resp.ok
    assert resp.headers["Content-Type"] == "image/svg+xml"
    content_str = str(resp.content.decode("utf8"))
    assert content_str.count("<path ") >= 10
    root = ET.fromstring(content_str)
    keys = root.keys()
    assert "width" in keys
    assert "height" in keys
    assert "viewBox" in keys
