import pytest

import github_accounts as ga


def _env_file(tmp_path, text=""):
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_slug_makes_a_login_env_var_safe():
    assert ga.slug("nv-minh") == "NV_MINH"
    assert ga.token_var("acme.bot") == "PRS_GH_TOKEN_ACME_BOT"


def test_add_account_stores_the_token_and_makes_it_active(tmp_path):
    path = _env_file(tmp_path)
    env = {}
    login = ga.add_account("ghp_one", env_path=path, env=env,
                           gh=lambda args, **kw: {"login": "nv-minh"})

    assert login == "nv-minh"
    assert env["PRS_GH_ACCOUNTS"] == "nv-minh"
    assert env["PRS_GH_ACCOUNT"] == "nv-minh"
    assert env["PRS_GH_TOKEN_NV_MINH"] == "ghp_one"
    assert ga.active_token(env) == "ghp_one"
    assert "PRS_GH_TOKEN_NV_MINH=ghp_one" in path.read_text()


def test_add_account_verifies_the_token_before_writing_anything(tmp_path):
    path = _env_file(tmp_path, "EXISTING=1\n")
    env = {}

    def reject(args, **kw):
        raise RuntimeError("gh api failed: HTTP 401: Bad credentials")

    with pytest.raises(ValueError, match="GitHub rejected this token"):
        ga.add_account("ghp_bad", env_path=path, env=env, gh=reject)
    assert env == {}
    assert path.read_text() == "EXISTING=1\n"


def test_a_second_account_joins_the_roster_and_takes_over(tmp_path):
    path = _env_file(tmp_path)
    env = {}
    ga.add_account("ghp_one", env_path=path, env=env,
                   gh=lambda args, **kw: {"login": "nv-minh"})
    ga.add_account("ghp_two", env_path=path, env=env,
                   gh=lambda args, **kw: {"login": "acme-bot"})

    assert [a["login"] for a in ga.list_accounts(env)] == ["nv-minh", "acme-bot"]
    assert ga.active_login(env) == "acme-bot"
    assert ga.active_token(env) == "ghp_two"

    ga.set_active("nv-minh", env_path=path, env=env)
    assert ga.active_token(env) == "ghp_one"


def test_list_accounts_never_leaks_a_token(tmp_path):
    env = {}
    ga.add_account("ghp_secret", env_path=_env_file(tmp_path), env=env,
                   gh=lambda args, **kw: {"login": "nv-minh"})
    accounts = ga.list_accounts(env)
    assert accounts == [{"login": "nv-minh", "active": True, "token_present": True}]
    assert "ghp_secret" not in str(accounts)


def test_two_logins_that_slug_alike_are_refused_not_overwritten(tmp_path):
    path = _env_file(tmp_path)
    env = {}
    ga.add_account("ghp_one", env_path=path, env=env,
                   gh=lambda args, **kw: {"login": "a-b"})
    with pytest.raises(ValueError, match="PRS_GH_TOKEN_A_B"):
        ga.add_account("ghp_two", env_path=path, env=env,
                       gh=lambda args, **kw: {"login": "a_b"})
    assert env["PRS_GH_TOKEN_A_B"] == "ghp_one"


def test_removing_the_active_account_hands_over_to_the_next(tmp_path):
    path = _env_file(tmp_path)
    env = {}
    ga.add_account("ghp_one", env_path=path, env=env,
                   gh=lambda args, **kw: {"login": "nv-minh"})
    ga.add_account("ghp_two", env_path=path, env=env,
                   gh=lambda args, **kw: {"login": "acme-bot"})

    ga.remove_account("acme-bot", env_path=path, env=env)
    assert ga.active_login(env) == "nv-minh"
    assert "PRS_GH_TOKEN_ACME_BOT" not in env
    assert "ACME_BOT" not in path.read_text()

    ga.remove_account("nv-minh", env_path=path, env=env)
    assert ga.active_login(env) == ""
    assert ga.active_token(env) == ""


def test_removing_an_unknown_account_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no GitHub account"):
        ga.remove_account("ghost", env_path=_env_file(tmp_path), env={})


def test_writing_preserves_comments_and_unrelated_keys(tmp_path):
    path = _env_file(tmp_path, "# provider auth\nANTHROPIC_API_KEY=sk-ant\n\n"
                               "PRS_SESSION_ROOT=sessions\n")
    ga.add_account("ghp_one", env_path=path, env={},
                   gh=lambda args, **kw: {"login": "nv-minh"})
    text = path.read_text()

    assert "# provider auth" in text
    assert "ANTHROPIC_API_KEY=sk-ant" in text
    assert "PRS_SESSION_ROOT=sessions" in text
    assert "PRS_GH_ACCOUNT=nv-minh" in text


def test_rewriting_a_key_replaces_it_in_place(tmp_path):
    path = _env_file(tmp_path, "PRS_GH_TOKEN_NV_MINH=old\nAFTER=1\n")
    ga.add_account("ghp_new", env_path=path, env={},
                   gh=lambda args, **kw: {"login": "nv-minh"})
    lines = path.read_text().splitlines()

    assert "PRS_GH_TOKEN_NV_MINH=ghp_new" in lines
    assert "PRS_GH_TOKEN_NV_MINH=old" not in lines
    assert lines.index("PRS_GH_TOKEN_NV_MINH=ghp_new") < lines.index("AFTER=1")


def test_the_env_file_holding_a_token_is_not_world_readable(tmp_path):
    path = _env_file(tmp_path)
    ga.add_account("ghp_one", env_path=path, env={},
                   gh=lambda args, **kw: {"login": "nv-minh"})
    assert path.stat().st_mode & 0o077 == 0


def test_an_active_pointer_at_a_gone_account_falls_back(tmp_path):
    env = {"PRS_GH_ACCOUNTS": "nv-minh", "PRS_GH_ACCOUNT": "deleted",
           "PRS_GH_TOKEN_NV_MINH": "ghp_one"}
    assert ga.active_login(env) == "nv-minh"
    assert ga.active_token(env) == "ghp_one"


def test_no_accounts_configured_reports_nothing():
    assert ga.list_accounts({}) == []
    assert ga.active_login({}) == ""
    assert ga.active_token({}) == ""
