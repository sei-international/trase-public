"""
Auto-reloading of Python code. Hopefully one day we can delete this in favour of
IPython's ``autoreload``.
"""

import importlib
import logging
from pathlib import Path
from types import ModuleType

from trase.tools.sei_pcs import constants

LOGGER = logging.getLogger(__name__)


def construct_module_name_from_filesystem_path(path_within_codebase: str) -> str:
    """
    Example:
        ```
        >>> path = "/path/to/codebase/orvessa/candy/model.py"
        >>> construct_module_name_from_filesystem_path(path)
        "orvessa.candy.model"
        ```

    """
    path_within_codebase = Path(path_within_codebase)
    relative_path = path_within_codebase.relative_to(constants.CODEBASE_ROOT)
    without_py_extension = relative_path.with_suffix("")
    return ".".join(without_py_extension.parts)


def reload_module_at_path(path_within_codebase: str) -> ModuleType:
    """
    Imports the target Python script as a module. The directory
    ``constants.CODEBASE_ROOT`` must be one of the parent directories of the path. Once
    imported, the module is also reloaded.
    """
    module_name = construct_module_name_from_filesystem_path(path_within_codebase)
    LOGGER.debug(f"Importing module {module_name} from {path_within_codebase}")
    module = importlib.import_module(module_name)
    importlib.reload(module)
    return module
