import pandas as pd


def is_string_series(series: pd.Series) -> bool:
    """From https://stackoverflow.com/a/67001213"""
    if series.empty:
        return True
    elif isinstance(series.dtype, pd.StringDtype):
        # The series was explicitly created as a string series (Pandas>=1.0.0)
        return True
    elif series.dtype == "object":
        # Object series, check each value
        return all((v is None) or isinstance(v, str) for v in series)
    else:
        return False


def dataframe_contains_nulls(df: pd.DataFrame):
    return df.isnull().any().any()


def dataframe_columns_are_all_strings(df: pd.DataFrame) -> bool:
    return df.apply(is_string_series).all()
