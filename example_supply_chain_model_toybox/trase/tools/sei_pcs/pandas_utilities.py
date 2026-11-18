"""
Useful functions that utilise Pandas with the goal of (a) reducing code repetition and
(b) minimising common errors.
"""

import inspect
import textwrap
from contextlib import contextmanager
from fnmatch import fnmatchcase
from functools import partial, wraps
from logging import getLogger
from typing import Dict, Iterable, List, Optional, Union
from unittest.mock import patch

import numpy as np
import pandas as pd
import scipy.spatial.distance
from pandas.testing import assert_frame_equal

from trase.tools.etl.utilities import consolidate
from trase.tools.sei_pcs.constants import ID
from trase.tools.sei_pcs.formatting import format_float
from trase.tools.utilities.iterables import rollup_by_keys

LOGGER = getLogger(__name__)


def to_nested_dict(df, columns, leaf_key, one=False) -> dict:
    return rollup_by_keys(df.to_dict(orient="records"), columns, leaf_key, one)


def select_minimum(df, by, on, include_id=True):
    if include_id and ID not in by:
        by = [*by, ID]

    cheapest = df.groupby(by)[on].idxmin()
    return df.loc[cheapest]


def full_merge(*args, how="outer", indicator=False, **kwargs):
    """Performs a Pandas merge but adds an additional check that no keys are missing.

    Suppose that we have two dataframes, df_production and df_demand

        df_production:                    df_demand:

          name  | production               name  | demand
        --------+-----------             --------+-------
         BALDIM |         16              BALDIM |     16
         CAXIAS |         73              CAXIAS |     34
         ...    |        ...              ...    |    ...
         PALMAS |        109              PALMAS |     46
         URUOCA |        121              URUOCA |     47

    Suppose that we wish to merge production and demand together. Our model expects that
    merge keys present in the left are present in the right and vice-versa. However,
    how do we assert this in code? If we don't assert it, we might accidentally lose
    rows.

    This function is a wrapper around `pd.merge` that will raise an error if any keys
    are missing on the left or the right.

    The behaviour depends on the value of the `how` parameter:

     - `how="outer"`: error if any keys in the left are not present in the right and
        vice-versa
     - `how="left"`: error if any keys in the left are not present in the right
     - `how="right"`: error if any keys in the right are not present in the left
     - `how="inner"`: behaviour will match that of `pd.merge`.

    All arguments are passed to `pd.merge`.

    Example:

    ```python
    # let's make two dataframes with keys that don't match
    df_a = pd.DataFrame({"name": ["POMBAL"]})
    df_b = pd.DataFrame({"name": ["PALMAS"]})

    # pandas merge (defaulting to how=inner) will return an empty dataframe
    df = pd.merge(df_a, df_b)
    df.is_empty  # True

    # full_merge (defaulting to how=outer) will raise an error
    full_merge(df_a, df_b)  # ValueError: Not all merge keys match:
                            #    name      _merge
                            #  POMBAL   left_only
                            #  PALMAS  right_only
    ```
    """
    merge_column = indicator if isinstance(indicator, str) else "_merge"
    df = pd.merge(*args, indicator=indicator or True, how=how, **kwargs)

    df_bad = None
    if how == "outer":
        df_bad = df[df[merge_column] != "both"]
    elif how == "left":
        df_bad = df[df[merge_column] == "left_only"]
    elif how == "right":
        df_bad = df[df[merge_column] == "right_only"]

    if df_bad is not None and not df_bad.empty:
        pretty = pretty_summarise(df_bad)
        raise ValueError(f"Not all merge keys match:\n{pretty}")

    return df if indicator else df.drop(columns=[merge_column])


def pivot(df, index: List, column: str, value: str, agg="sum"):
    """
    A version of ``pandas.DataFrame.pivot`` which allows a list of index names, a
    feature only added in Pandas > 1.1.0. Once we upgrade Pandas we can delete this
    function
    """
    return df.groupby([column, *index])[value].agg(agg).unstack(column).fillna(0)


def select_subset(df, subset):
    exact_matches = [column for column in subset if "*" not in column]
    wildcard_matches = [
        column
        for column in df.columns
        if column not in exact_matches
        and any(fnmatchcase(column, pattern) for pattern in subset)
    ]
    return df[[*exact_matches, *wildcard_matches]]


