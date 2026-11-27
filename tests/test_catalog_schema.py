"""Fails if the Glue table columns in catalog.tf differ from the Parquet schema in writer.py."""
import re
from pathlib import Path

from writer import SILVER_SCHEMA

CATALOG = Path(__file__).parent.parent / "infra" / "envs" / "dev" / "catalog.tf"

ARROW_TO_GLUE = {
    "string": "string",
    "timestamp[ms, tz=UTC]": "timestamp",
    "int64": "bigint",
    "int32": "int",
    "bool": "boolean",
}


def glue_columns():
    text = CATALOG.read_text(encoding="utf-8")
    block = re.search(r"silver_columns\s*=\s*\[(.*?)\n\s*\]", text, re.S).group(1)
    return re.findall(r'name\s*=\s*"(\w+)",\s*type\s*=\s*"(\w+)"', block)


def test_glue_columns_match_parquet_schema():
    expected = [(f.name, ARROW_TO_GLUE[str(f.type)]) for f in SILVER_SCHEMA]
    assert glue_columns() == expected