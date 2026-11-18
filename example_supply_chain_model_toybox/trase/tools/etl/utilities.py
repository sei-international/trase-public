import hashlib
import io
import json
import os
from contextlib import contextmanager
from logging import getLogger
from time import time
from typing import Union, Iterable, Optional
from termcolor import colored

import pandas as pd

from trase.tools.etl import exceptions
from trase.tools.etl.exceptions import ValidationError
from trase.tools.utilities.messages import indentify

LOGGER = getLogger(__name__)


class Loggable:
    @property
    def logger(self):
        name = ".".join([__name__, self.__class__.__name__])
        return getLogger(name)

    def info(self, *args, **kwargs):
        self.logger.info(*args, **kwargs)

    def debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)

    def warning(self, *args, **kwargs):
        self.logger.warning(*args, **kwargs)


@contextmanager
def timing(msg="", threshold=5, indent=0):
    LOGGER.debug(msg)
    start = time()
    yield
    duration = time() - start
    if duration > threshold:
        print(
            indentify(
                colored(f"{msg} took {duration:.1f} seconds", color="white"),
                count=indent,
            )
        )


def validate(series, validation_function):
    validated_rows = series.apply(validation_function)
    if not all(validated_rows):
        invalid_rows = series[~validated_rows]
        raise ValidationError(
            f"{len(invalid_rows):,} values in column '{series.name}' fail validation\n"
            + indentify(str(invalid_rows))
        )


def consolidate(
    df: pd.DataFrame,
    numerical_columns: Iterable[str],
    categorical_columns: Optional[Iterable[str]] = None,
    reset_index=True,
):
    """
    Group a dataframe by one or more categorical columns and sum one or more numerical
    columns.

    Example:
        ```
        df = pd.DataFrame({
            "product": ["eggs", "eggs", "bacon"],
            "value":   [  1.99,  1.99,    5.99],
        })
        consolidate(df, ["value"], ["product"])
        # product   value
        #   bacon    5.99
        #    eggs    4.98
        ```
    """
    # infer categorical columns if they weren't supplied
    all_columns = df.columns
    numerical_columns = list(numerical_columns)  # evaluate iterable
    categorical_columns = (
        [col for col in all_columns if col not in numerical_columns]
        if categorical_columns is None
        else list(categorical_columns)  # evaluate iterable
    )

    # check the user didn't supply columns that don't exist
    chosen_columns = list(dict.fromkeys(numerical_columns + categorical_columns))
    unrecognised_columns = [col for col in chosen_columns if col not in all_columns]
    if unrecognised_columns:
        pretty = ", ".join(unrecognised_columns)
        raise ValueError(f"Unrecognised column(s) {pretty}")

    # check that a column isn't both numerical and categorical
    overlap = set(numerical_columns).intersection(set(categorical_columns))
    if overlap:
        pretty = ", ".join(overlap)
        raise ValueError(
            f"The following column(s) are specified as both numerical and "
            f"categorical: {pretty}"
        )

    # check for NaNs
    columns_with_nans = [c for c in categorical_columns if df[c].isna().any()]
    if columns_with_nans:
        pretty = ", ".join(columns_with_nans)
        raise ValueError(
            f"The following column(s) contain NaNs: {pretty}\n. This is a problem "
            f"because rows that contain NaNs will disppear during consolidation. Either "
            f"drop the rows with NaNs or replace the NaN values"
        )

    # perform group-and-sum
    df = (
        df[chosen_columns]
        .groupby(by=categorical_columns)
        .agg({column: "sum" for column in numerical_columns})
    )

    if reset_index:
        df = df.reset_index()
    return df


SeriesOrDataFrame = Union[pd.Series, pd.DataFrame]


def drop_rows_missing_values(df, *columns):
    for column in columns:
        df = df[~df[column].isin(["", "NA", "nan"])]
    return df.copy()


def hash_string(string) -> str:
    return hashlib.sha1(string.encode()).hexdigest()


def hash_iterable(iterable) -> str:
    h = hashlib.sha1()

    class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return json.JSONEncoder.default(self, obj)

    def update_hash(obj):
        if isinstance(obj, pd.Series):
            # DataFrame has to_parquet() but Series doesn't
            obj = pd.DataFrame(obj)

        if isinstance(obj, pd.DataFrame):
            # DataFrame must have string column names
            obj.columns = [str(c) for c in obj.columns]

        if hasattr(obj, "to_parquet"):
            buffer = io.BytesIO()
            obj.to_parquet(buffer)
            h.update(hashlib.sha1(buffer.getvalue()).digest())
        else:
            h.update(
                hashlib.sha1(json.dumps(obj, cls=DateTimeEncoder).encode()).digest()
            )

    for obj in iterable:
        try:
            update_hash(obj)
        except (TypeError, ValueError) as e:
            raise exceptions.HashFailure from e

    return h.hexdigest()


def dataset_path(data_directory, name) -> str:
    return os.path.join(data_directory, "prepared", f"{name}.csv")
