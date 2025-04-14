"""Utility functions for celery task management"""

from itertools import islice


def batches(iterable, batch_size=10_000, max_batches=None):
    """Yields batch_size batches of items from iterable.

    ASSUMPTION: batch_size is low enough it's ok to make lists, not iterables, of
    batch_size items.

    Args:
        iterable (iterable): items to batch
        batch_size (int): batch size
        max_batches (int|None): yield only first max_batches batches, for dev. testing

    Yields:
        list: a batch
    """

    batch_i = 0
    # needs to be a consumable iterable, not re-usable like a list or a range
    iterable = iter(iterable)

    while max_batches is None or batch_i < max_batches:
        batch_i += 1
        # the fact that list() *consumes* batch_size items from iterable is important
        ans = list(islice(iterable, batch_size))
        if ans:
            yield ans
        else:
            return

        # This alternative is less safe, because it only consumes 1 item from iterable,
        # and relies on the caller to consume the rest, which the caller may fail to do.

        # batch = islice(iterable, batch_size)
        # # need to peek to see if anything left, verified 20210713 this returns
        # # expected total items
        # try:
        #     first = next(batch)
        # except StopIteration:
        #     return
        # yield chain([first], batch)