def rename(df, columns):
    return df.rename(columns=columns, errors="raise")


def split_dataframe_using_proportions(
    df: pd.DataFrame,
    df_proportions: pd.DataFrame,
    values: List[str],
    on: List[str],
    by: str,
    where=None,
    validate=None,
) -> pd.DataFrame:
    # filter dataset according to functors
    where = where or {}
    for column, functor in where.items():
        df = df[df[column].apply(functor)]
    df = df.drop(
        columns=[c for c in where if c not in values and c not in on], errors="raise"
    )

    # validate columns
    common = set(df).intersection(set(df_proportions))
    bad = common - set(values) - set(on)
    if bad:
        raise ValueError(
            "DF and DF_PROPORTIONS have columns in column that are neither in ON nor "
            f"VALUES: {', '.join(list(bad))}"
        )
    overlapping = common - set(on)
    if overlapping:
        raise ValueError(f"Unexpected columns present in both datasets: {overlapping}")

    # validate proportions add to one
    if any(~np.isclose(df_proportions.groupby(on)[by].sum().astype(float), 1)):
        raise RuntimeError(
            "Some proportions do not add to one, resulting in an unexpected loss or gain"
        )

    # apply proportions
    df = pd.merge(df, df_proportions, on=on, validate=validate)
    for value in values:
        df[value] *= df[by]
    return df


def grouped_proportion(
    df, numerical_column: str, categorical_columns: List[str]
) -> pd.Series:
    """Calculates the proportion of some numerical value relative to a group.

    For example, given the following dataframe ``df``:

        | company | province | vol
        | BIFFI   | ASCOPE   | 100
        | ARVUT   | ASCOPE   | 300
        | ARVUT   | PUNO     | 500

    Calling ``grouped_proportion(df, "vol", ["province"])`` would return:

        |  vol |
        | 0.25 |
        | 0.75 |
        | 1.00 |

    because 0.25 = 100 / (100 + 300), 0.75 = 300 / (100 + 300), and 1.00 = 500 / 500.
    The function returns a ``pd.Series`` with the same index as the dataframe so that it
    can be used to add a column:

    ```python
    df["proportion"] = grouped_proportion(df, "vol", ["province"])
    ```

    Args:
      numerical_column: string name of the numerical column, for eaxmple "vol"
      categorical_columns: list of one or more categorical columns that will be
        considered to define the "groups"
    """
    group_sum = df.groupby(categorical_columns)[numerical_column].transform("sum")
    return df[numerical_column] / group_sum


def concat(dfs, *args, sort=False, ignore_index=True, **kwargs):
    """Some useful defaults for concatenating two dataframes together.

    In particular:

    - Do not sort the dataframes.
    - Ignore indexes: we assume the indexes carry not useful information.
    - Validate that all dataframes have the same columns. Because NaNs are really
        annoying in Pandas.
    """
    dfs = list(dfs)
    columns = set(tuple(sorted(df.columns)) for df in dfs)
    if len(columns) != 1:
        raise ValueError("Some dataframes have different columns to others")
    # Drop empty/all-NA frames to preserve legacy dtype inference in concat.
    dfs_non_empty = [df for df in dfs if df.size > 0 and df.notna().any().any()]
    if not dfs_non_empty:
        # Avoid concat warning; return an empty frame with the expected columns.
        return dfs[0].head(0).copy()

    # Remove columns that are all-NA within each frame to avoid concat warnings,
    # then restore fully-all-NA columns after concat.
    all_na_cols_per_df = [
        {col for col in df.columns if not df[col].notna().any()} for df in dfs_non_empty
    ]
    all_na_cols_everywhere = set.intersection(*all_na_cols_per_df)
    dfs_trimmed = [
        df.drop(columns=list(all_na_cols), errors="ignore")
        for df, all_na_cols in zip(dfs_non_empty, all_na_cols_per_df)
    ]
    result = pd.concat(
        dfs_trimmed, *args, sort=sort, ignore_index=ignore_index, **kwargs
    )
    if all_na_cols_everywhere:
        for col in all_na_cols_everywhere:
            result[col] = pd.Series([pd.NA] * len(result), dtype=dfs[0][col].dtype)
        result = result.reindex(columns=list(dfs[0].columns))
    return result


