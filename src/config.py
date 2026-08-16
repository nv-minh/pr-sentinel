"""Configuration from the environment. All env vars are optional.

A `.env` file next to the working directory is loaded first (simple KEY=VALUE
parser — no dotenv dependency); real environment variables win over it.

Auth note: `api_key` may be empty. The Claude Agent SDK also accepts the
credentials of a logged-in Claude Code CLI, so `has_auth()` treats a configured
CLI (`~/.claude.json`) as valid auth too.
"""
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_CLAIMS_MODEL = "claude-haiku-4-5-20251001"
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
    api_key: str
    model: str
    claims_model: str
    session_root: Path
    slack_webhook: str

    def has_auth(self) -> bool:
        """True if the SDK can authenticate: an API key, or a logged-in CLI."""
        return bool(self.api_key) or CLI_CONFIG.exists()


def load_config() -> Config:
    return Config(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        model=os.environ.get("PRS_MODEL", DEFAULT_MODEL),
        claims_model=os.environ.get("PRS_CLAIMS_MODEL", DEFAULT_CLAIMS_MODEL),
        session_root=Path(os.environ.get("PRS_SESSION_ROOT", "sessions")),
        slack_webhook=os.environ.get("SLACK_WEBHOOK_URL", ""),
    )
