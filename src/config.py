"""Session and notification settings from the environment.

A `.env` file next to the working directory is loaded first (simple KEY=VALUE
parser — no dotenv dependency); real environment variables win over it.

Everything about LLM routing — which provider is active, its models, its auth —
is read through `providers.py` from the environment and `prsentinel.yml`;
this module only carries the two settings every entry point needs.
"""
import os
from dataclasses import dataclass
from pathlib import Path

CLI_CONFIG = Path.home() / ".claude.json"
AUTH_HINT = ("no Claude auth found: set ANTHROPIC_API_KEY (see .env.example) "
             "or log in with the Claude Code CLI")


def _load_dotenv() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Config:
    session_root: Path
    slack_webhook: str


def load_config() -> Config:
    return Config(
        session_root=Path(os.environ.get("PRS_SESSION_ROOT", "sessions")),
        slack_webhook=os.environ.get("SLACK_WEBHOOK_URL", ""),
    )
