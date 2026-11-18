""" Utility functions for formatting Python numbers as strings """


def round_to_significant_digits(number: float, significant_digits: int) -> float:
    return float(("{:." + str(significant_digits) + "g}").format(number))


def format_float(number, significant_digits=None):
    if significant_digits is not None:
        number = round_to_significant_digits(number, significant_digits)
    return f"{number:,.0f}"
