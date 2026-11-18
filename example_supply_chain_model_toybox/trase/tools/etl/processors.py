import inspect
import json
import os
import shutil

from abc import ABCMeta, abstractmethod
from functools import partial
from json import JSONDecodeError
from logging import getLogger
from os.path import splitext
from pathlib import Path
from typing import List, Optional

import pandas as pd

from trase.tools.etl import exceptions
from trase.tools.etl.context import Context
from trase.tools.etl.exceptions import ValidationError
from trase.tools.etl.pandas_wrapper import (
    WellBehavedCSV,
    read_csv,
    read_excel,
    read_json,
    cast_dataframe_to_types,
    types_similar,
)
from trase.tools.etl.source import GetSource
from trase.tools.etl.utilities import (
    Loggable,
    consolidate,
    hash_iterable,
    hash_string,
    timing,
    validate,
)
from trase.tools.utilities.messages import print_message
from trase.tools.utilities.helpers import clean_string
from trase.tools.utilities.pandas_ import (
    dataframe_contains_nulls,
    dataframe_columns_are_all_strings,
)

LOGGER = getLogger(__name__)


class OutputFileOverwriteTracker:
    """A quick hack to warn if two processors are writing to the same file"""

    def __init__(self):
        self._set = None

    def enabled_and_seen(self, path) -> bool:
        return self._set is not None and path in self._set

    def add_if_enabled(self, path):
        if self._set is not None:
            self._set.add(path)

    def enable(self):
        self._set = set()

    def disable(self):
        self._set = None


OUTPUT_FILE_OVERWRITE_TRACKER = OutputFileOverwriteTracker()


class _Meta(ABCMeta, GetSource):
    pass


