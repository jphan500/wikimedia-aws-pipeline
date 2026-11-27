import gzip
import json
import os
from urllib.parse import unquote_plus

import boto3
from transform import process_lines
from writer import rows_to_parquet_bytes

RAW_PREFIX = "raw/wikimedia_recentchange/"
s3 = boto3.client("s3")


def output_keys(raw_key):
    """raw/.../dt=D/hr=H/batch_X.jsonl.gz -> silver and quarantine keys, same dt/hr/batch."""
    stem = raw_key[len(RAW_PREFIX):-len(".jsonl.gz")]
    return (
        f"silver/recentchange/{stem}.parquet",
        f"quarantine/recentchange/{stem}.jsonl.gz",
    )


def handler(event, context):
    target_wiki = os.environ.get("TARGET_WIKI", "enwiki")
    results = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])  # S3 URL-encodes keys (= becomes %3D)
        if not key.startswith(RAW_PREFIX):
            continue  # safety net: never process our own outputs

        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        lines = gzip.decompress(body).decode("utf-8").split("\n")  # not splitlines()
        silver, bad, stats = process_lines(lines, target_wiki)
        silver_key, quarantine_key = output_keys(key)

        if silver:
            s3.put_object(
                Bucket=bucket,
                Key=silver_key,
                Body=rows_to_parquet_bytes(silver, key),
                ContentType="application/octet-stream",
            )
        if bad:
            payload = "\n".join(json.dumps(b) for b in bad) + "\n"
            s3.put_object(
                Bucket=bucket,
                Key=quarantine_key,
                Body=gzip.compress(payload.encode("utf-8")),
                ContentType="application/gzip",
            )

        result = {"source_key": key, **stats}
        print(json.dumps(result))
        results.append(result)
    return results