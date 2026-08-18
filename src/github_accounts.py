"""GitHub accounts the dashboard can act as, stored in the environment.

The repo's rule for secrets is that they live in the environment and never in
`prsentinel.yml` — `providers.py` reads LLM tokens that way. GitHub tokens
follow it, with one addition: there can be more than one, so an operator can
hold a personal and a work account at once and switch between them.

Three variables carry the whole store, written to `.env` (already gitignored)
and read back by `config._load_dotenv()`, so the CLI, the poller and the web
server all see the same active account:

    PRS_GH_ACCOUNTS=nv-minh,acme-bot   # the roster, in the order it was built
    PRS_GH_ACCOUNT=nv-minh             # which one calls are made as
    PRS_GH_TOKEN_NV_MINH=ghp_...       # one token per account

The per-account variable name is derived from the login, because an env var
cannot hold a dict. That mapping is lossy (`a-b` and `a_b` both slug to `A_B`),
so `add_account` refuses a login that would land on another account's variable
rather than overwrite it.

Nothing here ever returns a token to a caller that asked for account *status* —
`list_accounts()` reports only whether one is present, the way
`providers.describe()` does.
"""
import os
import re
import threading
from pathlib import Path

import config  # noqa: F401  — importing it loads .env into os.environ

ACCOUNTS_VAR = "PRS_GH_ACCOUNTS"
ACTIVE_VAR = "PRS_GH_ACCOUNT"
TOKEN_PREFIX = "PRS_GH_TOKEN_"
ENV_PATH = Path(".env")

# Held while the store is rewritten, and while `gh` copies the environment to
# build a subprocess env. Without it, connecting an account from a request
# thread can grow os.environ underneath a `{**os.environ}` in a running review
# thread, which raises "dictionary changed size during iteration".
LOCK = threading.RLock()


def slug(login: str) -> str:
    """The env-var-safe form of a login: `nv-minh` -> `NV_MINH`."""
    return re.sub(r"[^A-Z0-9]", "_", login.upper())


def token_var(login: str) -> str:
    return TOKEN_PREFIX + slug(login)


def _env(env: dict | None = None):
    """The mapping to read from: a caller's dict, or the process environment."""
    return os.environ if env is None else env


def logins(env: dict | None = None) -> list[str]:
    """Every configured account, in roster order."""
    raw = _env(env).get(ACCOUNTS_VAR, "") or ""
    seen, out = set(), []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def active_login(env: dict | None = None) -> str:
    """The account calls are made as, or "" when none is configured.

    A pointer at an account that is no longer in the roster falls back to the
    first one rather than silently authenticating as nobody.
    """
    names = logins(env)
    if not names:
        return ""
    current = (_env(env).get(ACTIVE_VAR) or "").strip()
    return current if current in names else names[0]


def active_token(env: dict | None = None) -> str:
    login = active_login(env)
    return (_env(env).get(token_var(login), "") or "").strip() if login else ""


def list_accounts(env: dict | None = None) -> list[dict]:
    """Account status for the dashboard. Never includes a token."""
    current = active_login(env)
    return [{"login": name,
             "active": name == current,
             "token_present": bool((_env(env).get(token_var(name)) or "").strip())}
            for name in logins(env)]


def verify_token(token: str, *, gh=None) -> str:
    """Which account this token belongs to. Raises ValueError if GitHub says no.

    The token is passed to one `gh api user` call without being stored, so a
    typo never reaches `.env`.
    """
    token = (token or "").strip()
    if not token:
        raise ValueError("token is required")
    if gh is None:
        from gh import run_gh
        gh = run_gh
    try:
        data = gh(["api", "user"], token=token)
    except (RuntimeError, OSError) as e:
        raise ValueError(f"GitHub rejected this token: {e}") from e
    login = data.get("login") if isinstance(data, dict) else None
    if not login:
        raise ValueError("GitHub accepted the token but returned no login")
    return str(login)


# ------------------------------------------------------------------------ writing

def _write_env_file(path: Path, updates: dict, removals: tuple = ()) -> None:
    """Set/remove keys in a KEY=VALUE file, leaving every other line untouched.

    Line-oriented rather than a parse-and-dump, for the reason
    `autoreview_config.set_language` rewrites one line of YAML: the operator's
    comments and ordering in `.env` have to survive a click in the dashboard.
    """
    for key, value in updates.items():
        if "\n" in str(value) or "\r" in str(value):
            raise ValueError(f"{key} value must be a single line")
    lines = path.read_text().splitlines() if path.exists() else []
    pending = dict(updates)
    out: list[str] = []
    for line in lines:
        key = ""
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
        if key and key in removals:
            continue
        if key and key in pending:
            out.append(f"{key}={pending.pop(key)}")
            continue
        out.append(line)
    out.extend(f"{key}={value}" for key, value in pending.items())

    text = "".join(f"{line}\n" for line in out)
    tmp = path.parent / (path.name + ".tmp")
    # The mode is set as the file is created, not after it is written: umask
    # would otherwise leave a token sitting in a world-readable file for the
    # length of the write. O_CREAT's mode is ignored when the file already
    # exists (a crashed earlier write), so chmod covers that case too.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _apply(updates: dict, removals: tuple, env_path: Path | None,
           env: dict | None) -> None:
    with LOCK:
        _write_env_file(env_path or ENV_PATH, updates, removals)
        target = _env(env)
        for key in removals:
            target.pop(key, None)
        target.update(updates)


def add_account(token: str, *, env_path: Path | None = None,
                env: dict | None = None, gh=None) -> str:
    """Verify a token, store it, and make its account the active one."""
    login = verify_token(token, gh=gh)
    names = logins(env)
    clash = next((n for n in names if n != login and slug(n) == slug(login)), None)
    if clash is not None:
        raise ValueError(
            f"{login!r} and the already configured {clash!r} both map to "
            f"{token_var(login)}; remove {clash!r} first")
    if login not in names:
        names.append(login)
    _apply({token_var(login): token.strip(),
            ACCOUNTS_VAR: ",".join(names),
            ACTIVE_VAR: login}, (), env_path, env)
    return login


def set_active(login: str, *, env_path: Path | None = None,
               env: dict | None = None) -> str:
    if login not in logins(env):
        raise ValueError(f"no GitHub account named {login!r}")
    _apply({ACTIVE_VAR: login}, (), env_path, env)
    return login


def remove_account(login: str, *, env_path: Path | None = None,
                   env: dict | None = None) -> str:
    """Forget an account. The active pointer moves to whoever is left."""
    names = logins(env)
    if login not in names:
        raise ValueError(f"no GitHub account named {login!r}")
    names = [n for n in names if n != login]
    current = active_login(env)
    updates = {ACCOUNTS_VAR: ",".join(names),
               ACTIVE_VAR: names[0] if (current == login and names) else current}
    if not names:
        updates[ACTIVE_VAR] = ""
    _apply(updates, (token_var(login),), env_path, env)
    return login
