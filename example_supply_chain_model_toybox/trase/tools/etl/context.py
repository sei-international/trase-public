from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass
class Context:
    """Simple container for useful information about a model.

    This object can be passed around the preparation script, run script, or elsewhere,
    to provide global variables for a model.

    If the variable is really a hard-coded constant, consider putting it in a file
    like `constants.py` instead.

    Args:
        year: the year for which the model is related to. This will be used, for
            example, in conjunction with the `data_directory` argument to determine
            where to store input and output data for the model.
        data_directory: path to a directory on the local file system which should be
            used to store input and output data for the model.
        extra (optional): a dictionary of extra metadata for the model, such as a model
            parameter.
        pre_extracted_data (optional): dataframes to pass to the preparation files.
    """

    year: int
    data_directory: str
    extra: Optional[dict] = field(default_factory=dict)
    pre_extracted_data: Optional[dict] = None

    def replace(self, **changes):
        """Return a copy of the instance except with some fields overwritten.

        This method is identical to
        [`dataclasses.replace`](https://docs.python.org/3/library/dataclasses.html#dataclasses.replace)
        except that it will handle overwriting only a subset of keys of `extra`:

        ```python
        # we have two pieces of extra information: "complex" and "percent"
        old = Context(2013, "/tmp/", extra=dict(complex=True, percent=10))

        # we alter percent only
        new = old.replace(extra=dict(percent=50))

        # percent has updated, but complex is unchanged
        new.extra["complex"]  # True
        new.extra["percent"]  # 50
        ```

        If you do not wish to have this behaviour then simply use `dataclasses.replace`
        """
        if "extra" in changes:
            changes = dict(changes, extra=dict(self.extra, **changes["extra"]))
        return replace(self, **changes)
