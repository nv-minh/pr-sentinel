"""Phase 5: turn findings into report.md and into one comment on the PR."""
import json
from pathlib import Path

import poc
import untrusted
from gh import run_gh

MARKER = "<!-- pr-sentinel -->"
STATUS_LABELS = {"PASS": "Matches", "FAIL": "Mismatch", "PARTIAL": "Partial",
                 "UNVERIFIED": "Unverified"}
GATE_LABELS = {"pass": "PASS", "warn": "WARNING", "fail": "BLOCKED"}


def _cell(text, max_len=200):
    text = str(text if text is not None else "")
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text.replace("|", "\\|").replace("\n", "<br>")


def _bullet(text, max_len=100):
    text = str(text if text is not None else "")
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text.replace("\n", " ")


def _confidence(value) -> str:
    # A prompt-mode provider's JSON isn't schema-enforced server-side, so a
    # non-numeric confidence is a real possibility — degrade rather than raise.
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "?"


def _overall_verdict(findings: dict) -> str:
    statuses = [c["status"] for c in findings.get("claims", [])]
    if not statuses:
        return "NO CLAIMS"
    if any(s == "FAIL" for s in statuses):
        return "MISLEADING"
    if any(s in ("PARTIAL", "UNVERIFIED") for s in statuses):
        return "PARTIAL"
    return "ACCURATE"


def _table(lines: list[str], header: str, columns: list[str], rows: list[list[str]],
           empty: str = "- (none)") -> None:
    lines += ["", f"## {header}", ""]
    if not rows:
        lines.append(empty)
        return
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "---|" * len(columns))
    lines += ["| " + " | ".join(row) + " |" for row in rows]


def build_report(snapshot: dict, claims: list[dict], findings: dict,
                 answers: list[dict], session_dir: Path,
                 scores: dict | None = None, cost_usd: float = 0.0) -> str:
    """Write report.md. Returns the report content."""
    verdict = _overall_verdict(findings)
    text_by_id = {cl["id"]: cl.get("text", "") for cl in claims}
    lines = [
        f"# Review PR #{snapshot['pr']} — {snapshot['title']}",
        "",
        f"- Author: {snapshot['author']} | Base: {snapshot['base']} → Head: {snapshot['head']}",
        f"- Files changed: {len(snapshot['files'])} | Commits: {len(snapshot['commits'])}",
        f"## Verdict: {verdict}",
    ]
    if scores:
        lines += [
            "",
            f"- Gate: **{GATE_LABELS.get(scores['gate'], scores['gate'])}** | "
            f"Verification score: {scores['verification_score']:.0%} | "
            f"Business risk: {scores['business_risk']}",
        ]
        for reason in scores.get("reasons", []):
            lines.append(f"  - {_bullet(reason, 200)}")

    try:
        ticket = json.loads((session_dir / "ticket.json").read_text())
    except (OSError, json.JSONDecodeError):
        ticket = None
    if isinstance(ticket, dict):
        if ticket.get("primary"):
            url = (ticket.get("tickets") or [{}])[0].get("url", "")
            lines += ["", f"- Requirement: judged against {ticket['primary']}"
                           + (f" ({url})" if url else "")]
        elif ticket.get("skipped"):
            lines += ["", f"- Requirement: none available — {ticket['skipped']}"]

    _table(lines, "Claims", ["Claim", "Content", "Status", "Evidence", "Notes"],
           [[c["id"], _cell(text_by_id.get(c["id"], c.get("text", ""))),
             STATUS_LABELS.get(c["status"], c["status"]),
             _cell(", ".join(c.get("evidence", [])) or "-"), _cell(c.get("note", ""))]
            for c in findings.get("claims", [])])

    _table(lines, "Docs vs reality", ["Doc", "Status", "Difference"],
           [[_cell(d["path"]), d["status"], _cell(d.get("what", ""))]
            for d in findings.get("docs", [])])

    _table(lines, "Requirement impact", ["Requirement", "Impact", "Area", "Detail"],
           [[_cell(i["requirement"]), i["impact"], _cell(i.get("area", "-")),
             _cell(i.get("detail", ""))] for i in findings.get("impact", [])])

    _table(lines, "Callers outside the diff",
           ["Symbol", "Defined at", "Callers", "Risk", "Notes"],
           [[_cell(c.get("symbol", "")), _cell(c.get("defined_at", "-")),
             _cell(", ".join(c.get("callers", [])) or "-"), c.get("risk", "-"),
             _cell(c.get("note", ""))]
            for c in findings.get("callers_outside_diff", [])],
           empty="- No symbol changed in a way that reaches code outside this PR.")

    _table(lines, "Contract changes", ["Kind", "Path", "Status", "Detail"],
           [[c.get("kind", "-"), _cell(c.get("path", "")), c["status"],
             _cell(c.get("detail", ""))] for c in findings.get("contracts", [])],
           empty="- No API, schema, type or proto contract touched.")

    try:
        siblings = json.loads((session_dir / "siblings.json").read_text())
    except (OSError, json.JSONDecodeError):
        siblings = None
    have_siblings = isinstance(siblings, dict)

    # siblings.json is a file on disk that can be missing, corrupt, or hand-edited —
    # its absence means there's no "list below" to point at, so the empty text differs.
    _table(lines, "Cross-PR collisions",
           ["PR", "Status", "Symbol", "Paths", "Evidence", "Detail", "Confidence"],
           [[f"#{c.get('pr', '?')}", c.get("status", "-"),
             _cell(c.get("symbol") or "-"),
             _cell(", ".join(c.get("paths") or []) or "-"),
             _cell(", ".join(c.get("evidence") or []) or "-"),
             _cell(c.get("detail", "")),
             _confidence(c.get("confidence"))]
            for c in findings.get("cross_pr", [])],
           empty=("- No collision found with the open pull requests listed below."
                  if have_siblings else "- No cross-PR collision was reported."))

    if have_siblings:
        # Absence of siblings.json (older session, or the scan disabled) means the
        # section doesn't appear at all — distinct from having scanned and found nothing.
        _table(lines, "Parallel open pull requests",
               ["PR", "Author", "Overlap", "Files", "Updated"],
               [[_cell(f"[#{s.get('pr', '?')}]({s.get('url', '')})"),
                 _cell(s.get("author", "")),
                 "same file" if s.get("overlap") == "file" else "same module",
                 _cell(", ".join(s.get("overlap_paths") or [])),
                 _cell(s.get("updated_at", ""))]
                for s in siblings.get("siblings") or []],
               empty=f"- {_cell(siblings.get('skipped') or 'none found')}")
        note = f"- Scanned {siblings.get('scanned', 0)} open pull request(s)."
        if siblings.get("truncated"):
            note += " The scan was capped, so this list may be incomplete."
        lines += ["", note]

    test_rows = []
    for t in findings.get("tests", []):
        gaps = "<br>".join(
            f"{_cell(e.get('case', ''), 120)} → {_cell(e.get('where', ''), 60)}"
            for e in t.get("uncovered_edge_cases", [])) or "-"
        test_rows.append([_cell(t.get("target", "")), t.get("assertion_quality", "-"),
                          gaps, _cell(t.get("note", ""))])
    _table(lines, "Test integrity",
           ["Target", "Assertions", "Uncovered edge cases", "Notes"], test_rows)

    _table(lines, "Review threads", ["Comment", "Status", "Notes"],
           [[_cell(t["text"], max_len=120), t["status"], _cell(t.get("note", ""))]
            for t in findings.get("threads", [])])

    pruned = snapshot.get("pruned", [])
    if pruned:
        _table(lines, "Excluded from review context", ["File", "Reason", "Dropped"],
               [[_cell(p["filename"]), _cell(p["reason"]), "yes" if p["dropped"] else "patch only"]
                for p in pruned])

    neutralized = untrusted.load_neutralized(session_dir)
    if neutralized:
        _table(lines, "Neutralized in untrusted text", ["Phase", "What was stripped"],
               [[entry["phase"], _cell(item)]
                for entry in neutralized for item in entry["items"]])

    try:
        pocs = json.loads((session_dir / "poc.json").read_text())
    except (OSError, json.JSONDecodeError):
        pocs = []
    section = poc.comment_section(pocs)
    if section:
        lines += ["", section]

    lines += ["", "## Confirmation log", ""]
    for a in answers:
        lines.append(f"- **{a['question']}** → {a['answer']}")
    if not answers:
        lines.append("- (none)")

    if cost_usd:
        lines += ["", f"_Review cost: ${cost_usd:.4f}_"]

    report = "\n".join(lines) + "\n"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "report.md").write_text(report)
    return report


