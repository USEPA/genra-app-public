import os

import pytest


@pytest.mark.very_slow
def test_toxref_generation(run_fp_generation_test):
    """Test torsion fingerprint generation using the RDKIT library

    Check the .env file:
      - This test will skip unless GENRA_DEPLOYMENT_TYPE is set to LOCAL_DEV
      - This test will error out unless the relevant DB fields
        in template.env are filled in (those with RES for DB)

    Please refer to
    https://confluence.epa.gov/display/CCTEA/FingerPrint+generation
    """
    run_fp_generation_test("tox_txrf", from_path=os.path.dirname(__file__))