class Compare:
    @staticmethod
    def signed_symmetric_relative_error(a, b):
        """
        Implements the below function, where division by zero is +/- infinity:

              |b| - |a|
            -------------
            min(|a|, |b|)

        The motivation for this comparator is to meaningfully handle zero values in
        either a or b: positive infinity means that a is zero but there is a value in b,
        and negative infinity means that a has a value but b is zero.

        Example:

            signed_symmetric_relative_error( 10,  10)  #  0
            signed_symmetric_relative_error(250, 100)  # -1.5
            signed_symmetric_relative_error(100, 250)  #  1.5
            signed_symmetric_relative_error(100,   0)  # -inf
            signed_symmetric_relative_error(0,   100)  #  inf
        """
        a = np.abs(a)
        b = np.abs(b)
        return (b - a) / np.minimum(a, b)

    @staticmethod
    def signed_total_relative_error(a, b):
        """
        Implements the below function:

            |b| - |a|
            ---------
            sum(|a|)

        The original use case for this comparator was to get the difference in volumes
        exported to e.g. China _relative to the entire export volume for the year_.
        """
        a = np.abs(a)
        b = np.abs(b)
        return (b - a) / sum(a)

    @classmethod
    def absolute_symmetric_relative_error(cls, a, b):
        return np.abs(cls.signed_symmetric_relative_error(a, b))

    @staticmethod
    def absolute_error(a, b):
        """The function `|b| - |a|`"""
        return np.abs(b) - np.abs(a)

    @staticmethod
    def l1_distance(a, b):
        return np.linalg.norm(b - a, ord=1)

    @staticmethod
    def l2_distance(a, b):
        return np.linalg.norm(b - a, ord=2)

    @staticmethod
    def cosine_similarity(a, b):
        return scipy.spatial.distance.cosine(a, b)

    @staticmethod
    def relative_error(a, b):
        """Implements the function:

            b - a
            -----
             |a|

        Note that this function will be undefined for zero and near-zero values of a
        """
        return (b - a) / np.abs(a)


def compare_dataframes_single(
    df_a,
    df_b,
    value: str,
    group_by: Optional[Iterable[str]] = None,
    comparator=Compare.signed_symmetric_relative_error,
    column="comparison",
    suffixes=("_a", "_b"),
    sort_absolute=True,
    sort="ascending",
    factor=1,
) -> pd.DataFrame:
    """
    A wrapper around ``trase.tools.sei_pcs.pandas_utilities.compare_dataframes`` which:

     1. Takes just one value column
     2. Renames the comparison column
     3. Sorts dataframe for you

    The intention is that the return value is slightly easier to use since columns only
    have one level, and it performs sorting for you (which is usually what you want).

    Example:

        >>> compare_dataframes_single(df_a, df_b, "volume", ["exporter"])
                  total_a  total_b  comparison
        exporter
           BUNGE      100      200         1.0
         CARGILL      500        0        -inf

    Args:
        value: the column which will be compared numerically
        group_by: columns over which to group
        comparator: a function which takes two series and returns their comparison.
            You can also pass in the string name of a method on
            ``trase.tools.sei_pcs.pandas_utilities.Compare``. See
            ``trase.tools.sei_pcs.pandas_utilities.Compare`` for some examples.
            Defaults to ``Compare.signed_symmetric_relative_error``
        column: the name of the comparison column. Defaults to "comparison"
        sort_absolute: whether to use absolute values as the sorting key. Defaults to
            True
        sort (optional): sorting order, either "ascending" (default) or "descending"
        factor (optional): multiply the comparison by a factor. The multiplication is
            done before any sorting occurs.

    Returns: a ``pd.DataFrame`` with the groups as the index. and three columns named
        (unless overridden) "total_a", "total_b", and "comparison"
    """
    if isinstance(comparator, str):
        comparator = getattr(Compare, comparator)

    df = compare_dataframes(df_a, df_b, {value: [comparator]}, group_by, suffixes)
    df.columns = [b for (_, b) in df.columns]
    df = df.rename(columns={comparator.__name__: column}, errors="raise")

    df[column] *= factor
    sort_by = df[column]
    if sort_absolute:
        sort_by = sort_by.abs()

    index = sort_by.argsort()
    if sort == "descending":
        index = index[::-1]
    elif sort != "ascending":
        raise ValueError("Sort must be 'ascending' or 'descending'")
    return df.iloc[index]


