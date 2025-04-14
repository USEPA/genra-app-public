"""
test_cache - test the GenRARedisLRU cache
"""
from genraweb.resources import DB, redis_cache
from tests.lib.misc import clear_cache

import pytest


def test_lru_cache(api_url):
    """Check that we can clear keys from LRU cache.
    Moved over from test_deployment.py"""

    clear_cache(api_url)

    @redis_cache
    def for_test_cache(i):
        return i

    for i in [1, 2, 3, 1, 2, 3]:
        for_test_cache(i)

    data = clear_cache(api_url)
    assert len(data["keys"]) >= 3
    assert data["keys_cleared"] >= 3

    data = clear_cache(api_url)
    # NOTE: *assuming* nothing else got cached in the meantime
    # a parallel test could cache something in theory
    assert len(data["keys"]) == 0, data["keys"]


@pytest.mark.no_smoke  # Usually passes but can fail for pernicious timing.
def test_lru_cache_smart(api_url):
    """Check that cache is 'smart':
    - able to ignore certain key-worded args
    - able to convert some key-worded args that are iterables to tuples
    - able to hash pymongo DB object
    - limit iterable caching to size 10,000

    NOTE: clears cache several times, and assumes no parallel test/API-call
    is made that caches additional things in the meantime"""

    clear_cache(api_url)

    counter = {"counter": 0}

    @redis_cache(
        to_ignore_keys=["unhashable_kwarg"],
        to_tuple_keys=["iterable_kwarg", "iterable_kwarg2"],
    )
    def for_test_cache(
        arg, unhashable_kwarg=None, iterable_kwarg=None, iterable_kwarg2=None
    ):
        counter["counter"] += 1  # state change
        # to prevent pylint unused args errors
        arg, unhashable_kwarg, iterable_kwarg, iterable_kwarg2

    inputs = [  # an equivalent set when calling for_test_cache
        ("xy", "this is ignored", ["x", "y"], ("x", "y")),
        ("xy", {"still": "ignored"}, ["x", "y"], "xy"),
        ("xy", None, ("x", "y"), "xy"),
        ("xy", -1, ("x", "y"), ["x", "y"]),
    ]

    inputs2 = [  # another equivalent set when calling for_test_cache
        (DB, "DB should be hashable", "xy", ["x", "y"]),
        (DB, "this is ignored", ["x", "y"], ("x", "y")),
        (DB, "iterator of dict is on keys", "xy", ["x", "y"]),
    ]

    list(
        map(
            lambda input: for_test_cache(
                input[0],
                unhashable_kwarg=input[1],
                iterable_kwarg=input[2],
                iterable_kwarg2=input[3],
            ),
            inputs + inputs2,
        )
    )

    data = clear_cache(api_url)
    # expecting 2 from cache cleared, one from each of `inputs` and `inputs2`,
    # but will allow upto 4 to account for parallel caching
    assert data["keys_cleared"] >= 2
    assert data["keys_cleared"] <= 4
    assert counter["counter"] == 2  # this should be exact

    # test that iterable hashing limited to 10,000
    counter["counter"] = 0
    clear_cache(api_url)
    num = 10
    for idx in range(2, 2 + num):
        for_test_cache(
            None,
            unhashable_kwarg=[],
            iterable_kwarg=list(i for i in range(idx * 10_000)),
            iterable_kwarg2=["only one element"],
        )
    data = clear_cache(api_url)
    assert data["keys_cleared"] <= 2  # ideal is 0, allow 2 from parallel caching
    assert counter["counter"] == num  # this should be exact
