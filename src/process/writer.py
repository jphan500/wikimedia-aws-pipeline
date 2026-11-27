import io

import pyarrow as pa
import pyarrow.parquet as pq

SILVER_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("event_ts", pa.timestamp("ms", tz="UTC")),
        ("rc_id", pa.int64()),
        ("wiki", pa.string()),
        ("type", pa.string()),
        ("namespace", pa.int32()),
        ("title", pa.string()),
        ("user", pa.string()),
        ("is_bot", pa.bool_()),
        ("is_minor", pa.bool_()),
        ("length_old", pa.int64()),
        ("length_new", pa.int64()),
        ("byte_delta", pa.int64()),
        ("revision_old", pa.int64()),
        ("revision_new", pa.int64()),
        ("comment", pa.string()),
        ("_source_key", pa.string()),
    ]
)


def rows_to_parquet_bytes(rows, source_key):
    stamped = [{**row, "_source_key": source_key} for row in rows]
    table = pa.Table.from_pylist(stamped, schema=SILVER_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()