def compare_dataframes(
    df_a,
    df_b,
    comparators: Dict[str, List],
    group_by: Optional[Iterable[str]] = None,
    suffixes=("_a", "_b"),
) -> pd.DataFrame:
    """
    Compares two dataframes. Before comparison, the dataframes are aggregated via
    summation. Missing rows in either dataframe are filled with zero before comparison.

    Args:
        comparators: A dictionary of {value_column: compare_methods}.
            value_column: str, The column which will be compared numerically. It will
                be summed over the group_by columns. The column must exist in both
                dataframes
            compare_methods: a list of Compare functions, which take two series and
                returns their comparison. You can also pass in the string name of a
                method on ``trase.tools.sei_pcs.pandas_utilities.Compare``. See
                ``trase.tools.sei_pcs.pandas_utilities.Compare`` for some examples.
        group_by: A list of columns to group the dataframes by during aggregation. The
            columns must exist in both dataframes.
        suffixes: how to suffix the two value columns, defaults to "_a" and "_b".
    """
    comparators = {
        value_column: [getattr(Compare, c) if isinstance(c, str) else c for c in cs]
        for (value_column, cs) in comparators.items()
    }

    if group_by is None:
        all_columns = set(df_a.columns) | set(df_b.columns)
        comparator_columns = set(comparators.keys())
        group_by = list(all_columns - comparator_columns)

    group_by = list(group_by)
    suffix_a, suffix_b = suffixes

    df_a = consolidate(df_a, comparators.keys(), group_by, reset_index=False)
    df_b = consolidate(df_b, comparators.keys(), group_by, reset_index=False)
    df = pd.merge(
        df_a,
        df_b,
        left_index=True,
        right_index=True,
        how="outer",
        suffixes=suffixes,
        validate=None,
    )

    data = {}
    for value_column, compare_methods in comparators.items():
        values_a = df[f"{value_column}{suffix_a}"].fillna(0)
        values_b = df[f"{value_column}{suffix_b}"].fillna(0)

        data[(value_column, f"total{suffix_a}")] = values_a
        data[(value_column, f"total{suffix_b}")] = values_b

        for compare in compare_methods:
            data[(value_column, compare.__name__)] = compare(values_a, values_b)

    return pd.DataFrame(data, index=df.index, columns=pd.MultiIndex.from_tuples(data))


