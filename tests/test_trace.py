"""web/trace.py — transcript records to a timeline, defensively.

No real transcript is committed to the repo, so the record shapes are the
synthetic SDK/CLI rows the project already models in test_session_store.py.
"""
import json

from web.trace import parse_events, pr_trace


def _assistant(content):
    return {"type": "assistant", "uuid": "u", "message": {"content": content}}


def test_parse_events_reads_text_and_tool_use():
    records = [
        _assistant([{"type": "text", "text": "  Looking at auth.  "}]),
        _assistant([{"type": "tool_use", "name": "Grep", "input": {"pattern": "price_for"}}]),
    ]
    assert parse_events(records) == [
        {"type": "text", "summary": "Looking at auth."},
        {"type": "tool", "tool": "Grep", "summary": "price_for"},
    ]


def test_parse_events_handles_string_content():
    assert parse_events([_assistant("plain text turn")]) == [
        {"type": "text", "summary": "plain text turn"}]


def test_parse_events_skips_unknown_record_shapes():
    records = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "summary", "summary": "compacted"},
        {"no": "message"},
        _assistant([{"type": "mystery"}, "not a dict", {"type": "text", "text": "   "}]),
        _assistant(42),
        "not even a dict",
    ]
    assert parse_events(records) == []


def test_tool_summary_prefers_the_known_arg_and_truncates():
    long = "x" * 500
    events = parse_events([
        _assistant([{"type": "tool_use", "name": "Bash", "input": {"command": long}}]),
        _assistant([{"type": "tool_use", "name": "Custom", "input": {"n": 3, "q": "query"}}]),
        _assistant([{"type": "tool_use", "name": "Empty", "input": {}}]),
    ])
    assert events[0]["summary"] == "x" * 160
    assert events[1]["summary"] == "query"
    assert events[2] == {"type": "tool", "tool": "Empty", "summary": ""}


def _session(tmp_path, usage, transcripts):
    d = tmp_path / "o" / "r" / "pr-1"
    (d / "transcripts").mkdir(parents=True)
    (d / "usage.json").write_text(json.dumps(usage))
    for name, records in transcripts.items():
        lines = [json.dumps(r) if not isinstance(r, str) else r for r in records]
        (d / "transcripts" / f"{name}.jsonl").write_text("\n".join(lines))
    return d


def test_pr_trace_skips_phases_without_a_transcript_file(tmp_path):
    _session(tmp_path,
             [{"phase": "claims", "session_id": "gone"},
              {"phase": "verify", "session_id": "v-1"},
              {"phase": "score"}],
             {"v-1": [_assistant([{"type": "text", "text": "checking"}])]})
    assert pr_trace(tmp_path, "o", "r", 1) == [
        {"phase": "verify", "session_id": "v-1",
         "events": [{"type": "text", "summary": "checking"}]}]


def test_pr_trace_sanitises_the_session_id_like_the_writer(tmp_path):
    from session_store import _safe
    sid = "v/../1"
    _session(tmp_path, [{"phase": "verify", "session_id": sid}],
             {_safe(sid): [_assistant([{"type": "text", "text": "safe"}])]})
    assert pr_trace(tmp_path, "o", "r", 1)[0]["events"][0]["summary"] == "safe"


def test_pr_trace_is_empty_when_nothing_exists(tmp_path):
    assert pr_trace(tmp_path, "o", "r", 1) == []
