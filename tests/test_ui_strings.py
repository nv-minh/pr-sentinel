"""The dashboard translates phase and metric labels by the ids web/metrics.py
emits. Those ids reach the UI at runtime, so the compiler cannot check them the
way it checks the rest of the dictionary — this test does it instead. A phase
added to metrics.py without a Vietnamese label fails here rather than silently
rendering English on a Vietnamese dashboard.
"""
import re
from pathlib import Path

from web.metrics import PHASES

STRINGS = Path(__file__).resolve().parents[1] / "web" / "ui" / "src" / "strings.ts"

# Every metric label _phase_metrics() can emit, kept here as the assertion's
# expectation: adding one to metrics.py means adding it here and translating it.
METRIC_LABELS = {"files", "commits", "pruned", "claims", "docs", "callers",
                 "contracts", "gate", "verified", "answered", "open", "patches",
                 "tests", "replies"}


def _keys() -> set[str]:
    text = STRINGS.read_text(encoding="utf-8")
    return set(re.findall(r"'([\w.]+)':", text))


def test_every_pipeline_phase_has_a_translated_label():
    keys = _keys()
    missing = [p["id"] for p in PHASES if f"graph.phase.{p['id']}" not in keys]
    assert not missing, f"untranslated pipeline phases: {missing}"


def test_every_phase_metric_has_a_translated_label():
    keys = _keys()
    missing = sorted(m for m in METRIC_LABELS if f"graph.metric.{m}" not in keys)
    assert not missing, f"untranslated phase metrics: {missing}"


def test_the_metric_label_list_still_matches_metrics_py():
    """If _phase_metrics() grows a label, this fails before the two above do,
    pointing at the real edit rather than at a stale expectation."""
    source = (Path(__file__).resolve().parents[1] / "web" / "metrics.py").read_text()
    body = source.split("def _phase_metrics(")[1].split("\ndef ")[0]
    found = set(re.findall(r'"label": "(\w+)"', body))
    assert found == METRIC_LABELS
