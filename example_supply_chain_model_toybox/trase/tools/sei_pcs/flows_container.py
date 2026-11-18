from dataclasses import dataclass
from logging import getLogger
from textwrap import indent
from types import SimpleNamespace
from typing import Dict, List, Type

import pandas as pd
from more_itertools import one

from trase.tools.etl.pandas_wrapper import read_csv
from trase.tools.etl.utilities import dataset_path
from trase.tools.sei_pcs.constants import ID
from trase.tools.sei_pcs.dataframe_container import DataFrameContainer
from trase.tools.sei_pcs.definition import Column, Dataset
from trase.tools.sei_pcs.pandas_utilities import select_subset, prefix_columns
from trase.tools.sei_pcs.recursive_join import Link, prejoin
from trase.tools.sei_pcs.validation import run_validation, ValidationError

LOGGER = getLogger(__name__)


@dataclass
class FlowsContainer:
    dataframes: DataFrameContainer
    flows_columns: List[Column]

    @classmethod
    def load(
        cls,
        data_directory: str,
        flows_columns: List[Column],
        datasets: Dict[str, Dataset] = None,
    ):
        datasets = datasets or {}
        if "flows" in datasets:
            raise ValueError("Cannot have a dataset called 'flows'")

        dataset_definitions = {
            "flows": SimpleNamespace(columns=flows_columns),
            **datasets,
        }
        dataset_columns = {
            name: dataset.columns for name, dataset in dataset_definitions.items()
        }

        # read data into memory
        dataset_column_types = resolve_column_types(dataset_columns)
        errors = []
        dataframes = {}
        for name, columns in dataset_columns.items():
            path = dataset_path(data_directory, name)
            try:
                dataframes[name] = read_dataset(
                    path, columns, dataset_column_types[name]
                )
            except ValueError as e:
                LOGGER.exception(f"Failure loading dataset '{name}'")
                errors.append(f"Failure loading dataset '{name}': {e}")
        if errors:
            raise ValueError("\n".join(errors))

        # Run column-level validation on all dataframe
        errors = []
        for name, df in dataframes.items():
            columns = dataset_columns[name]
            validation = {column.name: column.all_validators() for column in columns}
            try:
                run_validation(df, validation)
            except ValidationError as e:
                pretty = indent(str(e), prefix="\t")
                errors.append(
                    f"Dataset '{name}' failed column-level validation:\n{pretty}"
                )
        if errors:
            raise ValidationError("\n".join(errors))

        # execute all of the "links" (left-joins) in the definition, with the exception
        # of the flows dataset, which we leave unjoined so that the data can be altered
        # during the model run. we might want to be more clever here in the future: for
        # example marking some columns as being "mutable", or allowing auxiliary
        # datasets to be altered as well as flows
        links = {
            name: {
                column.name: Link(
                    column.linked_dataset,
                    column.linked_attribute,
                    column.only_validate_link,
                )
                for column in columns
                if column.is_linked
            }
            for name, columns in dataset_columns.items()
        }
        dataframes, links = prejoin(dataframes, links, excluding=["flows"])

        # create a container to hold the dataframes
        defaults = {
            name: {
                column.name: column.value
                for column in definition.columns
                if column.value
            }
            for (name, definition) in dataset_definitions.items()
        }
        validation = {
            name: {
                column.name: column.all_validators() for column in definition.columns
            }
            for (name, definition) in dataset_definitions.items()
        }
        dataframes = DataFrameContainer(dataframes, links, defaults, validation)
        obj = cls(dataframes, flows_columns)

        # validate that all joins are (actually, we only need to do this for flows!)
        obj.get("flows")

        return obj

    def get(self, name, subset=None, prefix="", copy=True, ids=True) -> pd.DataFrame:
        ids = (name == "flows") and ids
        df = self.dataframes.get(name, copy, ids)
        if subset is not None:
            # filter the columns according to the wild-card style patterns in "subset"
            # it may seem odd that this is an argument to get rather than separate free
            # function; but this is intentional, as it is antipicated we may be able to
            # make performance improvements in the future using this parameter, for
            # example by skipping unnecessary joins
            if ids and ID not in subset:
                subset = [ID, *subset]
            df = select_subset(df, subset)
        return prefix_columns(df, prefix)

    def update(
        self,
        df_flows,
        columns,
        skip_conservation_check_for=None,
        allow_splitting=True,
    ):
        skip_conservation_check_for = skip_conservation_check_for or []
        conserved_columns = [
            column.name
            for column in self.flows_columns
            if column.conserve and column.name not in skip_conservation_check_for
        ]
        return self.dataframes.update(
            "flows", df_flows, columns, conserved_columns, allow_splitting
        )

    def replace(
        self,
        df_flows,
        missing_value_columns="warn",
        extra_columns="raise",
        skip_conservation_check_for=None,
    ):
        skip_conservation_check_for = skip_conservation_check_for or []
        conserved_columns = [
            column.name
            for column in self.flows_columns
            if column.conserve and column.name not in skip_conservation_check_for
        ]
        return self.dataframes.replace(
            "flows", df_flows, conserved_columns, missing_value_columns, extra_columns
        )


