import gzip
import json

good = {
    "meta": {"id": "test-1", "dt": "2026-01-01T00:00:00Z"},
    "id": 1, "type": "edit", "namespace": 0, "title": "Test", "user": "Alice",
    "bot": False, "minor": False, "length": {"old": 100, "new": 150},
    "revision": {"old": 1, "new": 2}, "wiki": "enwiki", "comment": "test",
}
lines = [
    json.dumps(good),
    json.dumps({**good, "meta": {"id": "test-2", "dt": "2026-01-01T00:00:01Z"}, "wiki": "dewiki"}),
    "this is not json",
    json.dumps({**good, "meta": {"id": "test-3", "dt": "2026-01-01T00:00:02Z"}, "type": "weird"}),
    json.dumps(good),
]
with gzip.open("batch_test.jsonl.gz", "wt", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")