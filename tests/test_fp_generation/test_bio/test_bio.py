import os

import pytest

@pytest.mark.skip("Reference data is out of date")
def test_bio_generation(run_fp_generation_test):
    """Test bio fingerprint generation

    Check the .env file:
      - This test will skip unless GENRA_DEPLOYMENT_TYPE is set to LOCAL_DEV
      - This test will error out unless the relevant DB fields
        in template.env are filled in (those with PB_V5)

    Please refer to
    https://confluence.epa.gov/display/CCTEA/FingerPrint+generation
    """
    run_fp_generation_test("bio_txct", from_path=os.path.dirname(__file__))