class PreprocessorBase(Loggable, metaclass=_Meta):
    errors = []
    encoding = "utf-8"

    class _MetadataFailure(Exception):
        pass

    def __init__(self, context: Context):
        """Create a preprocessor.

        Args:
            context: note that ``Context.data_directory`` will be used to store files.
            We will create two subdirectories: downloaded (file before processing) and
            prepared (file after processing). If the preprocesser is year-dependent,
            these will furthermore be in a YEAR subdirectory. The root directory need
            not exist: it will be created lazily when needed.
        """
        self.context = context

    ####################################################################################
    # Methods that *must* be implemented by inheriting classes
    ####################################################################################

    @abstractmethod
    def extract(self, path: str) -> None:
        """This method should extract data from the source and write it to PATH"""

    @abstractmethod
    def read_file(self, path):
        """Read the file of extracted data into memory and return it"""

    @abstractmethod
    def to_disk(self, process_object, path):
        """
        Serialize the processed object to disk, in a way that it can later be
        deserialized to recover exactly the original file
        """

    @abstractmethod
    def from_disk(self, path):
        """Deserialize the processed object from disk into memory"""

    @property
    @abstractmethod
    def outname(self) -> str:
        pass

    @property
    def data_key(self) -> str:
        file_stem, _ = os.path.splitext(self.outname)
        return file_stem

    @property
    @abstractmethod
    def original_extension(self) -> str:  # TODO - do we really need this?
        pass

    ####################################################################################
    # Methods that *can* be implemented by inheriting classes
    ####################################################################################

    def process(self, deserialized_object, *args):
        return deserialized_object

    ####################################################################################
    # Implementation of this class
    ####################################################################################

    @property
    def year(self):
        return self.context.year

    def run(self, *args, returns=True, force=False, prevent=False) -> Optional:
        """
        :param returns: if True, will always return an object; if False then it will
            not return anything. This is an optimisation to avoid loading data if the
            return value is never used anyway.
        :param force: if True, will re-run regardless of value of self.should_rerun
        """
        assert not (
            force and prevent
        ), "cannot force run and prevent it at the same time"

        if (not self.should_rerun(args) and not force) or prevent:
            print_message(f"Skipping re-process of {self}", color="white", indent=0)
        else:
            print_message(
                f"Running pre-processing for {self}", attrs=["bold"], indent=0
            )

            # delete metadata to ensure a second run is triggered if this one fails
            if os.path.isfile(self.metadata_path()):
                os.unlink(self.metadata_path())

            try:
                data = (self.context.pre_extracted_data or {})[self.data_key]
            except KeyError:
                with timing(f"Reading {self.ori_path()} into memory", indent=1):
                    data = self.read_file(self.ori_path())

            with timing("Pre-processing data", indent=1):
                data = self.preprocess(data)

            with timing("Processing data", indent=1):
                data = self.process(data, *args)
                assert data is not None, "process() must return a value"

            with timing("Post-processing data", indent=1):
                data = self.postprocess(data)

            with timing("Writing data to disk", indent=1):
                self._to_disk(data)
                self.write_metadata(args)

        if returns:
            with timing("Loading data from disk", indent=1):
                path = self.out_path()
                self.debug(f"Reading {path}")
                return self.from_disk(path)

    def _to_disk(self, data):
        path = self.out_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.debug(f"Writing to {path}")
        if OUTPUT_FILE_OVERWRITE_TRACKER.enabled_and_seen(path):
            self.warning(
                f"Overwriting {self.outname}: do two processors have the same outname?"
            )
        OUTPUT_FILE_OVERWRITE_TRACKER.add_if_enabled(path)
        self.to_disk(data, path)
        print_message(f"Written {path}", color="green")

    def __str__(self):
        return self.__class__.__name__

    def preprocess(self, df):
        return df

    def postprocess(self, df):
        return df

    def should_rerun(self, args):
        self.debug(f"Determining if {self} should be re-run")
        # rerun if required files do not exist
        prefix = f"Should reprocess {self} due to "
        self.debug(f"Determining if {self} should be re-run: check existence of files")

        if (
            not os.path.isfile(self.ori_path())
            or not os.path.isfile(self.out_path())
            or not os.path.isfile(self.metadata_path())
        ):
            self.debug(f"{prefix} missing files")
            return True

        # rerun if metadata cannot be loaded
        self.debug(f"Determining if {self} should be re-run: parsing metadata")
        try:
            with open(self.metadata_path()) as file:
                metadata = json.load(file)
        except JSONDecodeError as e:
            self.debug(f"{prefix} error parsing metadata: {e}")
            return True

        # rerun if metadata has changed (most expensive given possible hasing of large
        # input dataframes)
        self.debug(f"Determining if {self} should be re-run: comparing metadata")
        try:
            expected = self.construct_metadata(args)
        except self._MetadataFailure:
            self.warning(
                "Unable to construct metadata: defensively re-running", exc_info=True
            )
            return True

        if metadata != expected:
            self.debug(
                f"{prefix} metadata mismatch: expected {expected} but got {metadata}"
            )
            return True

        return False

    def construct_metadata(self, args):
        self.debug(f"Constructing metadata for args of {self}")
        source_codes = [
            getattr(cls, "_source", "") for cls in inspect.getmro(self.__class__)
        ]
        if any(s is None for s in source_codes):
            raise self._MetadataFailure("Missing source code")

        try:
            return {
                "args_hash": hash_iterable(args),
                "code_hashes": hash_string("".join(source_codes)),
            }
        except exceptions.HashFailure as e:
            raise self._MetadataFailure("Hash failed") from e

    def write_metadata(self, args):
        path = self.metadata_path()

        try:
            metadata = self.construct_metadata(args)
        except self._MetadataFailure:
            self.warning("Unable to construct metadata for writing", exc_info=True)
            # ensure that stale metadata is deleted
            if os.path.exists(path):
                self.debug("Deleting existing (presumed stale) metadata")
                os.unlink(path)
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            json.dump(metadata, file)

    def ori_path(self) -> str:
        return os.path.join(self.context.data_directory, "downloaded", self.inname)

    def out_path(self) -> str:
        return os.path.join(self.context.data_directory, "prepared", self.outname)

    def metadata_path(self) -> str:
        metadata_name = os.path.basename(self.outname) + ".json"
        return os.path.join(
            self.context.data_directory, "prepared/.metadata", metadata_name
        )

    @property
    def inname(self) -> str:
        # ensure original_extension starts with a dot
        name = os.path.basename(self.outname)
        stem = os.path.splitext(name)[0]
        return stem + (self.original_extension or ".csv")