def stitch_dataframes(
    df_left,
    df_right,
    volume_column: str,
    values_left: List = None,
    values_right: List = None,
    fillna="UNKNOWN",
    indicator=False,
):
    """
    Merge dataframes on common columns, splitting the values in ``values_left``
    and ``value_right`` according to proportions in ``volume_column``.

    ```python
    df_left = pd.DataFrame(
        [
            ("K1", "M1", 10, 55, "good"),
            ("K2", "M1", 5, 32, "great"),
            ("K1", "M2", 2.5, 11, "awesome"),
            ("K2", "M2", 3, 19.2, "awful"),
        ],
        columns=["kab", "mill", "vol", "deforestation", "quality"],
    )

    df_right = pd.DataFrame(
        [
            ("M1", "T1", "C1", 8, 853, 3),
            ("M1", "T2", "C2", 8, 732, 5),
            ("M2", "T1", "C1", 1, 97, 3),
            ("M2", "T2", "C3", 4, 333, 5),
        ],
        columns=["mill", "exporter", "country", "vol", "fob", "forest_500"],
    )

    df = stitch_dataframes(
        df_left,
        df_right,
        volume_column="vol",
        values_left=["deforestation"],
        values_right=["fob"],
    )
    ```
    """
    values_left = values_left or []
    values_right = values_right or []

    values_both = [value for value in values_left if value in values_right]
    if values_both:
        raise ValueError(
            f"'value_left' and 'value_right' cannot have elements in common ({values_both})"
        )

    df_left = df_left[df_left[volume_column] > 0]
    df_right = df_right[df_right[volume_column] > 0]

    df_1 = df_left.copy()
    df_2 = df_right.copy()

    df_1 = consolidate(df_1, numerical_columns=values_left + [volume_column])
    df_2 = consolidate(df_2, numerical_columns=values_right + [volume_column])

    common = [
        column
        for column in set(df_1)
        if column in set(df_2) and column != volume_column
    ]

    # Note: change of behavior probably related to new version of Pandas
    # required to explicitly take subset of interest of dataframe before groupby
    df_1_common_sum = (
        df_1[common + [volume_column]]
        .groupby(common, dropna=False)
        .agg({volume_column: "sum"})
        .reset_index()
    )
    df_2_common_sum = (
        df_2[common + [volume_column]]
        .groupby(common, dropna=False)
        .agg({volume_column: "sum"})
        .reset_index()
    )

    # identify fraction of volume that can be matched to other dataframe
    df_matchability = pd.merge(
        df_1_common_sum,
        df_2_common_sum,
        on=common,
        suffixes=["_1", "_2"],
        how="outer",
        validate=None,
    ).fillna(0)

    df_matchability["fraction_2"] = df_matchability.apply(
        lambda row: (
            min(row[volume_column + "_1"] / row[volume_column + "_2"], 1)
            if row[volume_column + "_2"] != 0
            else 1
        ),
        axis=1,
    )
    df_matchability["fraction_1"] = df_matchability.apply(
        lambda row: (
            min(row[volume_column + "_2"] / row[volume_column + "_1"], 1)
            if row[volume_column + "_1"] != 0
            else 1
        ),
        axis=1,
    )
    df_matchability = pd.concat([df_matchability] * 2)
    df_matchability["matchable"] = df_matchability.duplicated()
    df_matchability.loc[df_matchability["matchable"] == False, "fraction_2"] = (
        1 - df_matchability.loc[df_matchability["matchable"] == False, "fraction_2"]
    )
    df_matchability.loc[df_matchability["matchable"] == False, "fraction_1"] = (
        1 - df_matchability.loc[df_matchability["matchable"] == False, "fraction_1"]
    )

    # split dataframes into matchable and unmatchable parts
    df_1 = split_dataframe_using_proportions(
        df_1,
        df_matchability,
        on=[column for column in set(df_1) if column in set(df_matchability)],
        values=values_left + [volume_column],
        by="fraction_1",
    )

    df_1 = df_1.drop(
        columns=[volume_column + "_1", volume_column + "_2", "fraction_1", "fraction_2"]
    )

    df_1_unmatchable = df_1.loc[(~df_1["matchable"]) & (df_1[volume_column] > 0.000001)]

    df_1 = df_1.loc[(df_1["matchable"]) & (df_1[volume_column] > 0)]

    df_2 = split_dataframe_using_proportions(
        df_2,
        df_matchability,
        on=[column for column in set(df_2) if column in set(df_matchability)],
        values=values_right + [volume_column],
        by="fraction_2",
    )

    df_2 = df_2.drop(
        columns=[volume_column + "_1", volume_column + "_2", "fraction_1", "fraction_2"]
    )

    df_2_unmatchable = df_2.loc[(~df_2["matchable"]) & (df_2[volume_column] > 0.000001)]

    df_2 = df_2.loc[(df_2["matchable"]) & (df_2[volume_column] > 0)]

    df_1_copy = df_1.copy()
    df_2_copy = df_2.copy()

    df_1["proportions"] = grouped_proportion(df_1, volume_column, common)
    df_1.pop(volume_column)

    df = split_dataframe_using_proportions(
        df_2,
        df_1,
        on=common + ["matchable"],
        values=values_right + [volume_column],
        by="proportions",
    )
    df.pop("proportions")
    for column in values_right:
        df_2.pop(column)
    for column in values_left:
        df.pop(column)

    df_1 = df_1_copy
    df_2 = df_2_copy

    common = [
        column
        for column in set(df_2)
        if column in set(df_1) and column != volume_column
    ]

    df_2["proportions"] = grouped_proportion(df_2, volume_column, common)
    df_2.pop(volume_column)

    df_2 = split_dataframe_using_proportions(
        df_1, df_2, on=common, values=values_left + [volume_column], by="proportions"
    )
    df_2.pop("proportions")
    for column in values_left:
        df_1.pop(column)
    for column in values_right:
        df_2.pop(column)

    common = [
        column for column in set(df_2) if column in set(df) and column != volume_column
    ]

    df = pd.merge(df, df_2, on=common, validate=None)
    df[volume_column] = df[volume_column + "_x"]

    df.pop(volume_column + "_x")
    df.pop(volume_column + "_y")

    if indicator:
        df["_matched"] = "both"
        df_1_unmatchable["_matched"] = "left_only"
        df_2_unmatchable["_matched"] = "right_only"

    df = pd.concat([df, df_1_unmatchable, df_2_unmatchable], sort=True)

    if fillna:
        df = df.fillna(fillna)

    if indicator:
        df = df.drop(columns="matchable")
    else:
        df = df.rename(columns={"matchable": "matched"})

    return df