def read_dataset(location, columns: List[Column], column_types: Dict[str, Type]):
    """Load a CSV file into a Pandas dataframe.

    Columns and types must be explicitly provided. If a column is specified with a
    default value, then it will not be read from the file but rather created after load
    and populated with the default value. If a column is specified without a default
    value then it is assumed to be in the file.

    If one of more columns has key=True, then they must together contain unique values.

    Raises:
        ValueError: if there are any type-casting issues or columns which are marked as
            "key" but contain duplicated values
    """
    # load columns that exist in file
    converters = {
        column.name: column_types[column.name]
        for column in columns
        if column.is_present_in_file
    }
    df = read_csv(location, converters, delimiter=";", quotechar='"', encoding="utf8")

    # add columns that do not exist in file
    for column in columns:
        if not column.is_present_in_file:
            column_type = column_types[column.name]
            base_type = getattr(column_type, "__origin__", None) or column_type
            if not isinstance(column.value, base_type):
                raise ValueError(
                    f"Expected the value of {column.name} to be of type {column_type}"
                )
            df[column.name] = pd.Series([column.value] * len(df))

    # validate that key columns contain unique values
    key_columns = [column.name for column in columns if column.key]
    if key_columns:
        duplicated = df.duplicated(subset=key_columns, keep=False)
        if any(duplicated):
            pretty = (
                df[duplicated][key_columns]
                .groupby(key_columns, as_index=False)
                .size()
                .rename(columns={"size": "count"})
                .reset_index(drop=True)
            )
            raise ValueError(
                f"The columns '{', '.join(key_columns)}' contain duplicated values:\n"
                f"{pretty}"
            )

    return df


def resolve_column_types(
    datasets: Dict[str, List[Column]]
) -> Dict[str, Dict[str, Type]]:
    """
    Given a dictionary of dataset definitions, return a dictionary of column types. For
    example::

        {"my_dataset": [Column("my_column")]}

    will become::

        {"my_dataset": {"my_column": str}}

    This is not just rearranging data structures: it will also handle linked columns,
    fetching the type of the target column.
    """

    def get_type(column: Column, dataset_name) -> Type:
        if column.is_linked:
            p = (
                f"The '{column.name}' column of the '{dataset_name}' dataset links to "
                f"the '{column.linked_attribute}' column of the "
                f"'{column.linked_dataset}' dataset, but the target dataset"
            )
            try:
                linked_column = one(
                    (
                        candidate_column
                        for candidate_column in datasets[column.linked_dataset]
                        if candidate_column.name == column.linked_attribute
                    ),
                    too_short=ValueError(f"{p} does not have this column"),
                    too_long=ValueError(f"{p} has multiple columns of that name"),
                )
            except KeyError:
                raise ValueError(f"{p} does not exist")
            return get_type(linked_column, column.linked_dataset)
        else:
            return column.type

    return {
        dataset_name: {
            column.name: get_type(column, dataset_name) for column in columns
        }
        for dataset_name, columns in datasets.items()
    }
