"""How much thinking a pull request is worth.

A markdown fix and a change to the payment path should not cost the same
review. This classifies a PR from its snapshot alone — no LLM, no I/O, like
score.py — and turns that into the agent's model, effort, turn limit and tools.

The sensitive-path list is `gate.sensitive_areas` from prsentinel.yml, reused
rather than duplicated: it already means "the parts of this repo where being
wrong is expensive", and two lists would drift apart.
"""
from score import DEFAULT_GATE, _matches

# Extensions that carry no executable behaviour on their own.
PROSE_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".css", ".scss")
# Contracts are critical wherever they live: breaking one breaks a consumer.
CONTRACT_SUFFIXES = (".proto", ".sql")
CONTRACT_HINTS = ("openapi", "swagger", "schema.graphql")

TIERS: dict[str, dict] = {
    "trivial": {"effort": "low", "max_turns": 15, "allow_bash": False,
                "use_claims_model": True},
    "standard": {"effort": "medium", "max_turns": 60, "allow_bash": False,
                 "use_claims_model": False},
    "critical": {"effort": "high", "max_turns": 90, "allow_bash": True,
                 "use_claims_model": False},
}


def _is_contract(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(CONTRACT_SUFFIXES) or any(h in lower for h in CONTRACT_HINTS)


def classify(snapshot: dict, gate: dict | None = None) -> str:
    """trivial / standard / critical, from the paths this PR touches."""
    sensitive = {**DEFAULT_GATE, **(gate or {})}["sensitive_areas"]
    paths = [f.get("filename", "") for f in snapshot.get("files") or []]

    if any(_matches(p, sensitive) or _is_contract(p) for p in paths):
        return "critical"
    if all(p.lower().endswith(PROSE_SUFFIXES) for p in paths):
        return "trivial"
    return "standard"


def settings(tier: str) -> dict:
    """The agent knobs for a tier. Unknown names fall back to standard."""
    return TIERS.get(tier, TIERS["standard"])
