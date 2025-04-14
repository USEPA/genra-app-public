"""Test that Corina runs.  Only works when run as root."""
import json
import os
from pathlib import Path

import pytest

from genraweb.lib.fp.fp_gen_chemotype import run_corina


def test_run_corina():
    """Test that Corina runs and produces the output it produced
    previously, not a test that the answer is right, although the previous
    output seems reasonable.
    """
    if os.environ.get("HOME") != "/root":
        pytest.skip(
            "test_run_corina only works when run as root, "
            "but it's tested on the server by test_chemotypes_generation"
        )
    data = json.load(Path(__file__).with_name("smiles_data.json").open())
    # When this test was written, run_corina returned dict[str, list] but
    # now it returns dict[tuple, list], this code updated for that in terms of
    # reading / writing tuples from JSON.
    if False:  # For calibration, write tuple keys as "___" separated strings.
        expected = run_corina(data, toxprint_file="toxprint_V2.0_r711.xml")
        expected = {
            ("___".join(i or str(i) for i in k) if isinstance(k, tuple) else k): v
            for k, v in expected.items()
        }
        json.dump(expected, Path(__file__).with_name("corina_expected.json").open("w"))
    expected = json.load(Path(__file__).with_name("corina_expected.json").open())
    # Convert back to tuple keys.
    expected = {
        (
            tuple((None if j == "None" else j) for j in k.split("___"))
            if "___" in k
            else k
        ): v
        for k, v in expected.items()
    }
    fps = run_corina(data, toxprint_file="toxprint_V2.0_r711.xml")
    assert fps == expected