def prefix_columns(df, prefix="", suffix=""):
    return df.rename(
        columns={c: f"{prefix}{c}{suffix}" for c in df.columns}, errors="raise"
    )


def assert_frame_like(a, b, **kwargs):
    """Assert two dataframes are equal, ignoring row and column order and index.

    Note: this is stronger than ``pandas.testing.assert_frame_equal(..., check_like=True)``
    — ``check_like`` only reindexes by index/column *labels*, whereas this helper
    sorts both row order (by all column values) and column order before comparing.
    """
    assert_frame_equal(
        a[sorted(a.columns)].sort_values(sorted(a.columns)).reset_index(drop=True),
        b[sorted(b.columns)].sort_values(sorted(b.columns)).reset_index(drop=True),
        **kwargs,
    )


def group_by_and_zip(df_a, df_b, on):
    df_a = df_a.sort_values(by=on)
    df_b = df_b.sort_values(by=on)
    assert_frame_like(df_a[on].drop_duplicates(), df_b[on].drop_duplicates())
    for (group, sub_df_a), (_, sub_df_b) in zip(df_a.groupby(on), df_b.groupby(on)):
        yield group, sub_df_a, sub_df_b


def append(df: pd.DataFrame, items) -> pd.DataFrame:
    return pd.concat([df, items], ignore_index=True, verify_integrity=True)


def cartesian_product(df_a, df_b, suffixes=("_x", "_y")) -> pd.DataFrame:
    """Returns the Cartesian product of two dataframes.

    For example, given the following two dataframes

        | foo |    | bar |
        |-----|    |-----|
        | a   |    | 1   |
        | b   |    | 2   |

    The Cartesian product would be:

        | foo | bar |
        |-----|-----|
        | a   | 1   |
        | a   | 2   |
        | b   | 1   |
        | b   | 2   |

    The returned dataframe will always have len(df1) * len(df2) rows. In the example
    above both dataframes have only one column, but this is not a requirement.

    Args:
        suffixes: suffixes which will be applied to columns which appear in both
            dataframes

    Note: this function is superceded in Pandas 1.2+ as pd.merge(how="cross")
    """

    # give both dataframes a column with exactly matching values
    if "_key" in [*df_a.columns, *df_b.columns]:
        raise ValueError('The column "_key" cannot appear in either dataframe')

    df_a = df_a.assign(_key=1)
    df_b = df_b.assign(_key=1)

    # merging on that column performs a cartesian product
    df = pd.merge(df_a, df_b, on="_key", suffixes=suffixes, validate=None)

    # discard the column before returning to user
    return df.drop(columns="_key", errors="raise")


def grouped_cartesian_product(
    df_a, df_b, common: List[str], suffixes=("_x", "_y")
) -> pd.DataFrame:
    """Like ``cartesian_product``, but merging on some common columns"""
    return concat(
        pd.merge(sub_df_a, sub_df_b, on=common, suffixes=suffixes, validate=None)
        for group, sub_df_a, sub_df_b in group_by_and_zip(df_a, df_b, on=common)
    )


