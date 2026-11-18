import os.path

from pathlib import Path


CODEBASE_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)


def context_root() -> str:
    return os.path.join(CODEBASE_ROOT, "trase/models")


EXPORT_DELIMITER = ";"
EXPORT_QUOTE_CHAR = '"'
EXPORT_ENCODING = "UTF-8"
ID = "_id"
