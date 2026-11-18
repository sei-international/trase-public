"""
General helper functions with examples.
"""

import importlib
import pkgutil
import re
import unicodedata
from collections import namedtuple
from typing import Dict, Iterable, Optional

from unidecode import unidecode

Kinship = namedtuple("Kinship", ["parent", "child"])
FamilyTree = Dict[Dict, "FamilyTree"]


def flatten(myl, results=None):
    """
    Takes a list of lists in the form [[X, dict]] and flattens the nested dictionary.

    E.g.,
    from pprint import pprint

    test_dict = {
        'A': {
            2: {
                3: ['a', 'b', 'c', 'd']
            }
        },
        'B': {
            12: {
                13: ['e', 'f']
            },
            14: {
                15: ['g', 'h'],
                16: ['p', 'm']
            }
        },
        'C': ['g', 'h', 'i', 'j']
    }

    print('\n' + '-' * 100 + '\ninitial:')
    pprint(test_dict)
    print('-' * 100 + '\n')
    final_result = flatten([['X', test_dict]])
    print('-' * 100 + '\nfinal:')
    pprint(final_result)
    print('-' * 100 + '\n')
    """
    assert isinstance(myl, list)
    if not results:
        results = []
    for nested_list in myl:
        hdr = []
        for el in nested_list:
            if isinstance(el, dict):
                nested = []
                for k in el:
                    nested.append(hdr + [k, el[k]])
                    results = flatten(nested, results=results)
            elif isinstance(el, list):
                for j in el:
                    final = hdr.copy() + [j]
                    if final not in results:
                        results.append(final)
            else:
                hdr.append(el)
    return results


def make_tree(parent_child_pairs: Iterable[Kinship]) -> FamilyTree:
    """Turns a list of parent-child relationships into a family tree represented as
    nested dictionaries. The value ``None`` implies a missing value:

        ```python
        Kinship(child="Xi", parent=None)  # parent-less child
        Kinship(child=None, parent="Xi")  # child-less parent
        ```

    A node without a parent is considered to be a root node. A node will also be
    considered a root node if it simply never appears as having a parent. A node without
    any childred is considered to be a leaf. For example, "Fred" below is a root node
    and "Bill" and "Jill" are leaf nodes:

        ```python
        parent_child_pairs=[
            Kinship(child="Bill", parent="Fred"),
            Kinship(child="Jill", parent="Fred"),
        ]
        ```

    The return value will consist of nested dictionaries. The ``parent_child_pairs``
    example from above would produce:

        ```python
        {
            "Fred": {
                "Bill": {},
                "Jill": {},
            }
        }
        ```

    Adapted from https://stackoverflow.com/a/45461474/1809078

    Raises:
        ValueError: if there is a circular reference
    """
    parent_child_pairs = list(parent_child_pairs)
    if not parent_child_pairs:
        return {}

    # Build a directed graph and a list of all names that have no parent
    graph = {
        name: set()
        for kinship in parent_child_pairs
        for name in kinship
        if name is not None
    }
    has_parent = {name: False for name in graph}
    for parent, child in parent_child_pairs:
        if parent is not None and child is not None:
            graph[parent].add(child)
            has_parent[child] = True

    # All names that have absolutely no parent:
    roots = [name for name, parents in has_parent.items() if not parents]

    # traversal of the graph (doesn't care about duplicates and cycles)
    def traverse(hierarchy, graph, names, seen=None):
        seen = seen or set()
        for name in names:
            if name in seen:
                raise ValueError("Cannot represent circular reference in tree form")
            else:
                seen.add(name)
            hierarchy[name] = traverse({}, graph, graph[name], seen)
        return hierarchy

    return traverse({}, graph, roots)


class Identifier:
    """Convert strings like "Wood Pulp" or "Cote D'Ivoire" to various styles.

    Example:
        ```
        i = Identifier("Cote D'Ivoire")
        i.upper_space  # COTE DIVOIRE
        i.lower_space  # cote divoire
        i.upper_snake  # COTE_DIVOIRE
        i.lower_snake  # cote_divoire
        ```
    """

    def __init__(self, string):
        self.parts = re.split(r"[_\- ]", string.replace("'", "").lower())
        self.upper_space = " ".join(self.parts).upper()  # COTE DIVOIRE
        self.lower_space = " ".join(self.parts).lower()  # cote divoire
        self.upper_snake = "_".join(self.parts).upper()  # COTE_DIVOIRE
        self.lower_snake = "_".join(self.parts).lower()  # cote_divoire
        self.upper_kebab = "-".join(self.parts).upper()  # COTE-DIVOIRE
        self.lower_kebab = "-".join(self.parts).lower()  # cote-divoire

    def __eq__(self, other):
        return self.parts == other.parts


import contextlib
import os


@contextlib.contextmanager
def modified_environ(*remove, **update):
    """
    Temporarily updates the ``os.environ`` dictionary in-place.

    The ``os.environ`` dictionary is updated in-place so that the modification
    is sure to work in all situations.

    :param remove: Environment variables to remove.
    :param update: Dictionary of environment variables and values to add/update.
    """
    env = os.environ
    update = update or {}
    remove = remove or []

    # List of environment variables being updated or removed.
    stomped = (set(update.keys()) | set(remove)) & set(env.keys())
    # Environment variables and values to restore on exit.
    update_after = {k: env[k] for k in stomped}
    # Environment variables and values to remove on exit.
    remove_after = frozenset(k for k in update if k not in env)

    try:
        env.update(update)
        [env.pop(k, None) for k in remove]
        yield
    finally:
        env.update(update_after)
        [env.pop(k) for k in remove_after]


def import_submodules(module):
    """Import all submodules of a module, recursively.

    Example usage:

        import myproject.models
        import_submodules(myproject.models)
    """
    for loader, module_name, is_pkg in pkgutil.walk_packages(
        module.__path__, module.__name__ + "."
    ):
        importlib.import_module(module_name)


def clean_string(text: Optional[str], upper=True):
    """
    Take a string and clean it!

    - Remove double-whitespace
    - Remove tab, newline, return, formfeed, etc.
    - Replace accented characters (e.g. ö becomes o)
    - Trim leading and trailing whitespace
    - Convert to upper-case
    """
    if not text:
        return text

    def keep(character):
        category = unicodedata.category(character)
        return (
            category[0] != "C"  # ignore control characters
            and category != "Zl"  # ignore line separator
            and category != "Zp"  # ignore paragraph separator
        )

    text = "".join(c for c in text if keep(c))
    text = " ".join(text.split())
    text = unidecode(text)

    return text.upper() if upper else text


