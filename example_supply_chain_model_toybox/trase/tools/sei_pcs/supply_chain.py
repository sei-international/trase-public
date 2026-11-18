"""
The "central" interface which enables a user use to easily run an SEI-PCS model
"""

import os
from contextlib import contextmanager
from logging import getLogger
from typing import List, Optional
from more_itertools import one

import numpy as np
import pandas as pd

from trase.tools.sei_pcs import constants
from trase.tools.sei_pcs.dataframe_container import (
    construct_export_dataframe,
    flow_report_by_attribute,
)
from trase.tools.sei_pcs.flows_container import FlowsContainer
from trase.tools.sei_pcs.pandas_utilities import split_dataframe_using_proportions
from trase.tools.sei_pcs.definition import Definition
from trase.tools.etl.context import Context
from trase.tools.sei_pcs.definition import reload_definition_at_path
from trase.tools.etl.processors import OUTPUT_FILE_OVERWRITE_TRACKER
from trase.tools.sei_pcs.pandas_utilities import (
    warnings_if_pd_merge_called_without_validate,
)
from trase.tools.sei_pcs.reload import reload_module_at_path
from trase.tools.etl.utilities import dataset_path
from trase.tools.sei_pcs.utilities import trace_memory_allocation

LOGGER = getLogger(__name__)


