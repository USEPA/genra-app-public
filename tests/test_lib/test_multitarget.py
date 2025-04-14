from genraweb.lib import multitarget


def test_chem_ids():
    """Check for commas"""
    assert multitarget.chem_ids("") == [""]
    assert multitarget.chem_ids("DTXCID30182") == ["DTXCID30182"]
    assert multitarget.chem_ids("DTXCID30182,OC(C)COC(CO)CO") == [
        "DTXCID30182",
        "OC(C)COC(CO)CO",
    ]


def test_is_multi():
    """Check for commas"""
    assert multitarget.is_multi("") is False
    assert multitarget.is_multi("DTXCID30182") is False
    assert multitarget.is_multi("DTXCID30182,OC(C)COC(CO)CO") is True


def test_clean_id():
    """DTXSID7020182 is dropped because it == DTXCID30182"""
    assert (
        multitarget.clean_id(
            " DTXSID7020182, DTXCID30182, COOC(=O)CCC(=O)OC(C)(C)C,"
            "DTXSID0020101,OC(C)COC(CO)CO"
        )
        == "DTXCID30182,DTXCID10120460,DTXSID0020101,OC(C)COC(CO)CO"
    )
    assert multitarget.clean_id("Bisphenol A") == "DTXCID30182"
    assert multitarget.clean_id("BPA") == ""
    assert multitarget.clean_id("DTXCID30182") == "DTXCID30182"
