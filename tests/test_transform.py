import json

from samples import GOOD
from transform import process_lines


def run(*records, wiki="enwiki"):
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    return process_lines(lines, wiki)


def test_valid_event_becomes_silver_row():
    silver, bad, stats = run(GOOD)
    assert len(silver) == 1 and not bad
    assert silver[0]["byte_delta"] == 50
    assert silver[0]["event_ts"].tzinfo is not None
    assert stats["silver"] == 1


def test_other_wiki_is_filtered_not_quarantined():
    silver, bad, stats = run({**GOOD, "wiki": "dewiki"})
    assert not silver and not bad
    assert stats["filtered_out"] == 1


def test_invalid_json_is_quarantined_with_raw_preserved():
    silver, bad, _ = run("this is not json")
    assert not silver
    assert bad[0]["_error"] == "invalid_json"
    assert bad[0]["_raw"] == "this is not json"


def test_unknown_type_is_quarantined():
    _, bad, _ = run({**GOOD, "type": "weird"})
    assert bad[0]["_error"] == "unknown_type"


def test_duplicates_are_dropped():
    silver, _, stats = run(GOOD, GOOD)
    assert len(silver) == 1
    assert stats["duplicates"] == 1


def test_new_page_byte_delta_treats_missing_old_as_zero():
    silver, _, _ = run({**GOOD, "type": "new", "length": {"new": 300}})
    assert silver[0]["byte_delta"] == 300


def test_wrong_field_type_cannot_break_the_schema():
    silver, bad, _ = run({**GOOD, "id": "not-an-int"})
    assert not bad
    assert silver[0]["rc_id"] is None