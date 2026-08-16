"""A whole review on a prompt-mode gateway, with the SDK faked out.

Guards the seam that `--fixtures` cannot reach: claims and verify actually run,
but the transport is a stub, so the assertion is "the phases produce valid
artifacts through the prompt-mode path", not "the model is smart".
"""
import json
from types import SimpleNamespace

import agent
import claims as claims_mod
import providers
import verify as verify_mod

SNAPSHOT = {
    "owner": "demo", "repo": "app", "pr": 1, "title": "Speed up checkout",
    "body": "Caches the price lookup. No behaviour change.",
    "base": "main", "head": "perf/x", "head_sha": "abc123",
    "files": [{"filename": "src/pricing.py", "additions": 10, "deletions": 2}],
    "commits": [], "threads": [], "pruned": [],
}

CLAIMS_REPLY = json.dumps({"claims": [
    {"id": "C1", "text": "Caches the price lookup", "category": "perf",
     "files": ["src/pricing.py"], "docs": []}]})

FINDINGS_REPLY = json.dumps({
    "claims": [{"id": "C1", "status": "PASS", "evidence": ["src/pricing.py:12"],
                "note": "", "confidence": 0.9}],
    "docs": [], "impact": [], "callers_outside_diff": [], "contracts": [],
    "tests": [], "threads": [], "unresolved_questions": [],
})


def _sdk(monkeypatch, replies):
    """Fake the SDK, handing back `replies` in order as free text."""
    queue = list(replies)
    prompts = []

    async def fake_query(prompt, options):
        prompts.append(prompt)
        return SimpleNamespace(
            subtype="success", session_id="sess-1", total_cost_usd=0.9,
            num_turns=3, duration_ms=100, structured_output=None,
            result=queue.pop(0))

    monkeypatch.setattr(agent, "_query", fake_query)
    return prompts


def test_prompt_mode_provider_completes_claims_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zai-token")
    prompts = _sdk(monkeypatch, [CLAIMS_REPLY, FINDINGS_REPLY])
    cfg = {"provider": providers.build("glm", None), "model": "glm-5.2",
           "claims_model": "glm-4.7", "max_turns": 10}

    extracted = claims_mod.extract_claims(SNAPSHOT, cfg, tmp_path)
    assert extracted[0]["id"] == "C1"
    assert json.loads((tmp_path / "claims.json").read_text())[0]["category"] == "perf"

    findings = verify_mod.run_verify(cfg, tmp_path, tmp_path, SNAPSHOT, extracted)
    assert findings["claims"][0]["status"] == "PASS"
    assert (tmp_path / "findings.json").exists()

    # The schema travelled in the prompt, because the gateway cannot enforce it.
    assert "ONE JSON object" in prompts[0]
    assert "unresolved_questions" in prompts[1]

    # Cost is not invented for a provider that cannot price itself.
    usage = json.loads((tmp_path / "usage.json").read_text())
    assert all(entry["cost_usd"] is None for entry in usage)
