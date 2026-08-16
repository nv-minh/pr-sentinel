import asyncio
import json

from session_store import FileSessionStore

KEY = {"project_key": "p", "session_id": "sess-1"}
SUB = {"project_key": "p", "session_id": "sess-1", "subpath": "subagents/agent-2"}


def _append(store, key, entries):
    asyncio.run(store.append(key, entries))


def _load(store, key):
    return asyncio.run(store.load(key))


def test_append_then_load_round_trips(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"},
                         {"type": "assistant", "uuid": "b"}])
    assert _load(store, KEY) == [{"type": "user", "uuid": "a"},
                                 {"type": "assistant", "uuid": "b"}]


def test_transcript_lands_under_the_session_dir(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    assert store.root == tmp_path / "transcripts"
    assert (tmp_path / "transcripts" / "sess-1.jsonl").exists()


def test_a_repeated_uuid_is_written_once(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    _append(store, KEY, [{"type": "user", "uuid": "a"},
                         {"type": "assistant", "uuid": "b"}])
    assert [e["uuid"] for e in _load(store, KEY)] == ["a", "b"]


def test_entries_without_a_uuid_are_always_appended(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "title"}])
    _append(store, KEY, [{"type": "title"}])
    assert len(_load(store, KEY)) == 2


def test_dedup_survives_a_new_store_instance(tmp_path):
    _append(FileSessionStore(tmp_path), KEY, [{"type": "user", "uuid": "a"}])
    _append(FileSessionStore(tmp_path), KEY, [{"type": "user", "uuid": "a"}])
    assert len(_load(FileSessionStore(tmp_path), KEY)) == 1


def test_load_of_an_unwritten_key_is_none(tmp_path):
    assert _load(FileSessionStore(tmp_path), KEY) is None


def test_a_subagent_transcript_is_a_separate_file(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    _append(store, SUB, [{"type": "user", "uuid": "z"}])
    assert store.path_for(KEY) != store.path_for(SUB)
    assert [e["uuid"] for e in _load(store, SUB)] == ["z"]


def test_a_subpath_cannot_escape_the_transcript_dir(tmp_path):
    store = FileSessionStore(tmp_path)
    escaping = {"project_key": "p", "session_id": "s", "subpath": "../../etc/passwd"}
    assert store.path_for(escaping).parent == store.root


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    path = store.path_for(KEY)
    path.write_text(path.read_text() + "{not json\n")
    assert [e["uuid"] for e in _load(store, KEY)] == ["a"]


def test_appending_nothing_creates_no_file(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [])
    assert not store.root.exists()


def test_entries_are_json_serialisable_round_trip(tmp_path):
    store = FileSessionStore(tmp_path)
    nested = {"type": "assistant", "uuid": "a",
              "message": {"content": [{"type": "text", "text": "hi"}]}}
    _append(store, KEY, [nested])
    assert json.loads(store.path_for(KEY).read_text().strip()) == nested
