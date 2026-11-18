import csv
import json
import warnings
from contextlib import contextmanager
from logging import getLogger
from math import isinf, isnan
from pathlib import Path
from textwrap import dedent
from typing import IO, AnyStr, Dict, List, Optional, Union, TypeVar

import numpy as np
import pandas as pd
from pandas.core.dtypes.common import (
    is_integer_dtype,
    is_float_dtype,
    is_bool_dtype,
    is_string_dtype,
)
from pandas.core.dtypes.inference import is_file_like

FilePathOrBuffer = Union[str, Path, IO[AnyStr]]
ERROR_ROW_LIMIT = 10
BYTES_FOR_CSV_SNIFFING = 16_894  # experimented and this seemed to work mostly...
BOOL_VALUES = {
    # Truthy
    "TRUE": True,
    "1": True,
    "True": True,
    "true": True,
    # Falsey
    "FALSE": False,
    "0": False,
    "False": False,
    "false": False,
}
LOGGER = getLogger(__name__)


class WellBehavedCSV:
    """
    Pandas and CSVs can do unexpected things. For example, how can you represent each of
    None, np.nan, and "" in a CSV? How can you write a number with a leading zero that
    doesn't get stripped on read?

    This class imposes a set of restrictions with the guarantee that if you
    deserialized a serialized DataFrame you will always recover exactly the original:

        write(df_2, location, types)
        df_2 == read(loaction, types)

    The restrictions are as follows:

        - Columns must be either str, float, int or bool type
        - None values are not allowed (but NaN is OK in non-string columns)
        - String columns may contain neither None nor NaN
        - No named or multi-level indexes are allowed (this isn't for any good reason,
            I just didn't spend the time understanding the behaviour of this)
    """

    Types = Dict[str, type]
    ALLOWED_DTYPES = [
        (str, np.object_),
        (float, np.float64),
        (float, np.float32),
        (int, np.int64),
        (int, np.int32),
        (bool, np.bool_),
    ]

    @classmethod
    def write(
        cls,
        df: pd.DataFrame,
        destination: FilePathOrBuffer,
        types: Optional[Types] = None,
    ):
        types = types or {}
        cls._raise_if_types_invalid(types)
        cls._raise_if_duplicated_column_names(df)
        cls._raise_if_dataframe_invalid(df, types)
        df.to_csv(destination, index=False, sep=";")

    @classmethod
    def read(
        cls, source: FilePathOrBuffer, types: Optional[Types] = None
    ) -> pd.DataFrame:
        types = types or {}
        cls._raise_if_types_invalid(types)
        try:
            df = cls.read_csv(source)
            return cls._cast_columns_to_dtypes(df, types)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    @classmethod
    def _raise_if_types_invalid(cls, types: Types):
        invalid_types = set(types.values()) - set(t for (t, _) in cls.ALLOWED_DTYPES)
        if invalid_types:
            pretty = ", ".join(f"'{t.__name__}'" for t in invalid_types)
            raise ValueError(f"types includes invalid type(s) {pretty}")

    @classmethod
    def _raise_if_duplicated_column_names(cls, df):
        duplicated_column_names = [
            column
            for column in df.columns
            if len([c for c in df.columns if c == column]) > 1
        ]
        if duplicated_column_names:
            raise ValueError(
                f"Column names are not unique: {', '.join(set(duplicated_column_names))}"
            )

    @classmethod
    def _raise_if_dataframe_invalid(cls, df, types: Types):
        errors = []

        # check that the columns have valid dtypes
        for column, dtype in df.dtypes.to_dict().items():
            # special checks for string columns
            series = df[column]
            if dtype == object:
                # the column could be just strings, or it could be of mixed type
                # this will be much simpler with Pandas 1.x's StringDType!
                # note: this will reject None and NaA for strings, which are
                # indistinguishable from the empty string when deserialized
                if any(series.map(type) != str):
                    errors.append(f"Column '{column}' contains mixed types")

            # check the dtype is consistent with the types dictionary
            # check dtypes are consistent with types dictionary
            python_type = types.get(column, str)
            python_type_name = python_type.__name__
            if (python_type, dtype.type) not in cls.ALLOWED_DTYPES:
                errors.append(
                    f"Mismatched or disallowed type: Column('{column}', "
                    f"type={python_type_name}) with Pandas type '{dtype}'"
                )

            # reject None as this is indistinguishable from NaN when deserialized
            if None in series.values:
                errors.append(f"Column '{column}' contains None")

        # check index is neither named nor multi-level
        index_names = list(df.index.names)
        if index_names != [None]:
            pretty = ", ".join(f"'{n}'" for n in index_names)
            errors.append(f"Expecting single anonymous index, received {pretty}")

        if errors:
            raise ValueError("\n".join(errors))

    @classmethod
    def _cast_columns_to_dtypes(cls, df, types) -> pd.DataFrame:
        for column in df.columns:
            python_type = types.get(column, str)
            if python_type != str:
                # empty values will have been read as empty string
                # however, for numeric columns we will have to make a choice: do we
                # interpret this as None or NaN? When we wrote the file we enforced
                # the latter, so that is what we choose here
                df[column] = df[column].replace("", np.nan)

            if python_type == bool:
                df[column] = df[column].map({"True": True, "False": False})
            else:
                df[column] = df[column].astype(python_type)
        return df

    @staticmethod
    def read_csv(source: FilePathOrBuffer):
        return pd.read_csv(
            source,
            delimiter=";",
            encoding="utf-8",
            dtype=str,
            keep_default_na=False,  # https://github.com/pandas-dev/pandas/issues/1657
        )


