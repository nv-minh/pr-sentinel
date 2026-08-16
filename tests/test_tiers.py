from tiers import TIERS, classify, settings

GATE = {"sensitive_areas": ["**/payment*/**", "**/auth*/**", "**/migrations/**"]}


def _snap(files):
    return {"files": [{"filename": f, "additions": 5, "deletions": 5} for f in files]}


def test_a_docs_only_pr_is_trivial():
    assert classify(_snap(["README.md", "docs/guide.md"]), GATE) == "trivial"


def test_a_style_only_pr_is_trivial():
    assert classify(_snap(["app.css", "notes.txt"]), GATE) == "trivial"


def test_a_logic_change_is_standard():
    assert classify(_snap(["src/app.py"]), GATE) == "standard"


def test_a_sensitive_path_is_critical():
    assert classify(_snap(["src/payments/charge.py"]), GATE) == "critical"


def test_a_migration_is_critical():
    assert classify(_snap(["db/migrations/001_add.sql"]), GATE) == "critical"


def test_a_contract_file_is_critical():
    assert classify(_snap(["api/openapi.yaml"]), GATE) == "critical"


def test_a_proto_is_critical():
    assert classify(_snap(["rpc/user.proto"]), GATE) == "critical"


def test_sensitive_beats_docs_only():
    assert classify(_snap(["README.md", "src/auth/login.py"]), GATE) == "critical"


def test_a_large_docs_change_is_still_trivial():
    snap = {"files": [{"filename": "docs/a.md", "additions": 900, "deletions": 900}]}
    assert classify(snap, GATE) == "trivial"


def test_a_huge_logic_change_is_not_trivial():
    snap = {"files": [{"filename": "src/a.py", "additions": 900, "deletions": 0}]}
    assert classify(snap, GATE) == "standard"


def test_an_empty_pr_is_trivial():
    assert classify({"files": []}, GATE) == "trivial"


def test_classify_without_a_gate_uses_the_default_sensitive_areas():
    assert classify(_snap(["src/auth/login.py"])) == "critical"


def test_every_tier_has_settings():
    for tier in ("trivial", "standard", "critical"):
        knobs = settings(tier)
        assert set(knobs) == {"effort", "max_turns", "allow_bash", "use_claims_model"}


def test_the_trivial_tier_is_the_cheapest():
    assert settings("trivial")["use_claims_model"] is True
    assert settings("trivial")["allow_bash"] is False
    assert settings("trivial")["max_turns"] < settings("standard")["max_turns"]


def test_the_critical_tier_is_the_most_thorough():
    assert settings("critical")["allow_bash"] is True
    assert settings("critical")["effort"] == "high"
    assert settings("critical")["max_turns"] > settings("standard")["max_turns"]


def test_an_unknown_tier_falls_back_to_standard():
    assert settings("nonsense") == TIERS["standard"]
