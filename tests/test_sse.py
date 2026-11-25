from datetime import UTC, datetime

from sse import build_key, event_time, read_events

SAMPLE = [
    ": hello\n",
    "event: message\n",
    'id: [{"topic":"t","partition":0,"timestamp":1}]\n',
    'data: {"meta":{"dt":"2026-11-25T10:00:00Z","id":"a"}}\n',
    "\n",
    'id: [{"topic":"t","partition":0,"timestamp":2}]\n',
    'data: {"meta":{"dt":"2026-11-25T10:00:01Z","id":"b"}}\n',
    "\n",
]


def test_read_events_pairs_ids_with_data():
    events = list(read_events(SAMPLE))
    assert len(events) == 2
    assert events[0][0].startswith('[{"topic"')
    assert '"id":"a"' in events[0][1]


def test_read_events_accepts_bytes():
    assert len(list(read_events([line.encode() for line in SAMPLE]))) == 2


def test_event_time_parses_utc():
    dt = event_time('{"meta":{"dt":"2026-11-25T10:00:00Z"}}')
    assert dt == datetime(2026, 11, 25, 10, 0, tzinfo=UTC)


def test_event_time_bad_input_returns_none():
    assert event_time("not json") is None
    assert event_time('{"no":"meta"}') is None


def test_build_key_is_deterministic():
    dt = datetime(2026, 11, 25, 10, 5, tzinfo=UTC)
    assert build_key("abc", dt) == build_key("abc", dt)
    assert build_key("abc", dt) != build_key("xyz", dt)
    assert build_key("abc", dt).startswith("raw/wikimedia_recentchange/dt=2026-11-25/hr=10/")