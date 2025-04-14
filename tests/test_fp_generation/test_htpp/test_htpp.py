"""Test HTPP fingerprint generation."""
import os


def not_test_htpp_generation_MCF7(run_fp_generation_test):
    """Test HTPP fingerprint generation."""
    # Disabled pending HTPP update
    run_fp_generation_test("bio_htpp_MCF7", from_path=os.path.dirname(__file__))


def not_test_htpp_generation_U2OS(run_fp_generation_test):
    """Test HTPP fingerprint generation."""
    # Disabled pending HTPP update
    run_fp_generation_test("bio_htpp_U2OS", from_path=os.path.dirname(__file__))
