"""
How we store and update Pandas dataframes once they have been loaded from disk into
memory.
"""

from dataclasses import dataclass, field
from logging import getLogger
from typing import List

import numpy as np
import pandas as pd

from trase.tools.sei_pcs.constants import ID
from trase.tools.sei_pcs.exceptions import ConservedValueError, RowSplittingError
from trase.tools.sei_pcs.definition import Export
from trase.tools.sei_pcs.recursive_join import Dataframes, Links, dot, recursive_join
from trase.tools.sei_pcs.reporting import print_report_by_attribute
from trase.tools.sei_pcs.validation import run_validation

LOGGER = getLogger(__name__)


@dataclass
class DataFrameContainer:
    """
    This class has a few functions. On the face of it, it's just a dictionary-like
    container which allows you to access Pandas dataframes by a name.

    More than that, it also executes "left-joins" recursively according to a list of
    "links". This takes some of the effort out of constantly doing that yourself (see
    the ``trase.tools.sei_pcs.recursive_join`` module).

    However, the biggest value it brings is that it adds some safety checks when you
    want to _modify_ one of the dataframes in the containers. This ensures that the
    dataframe adheres to its original columns: none can be added, deleted, or change
    dtype. See ``DataFrameContainer.update`` for more on how this works.
    """

    dataframes: Dataframes
    links: Links
    defaults: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)

    def get(self, name, copy=True, ids=True):
        """
        Get a dataframe in the container by name. You should assume that the returned
        object is a copy, not a pointer: altering the object will only alter the copy,
        not the original stored in this class.

        All joins specified in the `links` recipe when this class was created will be
        executed (see the `trase.tools.sei_pcs.recursive_join` module).

        Args:
          copy (bool): if you know that you are not going to alter the return object
            and you are looking for extra performance, pass ``copy=False`` and you
            _may_ be able to avoid an in-memory copy operation. If you do this you
            should never alter the object you receive, or else you may corrupt this
            class.
          ids (bool): adds a column called "_id", which is required if you ever want to
            call ``Dataframe.update`` with this dataframe.
        """
        df = self._recursive_join(name, self.dataframes, copy)
        return self._assign_ids(df) if ids else df

    def update(
        self,
        name,
        df: pd.DataFrame,
        columns,
        conserved_columns=None,
        allow_splitting=True,
    ):
        columns = [c for c in columns if c != ID]
        df = df[[ID, *columns]]

        if not allow_splitting:
            self._raise_if_rows_would_split(name, df)

        # get existing data with .dot column names (e.g. "municipality.trase_id")
        df_existing = self._get_dataframe_with_dot_column_names(name)
        df_existing = self._assign_ids(df_existing)

        # check that we are only updating canonical columns
        errors = list(set(columns) - set(df_existing.columns))
        if errors:
            raise ValueError(f"Some columns cannot be updated: {', '.join(errors)}")

        # keep a note of the values which will be conserved
        conserved_columns = conserved_columns or []
        conserved_values_before = self._compute_conserved_values(
            df_existing, conserved_columns
        )

        # join new data into existing data. We add a temporary order column so we can
        # restore the original left-then-right-only row ordering: in pandas >= 2 the
        # default outer merge no longer guarantees that left rows precede right-only
        # rows when the join keys do not overlap.
        order_col = "__row_order__"
        df_existing_ordered = df_existing.assign(**{order_col: range(len(df_existing))})
        df_new = pd.merge(
            left=df_existing_ordered,
            right=df,
            on=ID,
            how="outer",
            suffixes=("_old", "_new"),
            indicator=True,
            validate="one_to_many",
        )
        df_new = (
            df_new.sort_values(by=order_col, na_position="last", kind="stable")
            .reset_index(drop=True)
            .drop(columns=order_col)
        )

        found_in_existing_data = df_new["_merge"] != "right_only"
        to_create = df_new[ID] == -1
        assert all(found_in_existing_data | to_create)

        # new data should overwrite existing data
        left_only = df_new["_merge"] == "left_only"
        for column in columns:
            old_data = df_new.pop(f"{column}_old")
            new_data = df_new.pop(f"{column}_new")
            df_new[column] = np.where(left_only, old_data, new_data)
        df_new = df_new.drop(columns=[ID, "_merge"])

        # ensure types are correct. we need to do this as the merge could have, for
        # example, caused an integer to be converted to an object to be able to handle
        # missing values
        dtypes = df_existing.dtypes.to_dict()
        dtypes.pop(ID)
        df_new = df_new.astype(dtypes)

        self._check_and_replace_dataframe(name, df_new, conserved_values_before)

    def _check_and_replace_dataframe(self, name, df, conserved_values):
        """This runs self.dataframes[name] = df_2 but with extra checks:

        - Raise error if values are not conserved
        - Raise error if joins will not succeed
        - Raise error if validation does not pass
        """
        renames = self._column_renames(name)

        # ensure that values are conserved
        self._raise_if_values_not_conserved(df, conserved_values)

        # put column names back to their canonical form (e.g. "municipality")
        df = df.rename(columns=self._invert(renames), errors="raise")
        df = df[self.dataframes[name].columns]

        # TODO column validation (on canonical names)
        validation = self.validation.get(name, {})
        run_validation(df, validation)

        # ensure that joins will succeed
        dataframes = {**self.dataframes, name: df}
        self._recursive_join(name, dataframes, copy=False)

        # update this class
        self.dataframes[name] = df

    def replace(
        self,
        name,
        df: pd.DataFrame,
        conserved_columns=None,
        missing_value_columns="warn",
        extra_columns="raise",
    ):
        # get existing data with .dot column names (e.g. "municipality.trase_id")
        df_existing = self._get_dataframe_with_dot_column_names(name)

        # detect missing value columns
        required = set(df_existing.columns)
        missing = required - set(df.columns)
        defaults = self.defaults.get(name, dict())
        d = missing & set(defaults)
        if d:
            d = sorted(d)
            if missing_value_columns == "warn":
                LOGGER.warning(f"Missing columns, will use defaults: {', '.join(d)}")
            elif missing_value_columns == "raise":
                raise KeyError(f"Missing columns: {', '.join(d)}")
            elif missing_value_columns != "ignore":
                raise ValueError(
                    f"Unrecognised value '{missing_value_columns}' for "
                    f'missing_value_columns: should be one of "ignore", "warn", or '
                    f'"raise"'
                )

        # detect missing non-value columns
        missing = missing - set(defaults)
        if missing:
            raise KeyError(f"Missing columns: {', '.join(missing)}")

        # detect extra columns
        if extra_columns in ("warn", "raise"):
            all_permitted = set(self.get(name).columns)
            ignored = all_permitted - required
            extra = set(df.columns) - set(all_permitted)
            if extra:
                pretty = ", ".join(sorted(extra))
                if extra_columns == "warn":
                    LOGGER.warning(f"Unexpected column(s), will ignore: {pretty}")
                else:
                    raise ValueError(
                        f"Unexpected column(s): {pretty}\n"
                        "Remove these columns or set extra_columns to be 'warn' or "
                        f"'ignore'.\nThese columns are REQUIRED:\n"
                        f"{_pretty_list(required)}\nThese columns are PERMITTED but "
                        f"ignored:\n{_pretty_list(ignored)}"
                    )
        elif extra_columns != "ignore":
            raise ValueError(
                "extra_columns can be 'ignore', 'warn', or 'raise'. Received "
                f"'{extra_columns}'"
            )

        # add in default values
        df = df.assign(**{column: defaults[column] for column in d})
        df = df[df_existing.columns]

        # ensure that values are conserved
        conserved_columns = conserved_columns or []
        conserved_values_before = self._compute_conserved_values(
            df_existing, conserved_columns
        )
        self._check_and_replace_dataframe(name, df, conserved_values_before)

    def _get_dataframe_with_dot_column_names(self, name):
        return self.dataframes[name].rename(
            columns=self._column_renames(name), errors="raise"
        )

    def _column_renames(self, name):
        return {c: dot(c, target.column) for c, target in self.links[name].items()}

    def _compute_conserved_values(self, df, conserved_columns):
        return {column: df[column].sum() for column in conserved_columns}

    def _raise_if_values_not_conserved(self, df, conserved_values):
        errors = []
        for column, before in conserved_values.items():
            after = df[column].sum()
            if not np.isclose(before, after):
                errors.append(
                    f"The column '{column}' is not conserved:\n"
                    f"\twas      {before:,}\n"
                    f"\twould be {after:,}"
                )
        if errors:
            raise ConservedValueError("\n".join(errors))

    @staticmethod
    def _raise_if_rows_would_split(name, df):
        """Raise unless every row of `df` maps to a distinct existing row.

        Rows with an "_id" of -1 are each a request to create a new row, so any number
        of them is fine; it is a repeated _id of an *existing* row that silently
        duplicates that row's volume.
        """
        existing = df[df[ID] != -1]
        duplicated = existing[existing[ID].duplicated(keep=False)]
        if duplicated.empty:
            return

        counts = duplicated.groupby(ID).size().sort_values(ascending=False)
        examples = ", ".join(
            f"{row_id} ({count} times)" for row_id, count in counts.head(5).items()
        )
        raise RowSplittingError(
            f"This update was called with allow_splitting=False, but {len(counts):,} "
            f"row(s) of '{name}' appear more than once in the update, which would "
            f"split them into {len(duplicated):,} rows and duplicate their conserved "
            f"values.\n"
            f"\tMost repeated {ID}(s): {examples}\n"
            "This is usually a merge against a right-hand dataframe whose join key is "
            "not unique. Deduplicate it (or pass validate= to the merge) so that each "
            "row matches at most one row on the right. If the split is intended, pass "
            "allow_splitting=True."
        )

    @staticmethod
    def _assign_ids(df):
        return df.assign(**{ID: range(len(df))})

    def _recursive_join(self, name, dataframes, copy):
        return recursive_join(name, dataframes, self.links, copy)

    @staticmethod
    def _invert(dictionary):
        return {v: k for k, v in dictionary.items()}

    def __repr__(self):
        return f"DataFrameContainer, contains: {', '.join(list(self.dataframes))}"


def _pretty_list(iterable) -> str:
    return "\n".join([f"\t{c}" for c in sorted(iterable)])


def flow_report_by_attribute(dataframes: DataFrameContainer, name, *args, **kwargs):
    """See `trase.tools.sei_pcs.reporting.print_report_by_attribute`"""
    df = dataframes.get(name)
    print_report_by_attribute(df, *args, **kwargs)


def construct_export_dataframe(
    dataset: str, container: DataFrameContainer, export_columns: List[Export]
) -> pd.DataFrame:
    column_renames = {c.flow_attribute: c.header for c in export_columns}
    df = container.get(dataset)
    df = df[column_renames.keys()]
    df = df.rename(columns=column_renames, errors="raise")
    return df