@contextmanager
def open_filepath_or_buffer(filepath_or_buffer):
    if is_file_like(filepath_or_buffer):
        yield filepath_or_buffer
    else:
        with open(filepath_or_buffer) as file:
            yield file


def read_json(source: FilePathOrBuffer, types: Dict) -> pd.DataFrame:
    """
    Loads a JSON file from disk. The JSON file must be in a row-wise layout:

        [
            {"my_column": 1},
            {"my_column": 2},
            ...
        ]

    The dictionary of *types* should map column names to their types. A column will only
    appear in the dataframe if it also appears in this mapping. Constructing typed
    Python objects is delegated to the ``json`` module. We do, however, reject
    Python's float NaN object and other esoteric float objects. Unlike ``pd.read_json``,
    types are strictly enforced (even more strictly than Python! For example, ``None``
    is not an acceptable value for a boolean). You can use the type ``object`` to skip
    validation for that column.

    Unlike ``pd.read_json`` we do not interpret certain "missing values" as NaNs (except
    for a float NaN interpreted as an ``object``).

    TODO explore combining validation and casting for clarity and performance
    """

    # ---------------------------------------------------------------------------------
    # Load data from JSON, filtering to the subset of columns
    # We also switch to column-layout for performance later
    # ---------------------------------------------------------------------------------
    with open_filepath_or_buffer(source) as file:
        data = json.load(file)

    columns = types.keys()
    data = {column: [row[column] for row in data] for column in columns}

    # ---------------------------------------------------------------------------------
    # Validate data
    # ---------------------------------------------------------------------------------
    numeric_types = (float, int)
    list_types = {
        List[str]: str,
        List[bool]: bool,
        List[int]: int,
        List[float]: float,
        List[object]: object,
    }

    def invalid(value, target_type):
        if target_type is object:
            return False

        allowed_instances = (
            numeric_types
            if target_type in numeric_types
            else list if target_type in list_types else target_type
        )

        return (
            # reject None
            value is None
            # reject mis-matched types
            or (not isinstance(value, allowed_instances))
            # reject nan
            or (target_type in numeric_types and isnan(value))
            # reject inf
            or (target_type in numeric_types and isinf(value))
            # reject lists with invalid items
            or (
                target_type in list_types.keys()
                and any(invalid(item, list_types[target_type]) for item in value)
            )
        )

    errors = []
    for column, target_type in types.items():
        if target_type is object:
            continue  # anything goes - skip for performance

        values = data[column]
        sample_bad_values = [
            value
            for i, value in enumerate(values)
            if invalid(value, target_type) and i < ERROR_ROW_LIMIT
        ]
        if sample_bad_values:
            pretty = "\n\t".join([str(v) for v in sample_bad_values])
            errors.append(
                dedent(
                    f"""
                    Some values in column '{column}' not '{target_type}':
                    {pretty}
                    (showing up to {ERROR_ROW_LIMIT} values)
                    """
                )
            )
    if errors:
        raise ValueError("\n".join(errors))

    # ---------------------------------------------------------------------------------
    # Cast columns of numeric data, or lists of numeric data
    # ---------------------------------------------------------------------------------

    def cast_numeric_types(values, target_type):
        if target_type in numeric_types:
            return [target_type(value) for value in values]
        elif target_type in list_types.keys():
            subtype = list_types[target_type]
            if subtype in numeric_types:
                return [[subtype(item) for item in value] for value in values]

        return values

    data = {
        column: cast_numeric_types(values, types[column])
        for column, values in data.items()
    }

    # ---------------------------------------------------------------------------------
    # Construct pandas dataframe
    # ---------------------------------------------------------------------------------
    return pd.DataFrame(data=data)


