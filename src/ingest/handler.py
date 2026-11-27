"""Ingest Lambda: reads the Wikimedia stream from the last checkpoint until caught up,
writes one raw batch to S3, then advances the checkpoint."""  

import gzip
import http.client
import json
import os
import time
import urllib.request
from datetime import UTC, datetime, timedelta

import boto3
from sse import build_key, event_time, read_events

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
CHECKPOINT_KEY = {"stream": "recentchange"}
CAUGHT_UP_SECONDS = 10

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["CHECKPOINT_TABLE"])


def open_stream(start_id):
    headers = {"User-Agent": os.environ["USER_AGENT"], "Accept": "text/event-stream"}
    url = STREAM_URL
    if start_id:
        headers["Last-Event-ID"] = start_id
    else:  # very first run: start 5 minutes back
        since = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        url = f"{STREAM_URL}?since={since}"
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=30)


def handler(event, context):
    max_seconds = int(os.environ.get("MAX_SECONDS", "90"))
    max_events = int(os.environ.get("MAX_EVENTS", "50000"))

    item = table.get_item(Key=CHECKPOINT_KEY).get("Item")
    start_id = item["last_event_id"] if item else None

    lines, last_id, first_dt = [], None, None
    began = time.monotonic()
    resp = open_stream(start_id)
    try:
        for event_id, data in read_events(resp):
            lines.append(data)
            last_id = event_id or last_id
            ev_dt = event_time(data)
            first_dt = first_dt or ev_dt
            age = (datetime.now(UTC) - ev_dt).total_seconds() if ev_dt else None
            caught_up = age is not None and age < CAUGHT_UP_SECONDS
            if caught_up or len(lines) >= max_events or time.monotonic() - began > max_seconds:
                break
    except (TimeoutError, ConnectionError, http.client.HTTPException) as exc:
        # Keep whatever we already read; it is valid up to last_id.
        print(json.dumps({"warning": "stream interrupted", "error": repr(exc)}))
    finally:
        resp.close()

    if not lines or last_id is None:
        print(json.dumps({"events": 0, "note": "nothing to write"}))
        return {"events": 0}

    key = build_key(start_id, first_dt or datetime.now(UTC))
    body = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"))

    # Order matters: write the data FIRST, then move the checkpoint.
    s3.put_object(
        Bucket=os.environ["LAKE_BUCKET"], Key=key, Body=body, ContentType="application/gzip"
    )
    table.put_item(
        Item={
            **CHECKPOINT_KEY,
            "last_event_id": last_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "events_in_last_batch": len(lines),
        }
    )

    result = {"events": len(lines), "key": key, "seconds": round(time.monotonic() - began, 1)}
    print(json.dumps(result))
    return result