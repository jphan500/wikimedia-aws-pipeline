"""Parse, filter, validate and flatten raw recentchange events. No I/O."""
import json
from datetime import UTC, datetime

VALID_TYPES = {"edit", "new", "log", "categorize", "external"}


def _int(value):
    """Return value if it is a real int (not bool), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_ts(value):
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def flatten(rec):
    """Return (row, None) or (None, error_code). A returned row always fits the schema."""
    meta = rec.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("id"), str) or not meta["id"]:
        return None, "missing_meta_id"
    event_ts = _parse_ts(meta.get("dt"))
    if event_ts is None:
        return None, "bad_event_time"
    rtype = rec.get("type")
    if rtype not in VALID_TYPES:
        return None, "unknown_type"
    namespace = _int(rec.get("namespace"))
    if namespace is None:
        return None, "bad_namespace"
    title, user = rec.get("title"), rec.get("user")
    if not isinstance(title, str) or not title or not isinstance(user, str) or not user:
        return None, "missing_title_or_user"

    length = rec["length"] if isinstance(rec.get("length"), dict) else {}
    revision = rec["revision"] if isinstance(rec.get("revision"), dict) else {}
    length_old, length_new = _int(length.get("old")), _int(length.get("new"))
    comment = rec.get("comment")

    return {
        "event_id": meta["id"],
        "event_ts": event_ts,
        "rc_id": _int(rec.get("id")),
        "wiki": rec["wiki"],
        "type": rtype,
        "namespace": namespace,
        "title": title,
        "user": user,
        "is_bot": bool(rec.get("bot", False)),
        "is_minor": bool(rec.get("minor", False)),
        "length_old": length_old,
        "length_new": length_new,
        "byte_delta": None if length_new is None else length_new - (length_old or 0),
        "revision_old": _int(revision.get("old")),
        "revision_new": _int(revision.get("new")),
        "comment": comment if isinstance(comment, str) else None,
    }, None


def process_lines(lines, target_wiki):
    """Return (silver_rows, quarantined, stats)."""
    silver, quarantined = [], []
    stats = {"read": 0, "silver": 0, "quarantined": 0, "filtered_out": 0, "duplicates": 0}
    seen = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        stats["read"] += 1
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                raise TypeError("not an object")
        except (ValueError, TypeError):
            quarantined.append({"_error": "invalid_json", "_raw": line})
            continue

        wiki = rec.get("wiki")
        if not isinstance(wiki, str) or not wiki:
            quarantined.append({"_error": "missing_wiki", "_raw": line})
            continue
        if wiki != target_wiki:
            stats["filtered_out"] += 1
            continue

        row, error = flatten(rec)
        if error:
            quarantined.append({"_error": error, "_raw": line})
            continue
        if row["event_id"] in seen:
            stats["duplicates"] += 1
            continue
        seen.add(row["event_id"])
        silver.append(row)

    stats["silver"] = len(silver)
    stats["quarantined"] = len(quarantined)
    return silver, quarantined, stats