def pretty_summarise(
    obj: Union[pd.DataFrame, pd.Series, Iterable],
    index=False,
    max_rows=5,
    length=True,
    prefix="",
) -> str:
    """Returns the the top five values of an iterable, along with the number of items.
    This is useful for printing a potentially long list of items.

    Example:
        >>> text = pretty_summarise([
        ...     "Berlin", "Frankfurt", "Heidelberg", "Munich", "Hamburg", "Bremen"
        ... ])
        >>> print(text)
            Berlin
         Frankfurt
           ...
           Hamburg
            Bremen
        Length: 6

    Args:
        obj: a Pandas dataframe, Pandas series, or iterable of any kind
        index (bool, optional): whether to print the index of the Pandas object
            (default: False)
        max_rows (int, optional): number rows to print before collapsing with "..."
            (default: 5)
        length (bool, optional): whether to print the total number of rows in the object
            (default: True)

    Returns: a string representation of the pretty-printed object
    """
    if isinstance(obj, pd.DataFrame):
        kwargs = dict(index=index, max_rows=max_rows, show_dimensions=length)
    else:
        obj = pd.Series(obj)
        kwargs = dict(index=index, max_rows=max_rows, length=length)
    text = obj.to_string(**kwargs)
    return textwrap.indent(text, prefix) if prefix else text


def set_pandas_display(
    rows=None,
    columns=None,
    float_format=None,
    precision: int = None,
    significant_digits=None,
):
    """Alters the display settings that Pandas uses to pretty-print dataframes.

    When this function is called the setting will be altered globally for the current
    Python session. To alter a setting temporarily use
    ``trase.tools.sei_pcs.pandas_utilities.pandas_display_context`` instead.

    Example:
        ```
        pd.set_pandas_display(rows=100)
        print(df)  # up to 100 rows will be printed
        ```

    Args:
        rows (int, optional): the maximum number of rows to print before truncating them
        columns (int, optional): the maximum number of columns to print before truncating
            them
        float_format (callable, optional): a function that takes a floating-point number
            and returns a string representation
        precision (int, optional): floating-point output precision in terms of number of
            places after the decimal
        significant_digits (int, optional): number of significant figures to print a
            floating-point number to. This setting will be ignored if float_format is
            supplied
    """
    for option, value in _pd_display(
        rows, columns, float_format, precision, significant_digits
    ).items():
        pd.set_option(option, value)


def pandas_display_context(
    rows=None,
    columns=None,
    float_format=None,
    precision: int = None,
    significant_digits=None,
):
    """Temporarily alters the display settings that Pandas uses to pretty-print
    dataframes.

    Example:
        ```
        with pd.pandas_display_context(rows=100):
           print(df)  # up to 100 rows will be printed

        print(df)  # setting has now been reset to the previous value
        ```

    Args:
        rows (int, optional): the maximum number of rows to print before truncating them
        columns (int, optional): the maximum number of columns to print before truncating
            them
        float_format (callable, optional): a function that takes a floating-point number
            and returns a string representation
        precision (int, optional): floating-point output precision in terms of number of
            places after the decimal
        significant_digits (int, optional): number of significant figures to print a
            floating-point number to. This setting will be ignored if float_format is
            supplied
    """
    settings: dict = _pd_display(
        rows, columns, float_format, precision, significant_digits
    )
    return pd.option_context(*(a for (k, v) in settings.items() for a in (k, v)))


def _pd_display(
    rows=None, columns=None, float_format=None, precision=None, significant_digits=None
) -> dict:
    ret = {}
    if rows:
        ret["display.max_rows"] = rows
        ret["display.min_rows"] = rows
    if columns:
        ret["display.max_columns"] = columns
    if significant_digits:
        ret["display.float_format"] = partial(
            format_float, significant_digits=significant_digits
        )
    if float_format:
        ret["display.float_format"] = float_format  # overrides setting above!
    if precision:
        ret["display.precision"] = precision
    return ret


@contextmanager
def warnings_if_pd_merge_called_without_validate():
    signature = inspect.signature(pd.merge)

    unpatched = pd.merge

    @wraps(pd.merge)
    def pd_merge(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if "validate" not in bound.arguments:
            try:
                caller = inspect.stack()[4]
                location = f"{caller.filename}:{caller.lineno}"
            except:
                # we failed to get the caller location. since the warning is pretty
                # useless without the location, just skip it
                pass
            else:
                LOGGER.warning(
                    f"Use the validate option with pd.merge or pass validate=None to "
                    f"suppress this warning\n{location}"
                )

        return unpatched(*args, **kwargs)

    with patch("pandas.merge", side_effect=pd_merge):
        yield