class SupplyChain:
    """Core object from which supply chain models are run.

    This object is responsible for the following:

     - Executing the _data preparation script_

     - Loading data into memory from CSV files that were produced by the data
       preparation script, according to the rules in the model definition
     - Providing an interface by which these data can be modifed

     - Executing the _model script_, which uses the aforementioned interface

     - Generating the "results" file according to the rules in the model definition: a
       CSV file containing the data as it is after the model has modified it
    """

    def __init__(
        self,
        directory: str,
        year: int,
        extra: Optional[dict] = None,
        script_levels: int = 1,
        data_directory: Optional[str] = None,
        definition: Optional[Definition] = None,
        pre_extracted_data: Optional[dict] = None,
    ):
        """Provides an easy interface to run supply chain models.

        This class is intended to be used via
        `trase.tools.sei_pcs.supply_chain.SupplyChain`. The most basic
        invocation is:

        ```python
        SupplyChain("path/to/my/model", 2019)
        ```

        When run like this, the class *requires* the following file structure:

        ```nohiglight
        trase/models
        └── path/to/my/model
            └── definition.py
        ```

        The definition file should contain the definition of the supply chain model
        (see `trase.tools.sei_pcs.definition`).

        However, it *supports* the following file structure:

        ```nohiglight
        trase/models
        └── path/to/my/
            ├── model
            │   ├── 2019
            │   │   ├── downloaded         # raw files copied in by the ETL framework
            │   │   ├── prepared           # files prepared by ETL framework
            │   │   └── results            # output of the model
            │   ├── definition.py
            │   ├── model.py               # model run code
            │   ├── quality_assurance.py   # post-run, quality assurance code
            │   └── preparation.py         # ETL framework preparation code
            ├── preparation.py             # parent-level preparation*
            └── quality_assurance.py       # parent-level quality assurance*
        ```

        * Notice that the scripts `preparation.py` and `quality_assurance.py` may
        also be _additionally_ located in the parent directory. In this location, they
        will be run for all child models. This is intended to support "country-level"
        datasets when there are many models for country. By default only one parent
        directory is searched, but you can increase this using the `script_levels`
        parameter.


        Args:
            directory (str): path to the directory containing the definition.py file
                relative to the "trase/models" directory.
            year (int): year for which the supply chain model is to be run
            extra (dict, optional): extra data for the model that will be passed to
                `trase.tools.etl.context.Context`. For example, if we provide
                `extra=dict(factor=10)`, then we can access this later as
                `supplychain.context.extra["factor"]`.
            script_levels (int, optional): how many parent directories to search for
                preparation.py and quality_assurance.py scripts. The default is 1,
                meaning that the directory and its parent will be searched. Usually
                this is the commodity and the country.
            data_directory (str, optional): a place to store the data for the ETL
                framework. By default this will be stored alongside the definition.py
                file in a sub-directory named after the current year
            definition (trase.tools.sei_pcs.definition.Definition, optional): an
                in-memory definition for the supply chain. If this is not supplied then
                we will try to read a file "definition.py" in the directory argument of
                this constructor.
            pre_extracted_data (dict, optional): if this is provided, then preparation
                classes will use these in-memory dataframes instead of reading their
                source files. This object should be a dictionary, where the keys are
                the file stem of the "outname" properties of the preparation classes;
                for example "flows".
        """
        # convert directory to an absolute directory
        # e.g. /path/to/TRASE/trase/models/orvessa/candy
        if not os.path.isabs(directory):
            directory = os.path.join(constants.context_root(), directory)
        self.directory = os.path.normpath(directory)

        # context
        # e.g. /path/to/TRASE/trase/models/orvessa/candy/201X/
        data_directory = data_directory or os.path.join(self.directory, str(year))
        extra = extra or {}
        self.context = Context(year, data_directory, extra, pre_extracted_data)

        # local paths
        # e.g. /path/to/TRASE/trase/models/orvessa/candy/201X/results/
        self.results_directory = os.path.join(self.context.data_directory, "results")

        # e.g. /path/to/TRASE/trase/models/orvessa/candy/201X/results/results.csv
        self.results_path = os.path.join(self.results_directory, "results.csv")

        # e.g. /path/to/TRASE/trase/models/orvessa/candy/201X/results/results.csv
        self.results_flows_path = os.path.join(self.results_directory, "flows.csv")

        # locations of scripts
        # e.g. ["/path/to/TRASE/trase/models/orvessa/candy/", "/path/to/TRASE/trase/models/orvessa/", ...]
        def parents(path, n):
            yield path
            for _ in range(n):
                path, _ = os.path.split(path)
                yield path

        paths = list(parents(self.directory, script_levels))

        # e.g. ["/path/to/TRASE/trase/models/orvessa/candy/preparation.py", "/path/to/TRASE/trase/models/orvessa/preparation.py", ...]
        self.preparation_scripts = [os.path.join(d, "preparation.py") for d in paths]

        # e.g. ["/path/to/TRASE/trase/models/orvessa/candy/quality_assurance.py", "/path/to/TRASE/trase/models/orvessa/quality_assurance.py", ...]
        self.quality_assurance_scripts = [
            os.path.join(d, "quality_assurance.py") for d in paths
        ]

        # store definition
        if definition is None:
            # e.g. "/path/to/TRASE/trase/models/orvessa/candy/definition.py"
            definition_file = os.path.join(self.directory, "definition.py")
            definition: Definition = reload_definition_at_path(definition_file)
            LOGGER.info(f"Using definition at: {definition_file}")
        self.definition: Definition = definition

        # mark whether preparation has run
        self.prepared = False

        self.model_run_script = os.path.join(self.directory, "model.py")

    @trace_memory_allocation
    def preparation(self):
        """Execute the data preparation scripts."""
        context = self.context

        with cwd(constants.CODEBASE_ROOT):
            try:
                OUTPUT_FILE_OVERWRITE_TRACKER.enable()
                with warnings_if_pd_merge_called_without_validate():
                    self._call_scripts_with_function(
                        self.preparation_scripts, "preparation", context
                    )
            finally:
                OUTPUT_FILE_OVERWRITE_TRACKER.disable()

        self.prepared = True

    def results_path_with_optional_suffix(self, suffix=""):
        # TODO make results_path a function not a property and drop this function
        path = self.results_path
        if suffix:
            path = self.add_suffix(path, suffix)
        return path

    def results_flows_path_with_optional_suffix(self, suffix=""):
        path = self.results_flows_path
        if suffix:
            path = self.add_suffix(path, suffix)
        return path

    def add_suffix(self, path, suffix):
        name, ext = os.path.splitext(path)
        return f"{name}_{suffix}{ext}"

    def quality_assurance(self):
        self._call_scripts_with_function(
            self.quality_assurance_scripts, "quality_assurance", self
        )

    @trace_memory_allocation
    def run(self):
        """Execute the model run script.

        This function will open the script "model.py" in the model directory
        and execute the function `run` defined in it.

        Returns: the return value of the `run` function in the model run script.
        """
        with warnings_if_pd_merge_called_without_validate():
            results = self._call_scripts_with_function(
                [self.model_run_script], "run", self
            )
        return one(results)

    def _call_scripts_with_function(
        self, scripts: List[str], function_name: str, *function_arguments
    ):
        results = []
        for script_file in scripts:
            if not os.path.isfile(script_file):
                continue

            module = reload_module_at_path(script_file)
            function = getattr(module, function_name, None)
            if function is None:
                LOGGER.debug(f"{script_file}: no function named {function_name}")
                continue

            LOGGER.info(f"Running {function_name} from {script_file}")

            return_value = function(*function_arguments)
            results.append(return_value)

        return results

    def dataset_path(self, name) -> str:
        return dataset_path(self.context.data_directory, name)

    def load(self):
        """Read the prepared CSV files on disk and load them into this object.

        Which CSV files are read is determined by the datasets in the definition. If the
        definition contains this:

        ```python
        datasets = {
            "province": Dataset([
                c("name")
            ),
            ...
        }
        ```

        Then the file `<year>/prepared/province.csv` will be read. As well as "datasets", the
        file `<year>/prepared/flows.csv` is _always_ read.

        After all of the data is read, it will be checked for consistency. In
        particular, this includes:

         - The columns of a dataset with `key=True` must contain unique values when
           considered together
         - If a column has a `link` parameter then the target must be a many-to-one
           left join with no missing values.
         - The columns of CSV must be parsable to the target types, like int or bool

        Calling `load()` will also create columns which have the `value` parameter.
        """
        datasets = {**self.definition.datasets, **self.definition.constraints}
        self.flows_container = FlowsContainer.load(
            self.context.data_directory, self.definition.flows, datasets
        )

    def get(self, name, subset=None, prefix="", ids=True):
        """Access a dataset by name.

        Example:
            ```python
            df = supplychain.get("flows", subset=["branch"])
            ```

        If possible, it is best to use the `subset` parameter to pre-filter the
        columns you want.

        If the dataset has any columns which had a `link` parameter in the definition,
        they will be pre-joined for you using a dot notation, e,g,
        "department.province.name".

        Args:
            name: the name of the dataset, such as "province". The flows dataset is
                referred to as "flows"
            subset (list): a list of columns to select from the dataset. This is
                equivalent to filtering the dataset after you have accessed it; except
                with two differences. Firstly, the "_id" column which is required for
                the `update` method is preserved. Secondly, future versions of the
                framework may apply efficiency gains to using `subset` for large
                datasets
            prefix: an optional string to prefix every column with
        """
        return self._dataframes.get(name, subset, prefix, copy=True, ids=ids)

    def update(
        self,
        df_flows,
        columns,
        skip_conservation_check_for=None,
        allow_splitting=True,
    ):
        """Update a subset of the flows dataset.

        This function allows you to:

            - Update a _subset_ the columns, leaving the others unchanged; and/or
            - Update a _subset_ of rows, leaving the others unchanged; and/or
            - _Split_ rows; that is, duplicate rows and then overwrite a subset of
                columns; and/or
            - Add new rows

        It is not possible to delete rows, nor is it possible to merge them. If you wish
        to do either of these then use
        `trase.tools.sei_pcs.supply_chain.SupplyChain.replace`.

        This function can only be used to modify the "flows" dataset: it is not possible
        to modify any other datasets.

        ## Example: modifying a subset of columns

        ```python
        df = supplychain.get("flows")
        df["status"] = "my new value"
        supplychain.update(df, ["status"])
        ```

        ## Example: modifying a subset of rows

        ```python
        df = supplychain.get("flows")
        df = df[df["municipality"] != "UNKNOWN"].copy()  # select a subset of rows
        df["status"] = "solved"
        supplychain.update(df, ["status"])
        ```

        ## Example: splitting rows

        This is done by having rows which repeat the "_id" column:

        ```python
        df = supplychain.get("flows")
        df = pd.concat([
            df.assign(vol=0.5 * df["vol"], status="solved"),
            df.assign(vol=0.5 * df["vol"], status="unsolved"),
        ])
        supplychain.update(df, ["status", "vol"])
        ```

        ## Example: creating new rows

        This is done by using the value -1 for the "_id":

        ```python
        df = supplychain.get("flows", subset=["status", "vol"])
        df = pd.concat(
            [df, pd.DataFrame([{"_id": -1, "status": "DOMESTIC", "vol": 100}])],
            ignore_index=True,
        )
        supplychain.update(df, ["status", "vol"])
        ```

        ## Example: skipping a conservation check

        For example, suppose we would like to allow the total sum of "vol" to change:

        ```python
        supplychain.update(df, ["status", "vol"], skip_conservation_check_for=["vol"])
        ```

        ## Example: refusing to split rows

        Splitting is opt-out rather than opt-in, because a repeated "_id" is a valid
        way to express a split. Most branch-assignment code, though, means to label
        each flow exactly once: there, a repeated "_id" is a bug, usually a merge
        against a lookup table whose join key turned out not to be unique. Such an
        update silently duplicates the flow's volume, and the conservation check only
        catches it if the column is marked `conserve=True` in the definition. Pass
        `allow_splitting=False` to assert that this update maps each flow to at most
        one row:

        ```python
        supplychain.update(df, ["branch", "status"], allow_splitting=False)
        ```

        Args:
            df_flows: the flows dataset. This must have a column "_id" so that it is
                possible to relate your changed rows to the original ones.
            columns (list): a list of columns which should be updated. If a column was
                linked, you must update the link parameter. For example if you have a
                column `Column("province", link="province.name")` then you must pass
                `columns=["province.name"]` to this function in order to update it.
            skip_conservation_check_for (list): if you know that this update will cause
                a change in the total sum of a numeric column which has `conserve=True`,
                you can include it in this list to disable the check.
            allow_splitting (bool): whether rows may be split by repeating an "_id".
                Pass False to assert that this update touches each flow at most once;
                rows with an "_id" of -1 are new rows, not splits, and are always
                allowed.

        Raises:
            ValueError: if there are any type-casting issues or columns which are marked
                as "key" but contain duplicated values
            LinkError: if any linked columns fail to fully join with their targets
            ConservedValueError: if the update would cause any columns which have
                `conserve=True` in their definition and are not included in the
                 `skip_conservation_check_for` parameter to change in their total sum
            RowSplittingError: if `allow_splitting` is False and the update repeats the
                "_id" of an existing row
        """
        return self._dataframes.update(
            df_flows, columns, skip_conservation_check_for, allow_splitting
        )

    def replace(
        self,
        df_flows,
        missing_value_columns="warn",
        extra_columns="raise",
        skip_conservation_check_for=None,
    ):
        """Replace the flows dataset with a new dataframe.

        This function can only be used to modify the "flows" dataset: it is not possible
        to modify any other datasets.

        ## Example

        Suppose that we have the following flows definition:

        ```python
        datasets={
            "municipality": Dataset([
                Column("name"),
                Column("trase_id"),
            ]),
        },
        flows=[
            Column("status", value="UNPROCESSED"),
            Column("municipality", link="trase_id"),
            Column("vol", int),
        ],
        ```

        Then we would replace the flows dataset with some dataframe `df_2` as follows:

        ```python
        # the following columns are required. "status" is optional; if not supplied the
        # default value of "UNPROCESSED" will be used
        assert "vol" in df.columns
        assert "municipality.trase_id" in df.columns

        supplychain.replace(df)

        supplychain.get("flows")  # will now return the new dataframe
        ```

        In the above example, only the columns "vol", "municipality.trase_id" and
        (optionally) "status" will be read. Other columns, like "municipality.name" for
        example, will be ignored. Such linked data will be joined in from the
        "municipality" dataset during the call to `supplychain.get("flows")`.

        ## Example: skipping a conservation check

        For example, suppose we would like to allow the total sum of "vol" to change:

        ```python
        supplychain.replace(df, skip_conservation_check_for=["vol"])
        ```

        Args:
            df_flows: a pandas dataframe that will replace the flows dataset.
            missing_value_columns: behaviour when columns with a value have not been
                provided: one of "ignore" (do nothing), "warn" (print a warning) or
                "raise" (raise an error). By "column with a value" we mean one
                constructed like `Column("my_column", value="default")`: see
                `trase.tools.sei_pcs.definition.Column`
            extra_columns: behaviour when the dataframe has unexpected columns: one of
                one of "ignore" (do nothing), "warn" (print a warning) or "raise" (raise
                an error).
            skip_conservation_check_for (list): if you know that this update will cause
                a change in the total sum of a numeric column which has `conserve=True`,
                you can include it in this list to disable the check.

        Raises:
            KeyError: if some non-value columns are missing, or some value columns are
                missing and `missing_value_columns="error"`
            LinkError: if any linked columns fail to fully join with their targets
            ConservedValueError: if the update would cause any columns which have
                `conserve=True` in their definition and are not included in the
                 `skip_conservation_check_for` parameter to change in their total sum
        """
        return self._dataframes.replace(
            df_flows, missing_value_columns, extra_columns, skip_conservation_check_for
        )

    def flow_report_by_attribute(
        self, value_column: str, by: List[str], significant_digits=2, **kwargs
    ):
        """
        Prints a summary the flows dataframe when consolidated over one or more
        categorical columns. The absolute numbers are included as well as a relative
        percentage.

        Example:
            >>> supplychain.flow_report_by_attribute("vol", ["exporter"])
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
        """
        flow_report_by_attribute(
            self._dataframes,
            name="flows",
            value_column=value_column,
            by=by,
            significant_digits=significant_digits,
            **kwargs,
        )

    def df_export(self) -> pd.DataFrame:
        """Construct the results dataframe.

        The columns that this dataframe includes are as specified in the "export"
        section of the definition. To see how this should be written, refer to existing
        models such as the demonstrative "Orvessa" model.
        """
        return construct_export_dataframe(
            "flows", self._dataframes, self.definition.flows_export
        )

    def export_results(self, df=None, suffix="", export=True, flows=True):
        """Write the results dataframe to disk.

        The location will be `<year>/results/results.csv`, or
        `<year>/results/results_suffix.csv`.

        Args:
            export: write the results/results.csv file, containing columns defined in
                the "export" section of the definition (default: True)
            flows: write the results/flows.csv file, containing the flows dataset
                without pre-joined data (default: True)
        """
        if export:
            path = self.results_path_with_optional_suffix(suffix)
            df = self.df_export() if df is None else df
            write_results_dataframe_to_disk(df, path, mkdirs=True)

        if flows:
            path = self.results_flows_path_with_optional_suffix(suffix)
            df = self._dataframes.dataframes.dataframes["flows"]
            write_results_dataframe_to_disk(df, path)

    def sankey(self, value_column, categorical_columns, *args, **kwargs):
        """See `trase.tools.sei_pcs.plotting.sankey`"""
        from trase.tools.sei_pcs.plotting import sankey

        df = self.get("flows", subset=[value_column, *categorical_columns])
        return sankey(df, value_column, categorical_columns, *args, **kwargs)

    @property
    def _dataframes(self):
        try:
            return self.flows_container
        except AttributeError:
            raise RuntimeError("SupplyChain has no data - did you call load()?")

    def __repr__(self):
        return f"SupplyChain, {self.directory}, Year: {self.context.year}"


