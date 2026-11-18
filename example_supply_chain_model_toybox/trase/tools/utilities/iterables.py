"""
(DEPRECATED). Some useful functions that work on iterables, inspired by d3-array. Built
on top of itertools and more_itertools. This module is mostly useful for old-style
SEI-PCS models: new-style models are able to access the tools provided by Pandas.
"""

import itertools
from functools import partial
from typing import Callable, Iterable

import more_itertools


def group_by(
    iterable: Iterable,
    key_function: Callable,
    aggregation_function: Callable = list,
) -> dict:
    """A Python port of d3-array's groupby"""
    sorted_iterable = sorted(iterable, key=key_function)
    grouped = itertools.groupby(sorted_iterable, key=key_function)
    return {key: aggregation_function(list(items)) for (key, items) in grouped}


def rollup(
    iterable,
    key_functions: Iterable[Callable],
    aggregation_function: Callable = list,
) -> dict:
    """A Python port of d3-array's rollup"""

    def unpack(iterable_, key_functions_):
        key_function = key_functions_[0]
        remaining_key_functions = key_functions_[1:]

        def unpack_remaining(r):
            return unpack(r, remaining_key_functions)

        return group_by(
            iterable_,
            key_function,
            unpack_remaining if remaining_key_functions else aggregation_function,
        )

    return unpack(iterable, key_functions)


def rollup_by_keys(
    records: Iterable[dict], keys: Iterable, leaf_key, one=False
) -> dict:
    """Rollup function specifically for "records" (lists of dictionaries)"""

    def aggregation_function(records_):
        return (
            more_itertools.one(records_)[leaf_key]
            if one
            else [r[leaf_key] for r in records_]
        )

    def getitem(dictionary, key):
        # needed to get around the Python gotcha of late binding
        return dictionary[key]

    return rollup(
        records,
        key_functions=[partial(getitem, key=key) for key in keys],
        aggregation_function=aggregation_function,
    )
