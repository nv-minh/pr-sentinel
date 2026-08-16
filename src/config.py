"""Configuration from the environment. All env vars are optional.

A `.env` file next to the working directory is loaded first (simple KEY=VALUE
parser — no dotenv dependency); real environment variables win over it.

Model and provider defaults deliberately live in `providers.py`, not here: this
module only reports what the environment said, and empty means "the provider
decides". Auth is provider-dependent too — see `providers.has_auth()`.
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
    api_key: str
    auth_token: str
    base_url: str
    provider: str
    model: str
    claims_model: str
    session_root: Path
    slack_webhook: str

    def has_auth(self) -> bool:
        """True if the SDK can authenticate: a token, or a logged-in CLI.

        Deprecated: auth depends on which provider is active — see
        `providers.has_auth()`. Kept until run.py and web/server.py move over.
        """
        return bool(self.api_key or self.auth_token) or CLI_CONFIG.exists()


def load_config() -> Config:
    return Config(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ""),
        provider=os.environ.get("PRS_PROVIDER", ""),
        model=os.environ.get("PRS_MODEL", ""),
        claims_model=os.environ.get("PRS_CLAIMS_MODEL", ""),
        session_root=Path(os.environ.get("PRS_SESSION_ROOT", "sessions")),
        slack_webhook=os.environ.get("SLACK_WEBHOOK_URL", ""),
    )