class DataframePreprocessor(PreprocessorBase, Loggable):
    delimiter = None  # guess delimiter by default
    quotechar = '"'
    output_types = {}
    columns = []
    header = "infer"  # row number(s) that are considered headers
    skiprows = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _, out_extension = splitext(self.outname)
        if out_extension.lower() != ".csv":
            raise ValueError("Outname must end in .csv")
        columns = self.get_columns()
        duplicated_column_names = [
            column.rename
            for column in columns
            if len([c for c in columns if c.rename == column.rename]) > 1
        ]
        if duplicated_column_names:
            raise ValueError(
                f"Output column names are not unique: {', '.join(set(duplicated_column_names))}"
            )

    def read_file(self, path):
        converters = {column.name: column.type for column in self.get_columns()}
        if self.original_extension == ".json":
            return read_json(path, types=self.column_types())
        elif self.original_extension == ".xlsx":
            return read_excel(path, converters=converters)
        elif self.original_extension == ".parquet":
            return pd.read_parquet(path)
        else:  # assume CSV
            if self.original_extension != ".csv":
                self.warning(
                    f"Input file has extension {self.original_extension} but reading as a CSV"
                )

            return read_csv(
                path,
                converters=None,  # casting to types is done in preprocess
                delimiter=self.delimiter,
                encoding=self.encoding,
                quotechar=self.quotechar,
                header=self.header,
                skiprows=self.skiprows,
            )

    def column_types(self):
        return {c.name: c.type for c in self.get_columns()}

    def usecols(self):
        return [column.name for column in self.get_columns()]

    def select_output_columns(self, df):
        columns_to_remove = set(
            column.rename for column in self.get_columns() if not column.keep
        )
        return df[list(set(self.output_columns) - columns_to_remove)]

    def validate_columns(self, df):
        for column in self.get_columns():
            # validate series
            row_validation_function_name = f"validate_{column.rename.lower()}_series"
            if hasattr(self, row_validation_function_name):
                self.debug(f"Running validation {row_validation_function_name}")
                validation_function = getattr(self, row_validation_function_name)
                if not validation_function(df[column.rename]):
                    self.errors.append(
                        f"Some values in column {column.rename} fail validation"
                    )

            # validate rows
            row_validation_function_name = f"validate_{column.rename.lower()}"
            if hasattr(self, row_validation_function_name):
                validation_function = getattr(self, row_validation_function_name)
                self.debug(f"Running validation {row_validation_function_name}")
                series = df[column.rename]
                try:
                    validate(series, validation_function)
                except ValidationError as e:
                    self.errors.append(e.message)

        # print any errors
        for error in self.errors:
            print_message(error, color="red")
        success = not self.errors
        return success

    def validate(self, series, validation_function):
        try:
            validate(series, validation_function)
        except ValidationError as e:
            print_message(e, "error")
            raise e

    def preprocess(self, df):
        df = self._select_columns_and_cast_or_check_types(df)
        df = self.rename(df)
        self.possibly_clean_strings(df)
        if not self.validate_columns(df):
            raise ValueError("Validation failed")
        self.report(df, "Before processing")

        return df

    def postprocess(self, df):
        self.report(df, "After processing")
        return self.select_output_columns(df)

    def converters(self):
        column_types = {c.rename: c.type for c in self.get_columns() if c.keep}
        return {**column_types, **self.output_types}

    @property
    def output_columns(self) -> List[str]:
        return list(self.converters().keys())

    def get_columns(self) -> List["Column"]:
        return [Column(c) if type(c) == str else c for c in self.columns]

    def rename(self, df):
        return df.rename(
            columns={column.name: column.rename for column in self.get_columns()},
            errors="raise",
        )

    def report(self, df, msg="", report=None):
        """Print a summary of the dataframe.

        This function is intended to be used during the `process` function:

        Example:
            ```
            class MyData(DataframePreprocessor):
                columns = [
                    Column("year", type=int),
                    Column("vol", type=float, report=True),  # report=True causes sum to be included in the report
                ]

                def process(self, df_2):
                    df_2 = df_2[df_2["year"] == self.year]
                    self.report(df_2, "Filtered to current year")

                    df_2 = df_2[df_2["vol"] > 0]
                    self.report(df_2, "Dropped zero volume")

                    return df_2
            ```

        When the preprocessor is run, it will output something like:

        ```nohighlight
        Report: Filtered to current year
            | Row Count: 200
            | Sum of vol: 670
        Report: Dropped zero volume
            | Row Count: 150
            | Sum of vol: 670
        ```

        The function will always print out row counts. If furthermore any _numeric_
        columns are marked with `report=True` (as in the example of "vol" above), then
        their total sum will also be printed.

        Args:
            df: the Pandas dataframe to report on
            msg (optional): a message that will be printed to the screen
        """
        report = report or []
        print_message("Report" + (f": {msg}" if msg else ""))
        print_message(f"| Row Count: {len(df):,}", indent=2)
        for column in self.get_columns():
            should_report = column.rename in report or column.report
            column_in_dataframe = column.rename in df.columns
            if should_report and column_in_dataframe:
                print_message(
                    f"| Sum of {column.rename}: " f"" f"{df[column.rename].sum():,.0f}",
                    indent=2,
                )

    def from_disk(self, path: str):
        return WellBehavedCSV.read(path, self.converters())

    def to_disk(self, df, path: str):
        # check that the output path is for a .csv file
        ext = os.path.splitext(path)[1].lower()
        if ext and ext != ".csv":
            raise ValueError("Unable to write anything but csv")

        # write dataframe
        WellBehavedCSV.write(df, path, self.converters())

    def possibly_clean_strings(self, df):
        for column in self.get_columns():
            values = df[column.rename]

            if column.clean:
                LOGGER.debug(f"Cleaning column {column.rename}")
                values = values.apply(partial(clean_string, upper=False))

            if column.to_upper:
                LOGGER.debug(f"Upper-casing column {column.rename}")
                values = values.str.upper()

            df[column.rename] = values

    def consolidate(self, df, numerical_columns):
        categorical_columns = [
            c for c in self.output_columns if c not in numerical_columns
        ]
        df = consolidate(df, numerical_columns, categorical_columns)
        self.report(df, "Consolidate over " + "/".join(categorical_columns))
        return df

    def drop_duplicates(self, df):
        df = df.drop_duplicates(subset=self.output_columns)
        self.report(df, "Drop duplicates")
        return df

    def _select_columns_and_cast_or_check_types(self, df):
        # select only the columns requested
        converters = {column.name: column.type for column in self.get_columns()}
        # (copy, so that casting below doesn't write into a view of the original)
        df = df[list(converters)].copy()

        # if the source file is typed then we just check that the types in the data
        # match what was defined in the preprocessor
        if self.original_extension in [".parquet", ".xlsx", ".json"]:
            # TODO: could consider casting here anyway...
            self._warn_on_unexpected_types(df, converters)

        # if the source file is untyped then we cast the data to the types defined in
        # the preprocessor
        else:
            if self.original_extension == ".csv":
                # CSVs should always be loaded as strings and without nulls, rather
                # than relying on the type inference (explicit over implicit!)
                all_strings = dataframe_columns_are_all_strings(df)
                no_nulls = not dataframe_contains_nulls(df)
                assert all_strings and no_nulls, "CSV data should be not-null strings"

            df = cast_dataframe_to_types(df, converters)
        return df

    def _warn_on_unexpected_types(self, df, expected_types):
        for column, python_type in expected_types.items():
            dtype = df[column].dtype
            if not types_similar(dtype, python_type):
                LOGGER.warning(
                    f"In the Parquet file for {self} the column {column} has type "
                    f"{dtype} but the pre-processor has type={python_type}. Change "
                    f"the pre-processor to a compatible type."
                )


