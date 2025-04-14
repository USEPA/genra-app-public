"""Customized RedisLRU cache"""

import types
from functools import wraps

import redis_lru
from redis_lru.lru import ArgsUnhashable


class GenRARedisLRU(redis_lru.RedisLRU):
    """An 'smart' implementation of redis_lru.RedisLRU, but with additional options to
    ignore certain key-worded args and convert iterables to tuples for hashing."""

    def __call__(self, ttl=60 * 15, to_ignore_keys=None, to_tuple_keys=None):
        """Mostly copied and pasted from source code of redis_lru.RedisLRU, except it
        additionally takes in `to_ignore_keys` and `to_tuple_keys`, and passes them on
        to `_decorator_key(...)`.  See doc for `_decorator_key(...)` for details on how
        these parameters are used."""
        func = None

        # empty list as default value creates linting error PLW0101, so workaround
        if to_ignore_keys is None:
            to_ignore_keys = []
        if to_tuple_keys is None:
            to_tuple_keys = []

        def inner(*args, **kwargs):
            try:
                key = self._decorator_key(
                    func,
                    to_ignore_keys,  # Because of these two args, this now
                    to_tuple_keys,  # calls overridden method defined below
                    *args,
                    **kwargs,
                )
            except redis_lru.lru.ArgsUnhashable:
                return func(*args, **kwargs)
            else:
                try:
                    return self[key]
                except KeyError:
                    result = func(*args, **kwargs)
                    self.set(key, result, ttl)
                    return result

        # decorator without arguments
        if callable(ttl):
            func = ttl
            ttl = 60 * 15
            return wraps(func)(inner)

        # decorator with arguments
        def wrapper(f):
            nonlocal func
            func = f
            return wraps(func)(inner)

        return wrapper

    def _decorator_key(
        self,
        func: types.FunctionType,
        to_ignore_keys: list,
        to_tuple_keys: list,
        *args,
        **kwargs,
    ):
        """Calls on its parent class's method, after:
          - key-worded args in `to_ignore_keys` are temporarily removed from `kwargs`
          - key-worded args in `to_tuple_keys` are converted to tuples in `kwargs`
        Then, after getting the key for the cache, reverts `kwargs` back to original.

        If a key-worded arg corresponding to any key in `to_tuple_keys` is not a tuple,
        it will raise ArgsUnhashable, mimicing source code behavior and preventing the
        caching mechanism from taking place.

        IMPORTANT NOTE: any of the key-worded arg corresponding to a key in
        `to_tuple_keys` will be consumed by call to `tuple(iter(ITERABLE))`. Thus, do
        not pass on iterables that are only once consumable.

        Args:
            to_ignore_keys (list): list of keys corresponding to key-worded args that
                need to be ignored when key for function parameters are extracted
            to_tuple_keys (list): list of keys corresponding to key-worded args that
                need to be converted to tuple when key for function parameters are
                extracted
        """
        removed_kwargs = {}
        for to_ignore_key in to_ignore_keys:
            to_ignore_val = kwargs.pop(to_ignore_key, None)
            if to_ignore_val is not None:
                removed_kwargs[to_ignore_key] = to_ignore_val
        for to_tuple_key in to_tuple_keys:
            to_tuple_val = kwargs.pop(to_tuple_key, None)
            if to_tuple_val is not None:
                removed_kwargs[to_tuple_key] = to_tuple_val
                try:
                    kwargs[to_tuple_key] = tuple(iter(to_tuple_val))
                except TypeError:
                    # was not a valid iterable
                    raise ArgsUnhashable() from ArgsUnhashable

                if len(kwargs[to_tuple_key]) > 10_000:
                    # too big to hash
                    raise ArgsUnhashable() from ArgsUnhashable

        key = super()._decorator_key(func, *args, **kwargs)

        # when the function is actually called, we want all of the original parameters
        kwargs.update(removed_kwargs)

        return key


def no_cache(*args, **kwargs):
    """Function to use as @redis_cache decorator when GENRA_NO_LRU_CACHE=1"""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        # assume bare @redis_ache
        return args[0]  # unmodified function

    def null_decorator(function):
        return function

    return null_decorator
