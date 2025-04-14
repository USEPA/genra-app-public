"""Test the chemotypes for a number of substance ids/smiles/toxprint.xml
using CORINA software are created correctly and updating the chemotypes
collection.
"""
import os

import pytest


@pytest.mark.parametrize("fp_id", ["chm_ct", "chm_aim"])
@pytest.mark.very_slow
def test_chemotypes_generation(run_fp_generation_test, fp_id):
    """
    Test the ToxPrint, AIM, etc. ChemoType / Corina FPs.
    """
    run_fp_generation_test(fp_id, from_path=os.path.dirname(__file__))
