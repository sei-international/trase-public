import sys

from termcolor import colored
from textwrap import indent


def print_message(message, level="info", end="\n", indent=0, color=None, attrs=None):
    if color is None:
        color = {"info": None, "warn": "yellow", "error": "red"}[level]
    with_color = colored(str(message), color=color, attrs=attrs)
    with_indent = indentify(with_color, count=indent)
    print(
        with_indent,
        end=end,
        file=sys.stderr if level in ["warn", "error"] else sys.stdout,
    )


def indentify(text, count=1):
    if count <= 0:
        return text
    else:
        intended = indent(text, prefix="\t")
        return indentify(intended, count - 1)