class Preprocessor(DataframePreprocessor):
    source_path = None  # path to the raw input file on local disk

    def extract(self, path):
        """
        Copy source data into 'downloaded' folder.
        NOTE: Runs every time, as a local copy is cheap
        """
        shutil.copy(self.yearly_source_path(), path)

    def _extract_from_source(self):
        path = self.ori_path()
        self.debug(f"Fetching source data into {path}")
        if not os.path.isfile(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.extract(path)

    def run(self, *args, returns=True):
        if self.data_key not in (self.context.pre_extracted_data or {}):
            print_message("Extracting data from source ...", end="")
            with timing(threshold=0, indent=1):
                self._extract_from_source()

        if self.should_rerun(args):
            return super(DataframePreprocessor, self).run(
                *args, returns=returns, force=True
            )

    @property
    def original_extension(self):
        return "." + os.path.basename(self.yearly_source_path()).split(".")[1]

    def yearly_source_path(self):
        return self.source_path.replace("%YEAR%", str(self.context.year))

    def should_rerun(self, args):
        should = False

        try:
            with open(self.metadata_path()) as file:
                metadata = json.load(file)
        except JSONDecodeError as e:
            self.debug(f"Error parsing metadata: {e}")
            metadata = {}
        except FileNotFoundError:
            metadata = {}

        if super(DataframePreprocessor, self).should_rerun(args):
            should = True
        elif self.data_key in (self.context.pre_extracted_data or {}):
            # we can't tell if the source data changed so always re-run
            should = True
        elif os.path.getmtime(self.yearly_source_path()) != metadata.get(
            "source_file_last_modified", None
        ):
            should = True

        self.write_metadata(args)
        return should

    def construct_metadata(self, args):
        metadata = super(DataframePreprocessor, self).construct_metadata(args)
        metadata["source_file_last_modified"] = os.path.getmtime(
            self.yearly_source_path()
        )
        return metadata

    # this is the same implementation as in DataframePreprocessor class,
    # but it calls Preprocessor.construct_metadata instead of parent method
    def write_metadata(self, args):
        path = self.metadata_path()

        try:
            metadata = self.construct_metadata(args)
        except self._MetadataFailure:
            self.warning("Unable to construct metadata for writing", exc_info=True)
            # ensure that stale metadata is deleted
            if os.path.exists(path):
                self.debug("Deleting existing (presumed stale) metadata")
                os.unlink(path)
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            json.dump(metadata, file)


class TextPreprocessor(PreprocessorBase):
    def read_file(self, path: str):
        return Path(path).read_text()

    from_disk = read_file

    def to_disk(self, contents, path):
        Path(path).write_text(contents)


class NoInputDataframePreprocessor(DataframePreprocessor):
    # TODO - generalise

    def read_file(self, path):
        df = pd.DataFrame(columns=self.usecols(), dtype=object)
        dtypes = self.column_types()
        if dtypes:
            df = df.astype(dtypes)
        return df

    def process(self, df):
        return df

    def extract(self, path: str):
        pass

    original_extension = ".csv"
    delimiter = ";"
    columns = []


class Column:
    """
    Refer to a column in the input data that should be read and (possibly) also included
    in the output.

    Args:
        name (str): the name of the column in the input data
        rename (str): an optional renaming of the column before it gets included in the
            output data. If this is the same as the name in the input data, it is not
            necessary to provide this argument.
        type (type): the expected type of the column in the input data; for example
            ``int`` or ``float``. If this argument is not provided then it is assumed to
            be ``str``. This argument is particularly important for untyped input data
            such as CSV, since it will trigger a type-cast. Is it still important for
            typed input data like Excel, since the code should reflect the types that
            are expected to be encountered in the input data.
        keep (bool): whether this column should be included in the output data. This
            option is for when you want to read the column from the input data so that
            you can use it in some way but exclude it from the output. (If you neither
            intend to use the column nor include it in the output, it's recommended to
            simply not read the column at all).
        clean (bool): whether string data should be "cleaned" (double whitespace
            removed, accented characters removed, etc). Defaults to ``true`` if the
            column type is ``str``.
        to_upper (bool): whether string data should be upper-cased. It defaults to
            whatever value ``clean`` takes, and is intended to be provided as an
            "opt-out" for those scenarios where string cleaning is desired but the
            case/capitalisation in the input data should be preserved.
        report (bool): print a report of the total values in each column during the
            processing run. Defaults to ``true`` for numeric types (int, float).
    """

    def __init__(
        self,
        name,
        rename=None,
        type=None,
        keep=True,
        clean=None,
        to_upper=None,
        report=None,
    ):
        self.name = name
        self.rename = rename or name
        self.type = type or str
        self.keep = keep

        # default to reporting numeric columns but respect user's explicit choice
        report_default = type in (int, float)
        self.report = report_default if report is None else report

        # default to cleaning str columns but respect user's explicit choice
        clean_default = self.type == str
        self.clean = clean_default if clean is None else clean

        # default to uppercasing if cleaning but respect user's explicit choice
        to_upper_default = bool(self.clean)
        self.to_upper = to_upper_default if to_upper is None else to_upper
