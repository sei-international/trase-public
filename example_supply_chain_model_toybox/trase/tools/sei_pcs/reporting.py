"""
Some useful functions to summarise Pandas dataframes
"""

from functools import partial

import pandas as pd

from trase.tools.sei_pcs.formatting import format_float


def report_percentage_by_attribute(df, value_column, by) -> pd.DataFrame:
    """See `trase.tools.sei_pcs.reporting.print_report_by_attribute`"""
    total = df[value_column].sum()
    sums = df.groupby(by)[value_column].sum()
    report = pd.DataFrame({"sum": sums, "percentage": 100 * sums / total})
    return report.sort_values(by="percentage", ascending=False)


def print_report_by_attribute(
    df, value_column, by, significant_digits=2, printer=print
):
    """
    Prints a summary of a dataframe when consolidated over one or more categorical
    columns. The absolute numbers are included as well as a relative percentage.

    Example:
        >>> print_report_by_attribute(df, "vol", ["exporter"])
                             sum percentage
        exporter
        BUNGE      4,300,000,000        56%
        ADM        2,200,000,000        28%
        CARGILL    1,300,000,000        16%

    Args:
        value_column: the numerical column to add up. Only one column is supported
        by: the categorical column(s) to group over.
        significant_digits: number of significant digits to round the numbers to, or
            `None` if you do not want rounding to occur (default: 2).
        printer: a function which prints to the screen (default: `print`).
    """

    df = report_percentage_by_attribute(df, value_column, by)
    formatter = partial(format_float, significant_digits=significant_digits)
    printer(
        df.to_string(formatters={"sum": formatter, "percentage": lambda f: f"{f:.0f}%"})
    )
