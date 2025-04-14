from tests.lib.misc import deep_diff


def compare_data(expected_data, got_data, endpoint, NCD=True, tolerance=0):
    """
    Variations exist across different versions (code, db, etc) in response data obtained
    by an endpount.

    This method takes `expected_data` and `got_data`, and makes variation-specific
    adjustments and assertions.  Add keyword arguments as needed to drill down more
    specific test variations.

    At the end of adjustments (via various control flow statements), they should be
    identical - that is the final stage equality check.
    """

    if endpoint == "viewChemNNSummary" and NCD:
        # recall that NCD has key 'prop' whereas current codebase uses 'null'
        for elem in got_data["heatmap"]["rect"]:
            elem["prop"] = elem.pop("null")

    elif endpoint == "runGenRAPerfPred":
        """
        p-value is based on a sample, so is not static -- we will need to account for
        differences.
        Using the tolerance approach would make things simple, but this is a percentage
        adjustment -- tolerance=0.5 implies +/- 50% of eachother.
        We will approach it in absolute terms - plus or minus `margin` (note: the unit
        here is p-value, not %) within eachother.
        So, given p-values X and Y (where they're both in [0,1]) from different endpoint
        calls, the following should be true:
        |X - Y| < margin
        """
        margin = 0.2
        key = "p_val"
        result_list_expected, result_list_got = expected_data["pred"], got_data["pred"]
        assert len(result_list_expected) == len(result_list_got)
        for result_expected, result_got in zip(result_list_expected, result_list_got):
            assert abs(result_expected[key] - result_got[key]) < margin
            # now fill in with None so it passes in last stage of equality check
            result_expected[key], result_got[key] = None, None

    else:
        pass

    # final stage equality check
    deep_diff(expected_data, got_data)
    # assert len(list(diff(expected_data, got_data, tolerance=tolerance))) == 0
