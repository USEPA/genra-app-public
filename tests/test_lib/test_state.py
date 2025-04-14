from genraweb.lib.state import GenRAState


def test_state_fp():
    """Test that fp === fp_id"""

    state = GenRAState()
    assert state.fp == "chm_mrgn" and state.fp_id == "chm_mrgn"

    state = GenRAState(fp_id="test_case1")
    assert state.fp == "test_case1" and state.fp_id == "test_case1"

    state = GenRAState(fp="test_case2")
    assert state.fp == "test_case2" and state.fp_id == "test_case2"

    state = GenRAState()
    state.fp = "test_case3"
    assert state.fp == "test_case3" and state.fp_id == "test_case3"

    state = GenRAState()
    state.fp_id = "test_case4"
    assert state.fp == "test_case4" and state.fp_id == "test_case4"

    state = GenRAState({"fp": "test_case5"})
    assert state.fp == "test_case5" and state.fp_id == "test_case5"

    state = GenRAState({"fp_id": "test_case6"})
    assert state.fp == "test_case6" and state.fp_id == "test_case6"
