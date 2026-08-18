"""Mirrored agent transcripts as a phase timeline. Pure logic, no HTTP.

A transcript line is one raw Claude Agent SDK record, the same rows the CLI
stores under ~/.claude/projects (see session_store.FileSessionStore). Only
assistant turns carry content worth showing; everything else — user rows,
summary rows, malformed lines — is skipped, never raised on. No real
transcript is committed to this repo, so the shapes are pinned by synthetic
fixtures in tests/test_trace.py.
"""
import json
from pathlib import Path

from session_store import _safe

SUMMARY_LEN = 160
TOOL_ARG = {"Read": "file_path", "Grep": "pattern", "Glob": "pattern",
            "Bash": "command"}


def _tool_summary(name: str, tool_input: dict) -> str:
    value = tool_input.get(TOOL_ARG.get(name, ""), "")
    if not value:
        value = next((v for v in tool_input.values() if isinstance(v, str)), "")
    return str(value)[:SUMMARY_LEN]


def parse_events(records) -> list[dict]:
    """Text and tool_use events from assistant records, in order."""
    events: list[dict] = []
    for record in records:
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        content = (record.get("message") or {}).get("content")
        if isinstance(content, str):
            if content.strip():
                events.append({"type": "text", "summary": content.strip()[:SUMMARY_LEN]})
            continue
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and (item.get("text") or "").strip():
                events.append({"type": "text",
                               "summary": item["text"].strip()[:SUMMARY_LEN]})
            elif item.get("type") == "tool_use":
                events.append({"type": "tool", "tool": item.get("name", ""),
                               "summary": _tool_summary(item.get("name", ""),
                                                        item.get("input") or {})})
    return events


def pr_trace(session_root: Path, owner: str, repo: str, n: int) -> list[dict]:
    """[{phase, session_id, events}] in usage.json order; [] when none exist."""
    session_dir = session_root / owner / repo / f"pr-{n}"
    try:
        usage = json.loads((session_dir / "usage.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    phases = []
    for entry in usage:
        if not isinstance(entry, dict) or not entry.get("session_id"):
            continue
        sid = str(entry["session_id"])
        path = session_dir / "transcripts" / f"{_safe(sid)}.jsonl"
        if not path.is_file():
            continue
        records = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        phases.append({"phase": entry.get("phase", ""), "session_id": sid,
                       "events": parse_events(records)})
    return phases