def read_csv(
    path_or_buffer,
    converters: Optional[dict],
    delimiter: Optional[str],
    quotechar,
    encoding,
    header="infer",
    skiprows=None,
):
    if not converters and converters is not None:
        return pd.DataFrame()

    if delimiter is None:
        delimiter = sniff_csv_delimiter(path_or_buffer, encoding)
        LOGGER.debug(f"Auto-detected {path_or_buffer} to have delimiter '{delimiter}'")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Falling back to the 'python' engine")
        LOGGER.debug(f"Calling pd.read_csv for {path_or_buffer}")
        df = pd.read_csv(
            path_or_buffer,
            usecols=None if converters is None else converters.keys(),
            keep_default_na=False,
            dtype=str,
            sep=delimiter,
            encoding=encoding,
            quotechar=quotechar,
            header=header,
            skiprows=skiprows,
        )

    if converters:
        LOGGER.debug("Casting dataframe columns to desired types")
        return cast_dataframe_to_types(df, converters)
    else:
        return df


def types_similar(dtype, python_type: TypeVar):
    if python_type is int:
        return is_integer_dtype(dtype)
    elif python_type is float:
        return is_float_dtype(dtype)
    elif python_type is bool:
        return is_bool_dtype(dtype)
    elif python_type is str:
        return is_string_dtype(dtype)
    else:
        LOGGER.warning(f"Unrecognised type {python_type}")
        return False


def sniff_csv_delimiter(path_or_buffer, encoding="utf8"):
    """
    Pandas is not very good at this, so we instead use the csv sniffer from Python's
    standard library. we run the sniffer on a sample of the file. if the object is
    buffer-like, then we'll need to be careful to reset it to the original location
    after read
    """
    if is_file_like(path_or_buffer):
        position = path_or_buffer.tell()
        sample = path_or_buffer.read(BYTES_FOR_CSV_SNIFFING)
        path_or_buffer.seek(position)
    else:
        with open(path_or_buffer, encoding=encoding) as file:
            sample = file.read(BYTES_FOR_CSV_SNIFFING)
    return csv.Sniffer().sniff(sample).delimiter


def read_excel(location, converters: dict):
    df = pd.read_excel(
        location,
        usecols=list(converters.keys()),
        keep_default_na=False,
        dtype=str,
        parse_dates=False,
    )
    return cast_dataframe_to_types(df, converters)


def cast_dataframe_to_types(df, converters):
    errors = []
    for column_name, python_type in converters.items():
        typename = python_type.__name__
        try:
            df[column_name] = _cast_series_to_type(df[column_name], python_type)
        except ValueError as e:
            errors.append(
                f"Some values of column '{column_name}' cannot be parsed as "
                f"{typename}:\n{e}"
            )
    if errors:
        raise ValueError("\n".join(errors))
    return df


def _cast_series_to_type(series, python_type):
    if python_type is float:
        return _cast_series_to_float(series)
    elif python_type is int:
        return _cast_series_to_float(series).astype(int)
    elif python_type is bool:
        return _cast_series_to_bool(series)
    else:
        return series


def _cast_series_to_float(series):
    new_series = pd.to_numeric(series, errors="coerce")
    errors = series[new_series.isna() | ~np.isfinite(new_series)].drop_duplicates()
    if not errors.empty:
        raise ValueError(errors.to_string(index=False, max_rows=5))
    return new_series.astype(float)


def _cast_series_to_bool(series):
    errors = series[~series.isin(BOOL_VALUES.keys())].drop_duplicates()
    if not errors.empty:
        if not errors.empty:
            raise ValueError(errors.to_string(index=False, max_rows=5))
    return series.map(BOOL_VALUES)
