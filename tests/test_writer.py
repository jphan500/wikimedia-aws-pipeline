import io
import json

import pyarrow.parquet as pq
from samples import GOOD
from transform import process_lines
from writer import SILVER_SCHEMA, rows_to_parquet_bytes


def test_parquet_roundtrip_matches_schema():
    silver, _, _ = process_lines([json.dumps(GOOD)], "enwiki")
    data = rows_to_parquet_bytes(silver, "raw/x.jsonl.gz")
    table = pq.read_table(io.BytesIO(data))
    assert table.num_rows == 1
    assert table.schema.names == SILVER_SCHEMA.names
    assert table.to_pylist()[0]["_source_key"] == "raw/x.jsonl.gz"