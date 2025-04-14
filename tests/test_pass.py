import pytest

from tests.lib.misc import deep_diff


def test_passing():
    """Test the test. Should always pass."""
    assert True


def test_diff():

    a = {"a": 2, "b": [0, 1]}
    b = {"a": 2, "b": [0, 1]}
    deep_diff(a, b)
    b["b"].append(3)
    with pytest.raises(AssertionError):
        deep_diff(a, b)
