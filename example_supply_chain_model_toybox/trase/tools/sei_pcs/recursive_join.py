"""
In order to reduce the amount of joins that a user has to do in their model code we
allow them to specify a recipe of joins that can be handled for them.

A typical example is that they might have a customs dataset with a column containing
geocodes of municipalities which they always want to be left-joined on to a dataset of
municipalities.

This module implements the above wishes into actual Panda merge operations with
user-friendly errors for when things go wrong. It also supports more deeply-nested
joining operations.
"""

from dataclasses import dataclass
from textwrap import indent
from typing import Dict, Tuple

import pandas as pd
from pandas.errors import MergeError

from trase.tools.sei_pcs.exceptions import LinkError


@dataclass
class Link:
    dataset: str
    column: str
    validate_only: bool = False


Links = Dict[str, Dict[str, Link]]
Dataframes = Dict[str, pd.DataFrame]


def recursive_join(
    dataset: str,
    dataframes: Dataframes,
    links: Links,
    copy=True,
    limit=100,
) -> pd.DataFrame:
    """Perform a "recursive join" for the given dataset.

    For example, given the dataframes:

    ```python
    dataframes = {
        "state": pd.DataFrame([
            {"code": 12, "name": "ACRE"},
            # ...
        ]),
        "municipality": pd.DataFrame([
            {"state": 12, "code": 1200302, "name": "FEIJO"},
            # ...
        ]),
    }
    ```

    We might specify the following links:

    ```python
    links = {
        "state": {},
        "municipality": Link("state", "code"),
    }
    ```

    That is to say: the "state" column of the "municipality" dataframe should be
    left-joined on to the "code" column of the "state" dataframe.

    We would perform such a join as follows:

    ```python
    recursive_join("municipality", dataframes, links)
    ```

    That would return the following dataframe

        | state.code | state.name |    code |  name |
        |------------|------------|---------|-------|
        | 12         | ACRE       | 1200302 | FEIJO |


    The above example is simple, but this method also implements deeply-nested links
    with many dataframes.

    Args:
      copy: if false and there are no joins to be made, a reference to the original
        dataframe in the dictionary will be returned. This can be a bit faster if you
        know you are not going to modify the return value.
      limit: the limit of recursive entries to this call before RecursionError is
        raised

    Raises:
      LinkError: if any left joins have missing or duplicated keys on the right.
      ValueError: if any of the targets of the links are themselves linked, for
        example dataset1.column1 left joins on dataset2.column2, but dataset2.column2
        also left joins on some dataset3.column3.
    """
    if limit < 0:
        raise RecursionError

    _raise_if_any_link_targets_are_links(links)
    _raise_if_any_link_targets_missing(dataframes, links)

    errors = []
    df = dataframes[dataset]
    column_targets = links[dataset].items()
    for column, target in column_targets:
        join_column = dot(column, target.column)
        df = _rename(df, {column: join_column})

        _links = links
        if target.validate_only:
            # since we are only interested in the target column, there is no need for
            # the target dataset to perform any of the joins it needs. We achieve this
            # by deleting any links in the target dataset
            _links = {**links, target.dataset: {}}

            # this assumes that the target column is not itself joined. At the time of
            # writing, this is already checked in a call at the top of this function.
            # However, just to be extra careful, we check it again here
            if target.column in links.get(target.dataset, {}):
                raise ValueError("Link targets cannot be themselves linked")

        df_target = recursive_join(target.dataset, dataframes, _links, copy, limit - 1)

        if target.validate_only:
            # filter down to only the target column: we don't want any of the other
            # columns
            df_target = df_target[[target.column]]

        df_target = _rename(df_target, {c: dot(column, c) for c in df_target.columns})

        left_pretty = f"{dataset}.{column}"
        right_pretty = f"{target.dataset}.{target.column}"

        try:
            df = _left_join(df, df_target, on=join_column)
        except MergeError as e:
            errors.append(f"Failed to merge {left_pretty} to {right_pretty}: {e}")
        except LinkError as e:
            pretty = indent(str(e), prefix="\t")
            errors.append(
                f"Some values of {left_pretty} are not in {right_pretty}:\n{pretty}"
            )

    if errors:
        raise LinkError("\n".join(errors))

    if copy and not column_targets:
        df = df.copy()

    return df


def _raise_if_any_link_targets_are_links(links: Links):
    """It _might_ be possible to support this, I just didn't do it yet"""
    if any(
        target.column in links[target.dataset]
        for targets in links.values()
        for target in targets.values()
    ):
        raise ValueError("Link targets cannot be themselves linked")


def _raise_if_any_link_targets_missing(dataframes, links: Links):
    empty = pd.DataFrame()
    if any(
        target.column not in dataframes.get(target.dataset, empty).columns
        for targets in links.values()
        for target in targets.values()
    ):
        raise ValueError("Missing link targets")


def dot(a, b):
    return f"{a}.{b}"


def prejoin(
    dataframes: Dataframes, links: Links, excluding
) -> Tuple[Dataframes, Links]:
    def split_dictionary(dictionary, keys):
        a = {key: dictionary[key] for key in keys}
        b = {key: value for (key, value) in dictionary.items() if key not in keys}
        return a, b

    excluded_dataframes, included_dataframes = split_dictionary(dataframes, excluding)
    excluded_links, included_links = split_dictionary(links, excluding)

    joined_dataframes = {}
    errors = []
    for name in included_dataframes:
        try:
            joined_dataframes[name] = recursive_join(
                name, included_dataframes, included_links
            )
        except (LinkError, ValueError) as e:
            errors.append(f"While joining {name}: {e}")
    if errors:
        raise LinkError("\n".join(errors))

    dataframes = {**joined_dataframes, **excluded_dataframes}
    links = {**excluded_links, **{name: {} for name in included_dataframes}}
    _raise_if_any_link_targets_missing(dataframes, links)
    return dataframes, links


def _left_join(left: pd.DataFrame, right: pd.DataFrame, on) -> pd.DataFrame:
    """
    Raises:
        LinkError: if there are missing keys on the right dataframe
        MergeError: if there are duplicated keys on the right dataframe
    """
    df = pd.merge(
        left, right, how="left", on=on, indicator=True, validate="many_to_one"
    )
    missing = df[on][df.pop("_merge") != "both"].drop_duplicates()
    if not missing.empty:
        raise LinkError(missing.to_string(index=False, max_rows=5, length=True))
    return df


def _rename(df: pd.DataFrame, columns: Dict[str, str]) -> pd.DataFrame:
    """shorthand for df_2.rename specific to the usage in this module"""
    return df.rename(columns=columns, errors="raise", copy=False)
