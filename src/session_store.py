"""Mirror agent transcripts into the session directory.

`resume=<session_id>` replays a conversation from the Claude Code CLI's own
transcript store under `~/.claude/projects/`. On an ephemeral CI runner that
directory is gone by the time someone replies on the PR, so the follow-up pass
degrades into a full re-review without saying so.

The SDK accepts a `session_store` adapter: it receives a copy of every
transcript line, and is read back before a resume. Pointing it at the session
directory makes the transcript one more phase artifact beside findings.json —
restore `sessions/` and the resume works on any machine.

Duck-typed on purpose: the SDK probes for methods rather than using
`isinstance`, so only the two required ones are implemented.
"""
import json
from pathlib import Path

TRANSCRIPTS = "transcripts"


def _safe(part: str) -> str:
    """One path segment: no separators, no traversal, never empty."""
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in part)
    return cleaned.strip(".") or "_"


class FileSessionStore:
    """One JSONL file per session (plus one per subagent) under the session dir."""

    def __init__(self, session_dir: Path | str):
        self.root = Path(session_dir) / TRANSCRIPTS
        self._seen: dict[Path, set[str]] = {}

    def path_for(self, key: dict) -> Path:
        name = _safe(key["session_id"])
        subpath = key.get("subpath")
        if subpath:
            name = f"{name}__{_safe(subpath)}"
        return self.root / f"{name}.jsonl"

    async def append(self, key: dict, entries: list[dict]) -> None:
        """Mirror a batch of transcript lines, dropping uuids already written."""
        if not entries:
            return
        path = self.path_for(key)
        seen = self._uuids(path)
        fresh = []
        for entry in entries:
            uid = entry.get("uuid")
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)
            fresh.append(entry)
        if not fresh:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            for entry in fresh:
                fh.write(json.dumps(entry) + "\n")

    async def load(self, key: dict) -> list[dict] | None:
        """Every entry for a key, or None when it was never written."""
        path = self.path_for(key)
        if not path.exists():
            return None
        return list(self._read(path))

    def _uuids(self, path: Path) -> set[str]:
        """Uuids already on disk for this key, read once per store instance."""
        if path not in self._seen:
            self._seen[path] = {e["uuid"] for e in self._read(path) if e.get("uuid")}
        return self._seen[path]

    def _read(self, path: Path):
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
