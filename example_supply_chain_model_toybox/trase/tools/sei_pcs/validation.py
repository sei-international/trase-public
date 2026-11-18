from dataclasses import dataclass
import typing

import pandas as pd

from trase.tools.sei_pcs.pandas_utilities import pretty_summarise
from trase.tools.sei_pcs.validation_base import Validation


class ValidationError(Exception):
    pass


@dataclass
class Code(Validation):
    """
    Has to be a string of a predefined length containing only digits, like "030211".

    Example:
        ```
        Code(6)
        ```

    Args:
        allow_x: also permit "XXXXXX" (defaults to True).
    """

    length: int
    allow_x: bool = True

    def is_valid(self, values):
        correct_length = values.str.len() == self.length

        all_digits = values.str.isdigit()
        if self.allow_x:
            all_xs = values == "X" * self.length
            valid_characters = all_digits | all_xs
        else:
            valid_characters = all_digits

        return correct_length & valid_characters


@dataclass
class Enum(Validation):
    """
    Must take one of a set of pre-defined values.

    Example:
        ```
        Enum(["SOLVED", "UNSOLVED"])
        ```
    """

    permitted: typing.List

    def is_valid(self, values):
        return values.isin(self.permitted)


@dataclass
class Value(Validation):
    """
    Must match a single value

    Example:
        ```
        Value("UNKNONWN")
        ```
    """

    value: typing.Any

    def is_valid(self, values):
        return values == self.value


class IsNonNegative(Validation):
    """
    Must be non-negative
    """

    def is_valid(self, values):
        return values >= 0


class Any(Validation):
    """
    Combine other validation functions

    Example:
        ```
        Any(Code(6), Code(8))  # accept codes that are length six *or* eight
        ````
    """

    def __init__(self, first_child: Validation, *other_children: Validation):
        self.first_child = first_child
        self.other_children = other_children

    def is_valid(self, values):
        valid = self.first_child.is_valid(values)
        for child in self.other_children:
            valid |= child.is_valid(values)
        return valid


def run_validation(
    df: pd.DataFrame, validation: typing.Dict[str, typing.Iterable[Validation]]
):
    errors = []
    for column, validations in validation.items():
        if validations is not None:
            values = df[column]
            for validator in validations:
                valid = validator.is_valid(values)
                if not all(valid):
                    invalid_values = values[~valid].unique()
                    pretty = pretty_summarise(invalid_values, prefix="\t")
                    errors.append(f"Column '{column}' failed validation:\n{pretty}")

    if errors:
        raise ValidationError("\n".join(errors))