def split_flows_using_proportions(
    supplychain: SupplyChain,
    df_proportions: pd.DataFrame,
    values: List[str],
    updating: List[str],
    on: List[str],
    by: str,
    where=None,
    skip_conservation_check_for=None,
    validate=None,
):
    """
    Args:
      values: a list of numerical columns whose values will be reduced: usually this
        is ``["volume", "fob"]``
      updating: a list of columns which will be updated on the flows dataset:
        usually this is ``["status", "branch"]``
      on: a list of columns on which the flows dataframe will be joined with the
        proportions dataframe
      by: the name of the column which contains the proportions: values between 0.0
        and 1.0, which always sum to one when aggregated over the columns specified
        in the ``on`` parameter
      where: a dictionary of column name -> function which will be used to filter the
        flows dataframe before the proportions are applied: usually this is
        ``{"status": lambda status: status == "UNKNOWN"}``
    """
    where = where or {}
    df_proportions = df_proportions[list(set([by, *on, *updating]))]
    df_flows = supplychain.get("flows", subset=set([*on, *values, *where]))
    df = split_dataframe_using_proportions(
        df_flows, df_proportions, values, on, by, where, validate
    )
    supplychain.update(
        df,
        columns=updating + values,
        skip_conservation_check_for=skip_conservation_check_for,
    )


def write_results_dataframe_to_disk(df, pathlike_or_buffer, mkdirs=False):
    if any(df.isna().any()):
        print(df.isna())
        raise ValueError(
            "Refusing to write a dataframe with None/NaNs since these cannot be "
            "unambiguously represented in the CSV format"
        )

    @np.vectorize
    def force_decimal(number):
        return np.format_float_positional(number, trim="-")

    if mkdirs:
        os.makedirs(os.path.dirname(pathlike_or_buffer), exist_ok=True)

    df.to_csv(
        pathlike_or_buffer,
        sep=constants.EXPORT_DELIMITER,
        encoding=constants.EXPORT_ENCODING,
        quotechar=constants.EXPORT_QUOTE_CHAR,
        index=False,
        float_format=force_decimal,  # plain decimals, never scientific notation
    )


@contextmanager
def cwd(path):
    oldpwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(oldpwd)