def build_comment(snapshot: dict, claims: list[dict], findings: dict,
                  answers: list[dict], report_content: str | None = None,
                  scores: dict | None = None, extra: str = "") -> str:
    """One English comment carrying the whole review (marker keeps it unique)."""
    verdict = _overall_verdict(findings)
    header = f"## PR Sentinel — Verdict: {verdict}"
    if scores:
        header += (f"\n\n**Gate: {GATE_LABELS.get(scores['gate'], scores['gate'])}** · "
                   f"Verification score {scores['verification_score']:.0%} · "
                   f"Business risk {scores['business_risk']}")
        if scores.get("reasons"):
            header += "\n\n" + "\n".join(f"- {_bullet(r, 200)}" for r in scores["reasons"])
    body = extra + "\n\n" if extra else ""
    if report_content:
        return (f"{header}\n\n{body}<details open>\n\n<summary>Full report</summary>\n\n"
                f"{report_content}\n\n</details>\n\n{MARKER}")

    claim_lines = "\n".join(f"- {c['id']}: {c['status']}" for c in findings.get("claims", []))
    doc_lines = "\n".join(f"- {d['path']}: {d['status']}" for d in findings.get("docs", []))
    thread_lines = "\n".join(f"- {_bullet(t['text'])} → {t['status']}"
                             for t in findings.get("threads", []))
    return (f"{header}\n\n{body}### Claims\n{claim_lines or '- none'}\n\n"
            f"### Docs vs reality\n{doc_lines or '- none'}\n\n"
            f"### Unresolved threads\n{thread_lines or '- none'}\n\n"
            f"Full report: local `sessions/{snapshot['owner']}/{snapshot['repo']}/"
            f"pr-{snapshot['pr']}/report.md`\n\n{MARKER}")


def find_comment(owner: str, repo: str, n: int, *, gh=run_gh) -> dict | None:
    """The bot's own comment on a PR, if it already posted one."""
    for c in gh(["api", f"repos/{owner}/{repo}/issues/{n}/comments", "--paginate"]):
        if MARKER in c.get("body", ""):
            return c
    return None


def post_comment(owner: str, repo: str, n: int, body: str, *,
                 gh=run_gh, list_comments=None) -> bool:
    """Create the comment, or UPDATE the existing one so a PR never accumulates them.

    Returns True when a new comment was created, False when one was updated.
    """
    if list_comments is None:
        list_comments = lambda: gh(["api", f"repos/{owner}/{repo}/issues/{n}/comments", "--paginate"])
    for c in list_comments():
        if MARKER in c.get("body", ""):
            gh(["api", f"repos/{owner}/{repo}/issues/comments/{c['id']}",
                "-X", "PATCH", "-f", f"body={body}"])
            return False
    gh(["api", f"repos/{owner}/{repo}/issues/{n}/comments", "-f", f"body={body}"])
    return True
