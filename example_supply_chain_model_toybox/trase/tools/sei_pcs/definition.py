"""
The "definition" of an SEI-PCS model. It provides a quick overview of the datasets the
model requires, the "topology" of the model (the auxiliary datasets, nodes, constraints,
etc), how their columns relate to one another, and how the model results get exported
to CSV.
"""

from dataclasses import dataclass, field
from itertools import chain
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from pandas.api.types import is_numeric_dtype, is_bool_dtype
from toposort import toposort_flatten

from trase.tools.sei_pcs.reload import reload_module_at_path
from trase.tools.sei_pcs.validation import IsNonNegative
from trase.tools.sei_pcs.validation_base import Validation


@dataclass
class Column:
    """Define a column of a dataset.

    Args:
        name: the name of the column as it appears in the file.
        type: one of int, float, str, bool, List[int], etc.
        key: indicates that the column should be considered to be part of the "primary
            key" of the dataset; in particular, that the values (among all key columns)
            should be unique.
        link: of the form "target_dataset.target_column", indicating that this column
            should be left-joined on to on the "target_column" column in
            "target_dataset".
        value: a default value that the column should be populated with.
        conserve: whether this column should conserve its total sum throughout the
            model.
        validate: a class from the ``trase.tools.sei_pcs.validation`` model which
            performs column-level validation. For example ``validate=Code(6)`` will
            check that every value in the column is a six-digit code.
        only_validate_link: by default, if you link a target dataset, all columns of
            that dataset are added as part of the merge. For large datasets this can
            significantly increase memory. By setting ``only_validate_link=True``, only
            the target column will be added.

            For example, suppose that we have this definition:

                datasets = {
                    "state": Dataset([
                        Column("name"),
                        Column("code"),
                    ]),
                    "asset": Dataset([
                        Column("state", link="state.code"),
                    ]),
                }

            Then, the "asset" dataset will have the following columns:

             - `state.name`
             - `state.code`

            If, however, we pass `only_validate_link=True` to the link:

                datasets = {
                    # ...
                    "asset": Dataset([
                        Column("state", link="state.code", only_validate_link=True),
                    ]),
                }

            then the "asset" dataset will have only one column: the target of the link:

             - `state.code`

             However, the usual link validation will still occur.
        non_negative: add a validation that values are not negative. This defaults to
            true for numeric types and false otherwise.
    """

    name: str
    type: Type = str
    key: bool = False
    link: str = None
    value: Optional[Any] = None
    conserve: bool = False
    validate: Optional[Validation] = None
    only_validate_link: bool = False
    non_negative: bool = None

    LINK_DELIMITER = "."

    @classmethod
    def _parse_link(cls, link_string) -> Tuple[str, Optional[str]]:
        items = link_string.split(cls.LINK_DELIMITER)
        if len(items) == 1:
            return items[0], None
        elif len(items) == 2:
            return items[0], items[1]
        else:
            raise ValueError(
                f"Cannot parse link {link_string}: should be of the form 'dataset' or "
                "'dataset.attribute'"
            )

    def __post_init__(self):
        self.is_linked = self.link is not None
        if self.is_linked:
            self.linked_dataset, self.linked_attribute = self._parse_link(self.link)

        # calculate default value for self.non_negative if it wasn't supplied
        is_numeric = is_numeric_dtype(self.type) and not is_bool_dtype(self.type)
        if self.non_negative is None:
            self.non_negative = is_numeric

    @property
    def is_present_in_file(self):
        return self.value is None

    def all_validators(self) -> List[Validation]:
        explicit_validators = [self.validate] if self.validate is not None else []
        positivity_validators = [IsNonNegative()] if self.non_negative else []
        return [*explicit_validators, *positivity_validators]


@dataclass
class Export:
    """Construct an export definition for a column.

    This object contains information which is used by the functions which construct
    the results file.

    Args:
        header: the name of the resulting header in the CSV file. This should follow
            the Trase standard conventions, for example COUNTRY_OF_ORIGIN
        flow_attribute: the name of the column in the flow. This must relate to a column
            in the flow definition. You can refer to linked columns using dot syntax,
            for example "country.trase_id".
    """

    header: str
    flow_attribute: str


@dataclass
class Dataset:
    columns: List[Column]


@dataclass
class Definition:
    description: str
    commodity_equivalence_group_name: str = ""
    years: List[int] = field(default_factory=list)
    version: str = "1"
    country: str = "unknown_country"
    commodity: str = "unknown_commodity"
    datasets: Dict[str, Dataset] = field(default_factory=dict)
    # inputs that limit where flows can come from (e.g. production); loaded and
    # linked exactly like `datasets`, kept separate only to make definitions readable
    constraints: Dict[str, Dataset] = field(default_factory=dict)
    flows: List[Column] = field(default_factory=list)
    flows_export: List[Export] = field(default_factory=list)


def _raise_if_overlapping_keys(*dictionaries):
    keys = list(chain(*(d.keys() for d in dictionaries)))
    collisions = [key for key in keys if keys.count(key) > 1]
    if collisions:
        pretty = ", ".join(collisions)
        raise ValueError(f"The key(s) {pretty} appear multiple times")


def load_definition_from_module(module: ModuleType) -> Definition:
    field_names: Iterable[str] = Definition.__dataclass_fields__.keys()
    field_values = {
        name: getattr(module, name) for name in field_names if hasattr(module, name)
    }

    # extract any "nodes" and "connections" defined in the file. these are simply
    # bundled into "datasets": their only purpose is to encourage the user to think
    # about how to categorise their datasets
    datasets = field_values.get("datasets", {})
    nodes = getattr(module, "nodes", {})
    connections = getattr(module, "connections", {})
    _raise_if_overlapping_keys(datasets, nodes, connections)
    field_values = {**field_values, "datasets": {**datasets, **nodes, **connections}}

    return Definition(**field_values)


def reload_definition_at_path(path_to_definition_py: str) -> Definition:
    module = reload_module_at_path(path_to_definition_py)
    return load_definition_from_module(module)


def determine_load_order(datasets: Dict[str, Dataset]):
    dependencies = {
        dataset_name: set(
            column.linked_dataset for column in dataset.columns if column.is_linked
        )
        for dataset_name, dataset in datasets.items()
    }
    return toposort_flatten(dependencies)


c = Column


def e(header: str, flow_attribute: Optional[str] = None):
    if flow_attribute is None:
        flow_attribute = header
    return Export(header=header, flow_attribute=flow_attribute)


e.__doc__ = Export.__doc__
