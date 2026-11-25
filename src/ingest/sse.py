"""Pure helpers: no AWS imports, so they are easy to unit test."""
import hashlib
import json
from datetime import UTC, datetime


def read_events(lines):
    """Turn raw SSE lines (bytes or str) into (event_id, data_json_string) pairs."""
    event_id = None
    data_parts = []
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        line = line.rstrip("\r\n")
        if line == "":
            if data_parts:
                yield event_id, "\n".join(data_parts)
            event_id = None
            data_parts = []
        elif line.startswith("id:"):
            event_id = line[3:].strip()
        elif line.startswith("data:"):
            data_parts.append(line[5:].lstrip())
        # ": keepalive" comments and "event:" lines are ignored


def event_time(data):
    """Return the event timestamp as an aware UTC datetime, or None if unreadable."""
    try:
        dt = datetime.fromisoformat(json.loads(data)["meta"]["dt"])
    except (ValueError, KeyError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def build_key(start_id, first_dt):
    """Same starting checkpoint -> same key, so a retried run overwrites, not duplicates."""
    batch_id = hashlib.sha256((start_id or "initial").encode()).hexdigest()[:16]
    return (
        "raw/wikimedia_recentchange/"
        f"dt={first_dt:%Y-%m-%d}/hr={first_dt:%H}/batch_{batch_id}.jsonl.gz"
    )