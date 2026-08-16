"""CLI entry: orchestrates the review pipeline.

    python -m src.run <owner>/<repo> <pr> [--skip-human] [--force] [--no-post]
                      [--ci] [--fixtures DIR] [--dry-run]

Every phase writes its result into the session directory, and every phase is
skipped when that result already exists — so a re-run resumes instead of paying
for the same work twice. `--force` re-runs them.
"""
import argparse
import json
import sys
from pathlib import Path

import providers
from agent import total_cost
from config import load_config
from gh import add_labels, create_check_run, gh_available
from human_gate import run_gate
from notify import build_payload, notify
from score import score as compute_score
from synthesize import (build_comment, build_report, post_comment,
                        _overall_verdict)

CONFIG_PATH = Path("prsentinel.yml")
CHECK_NAME = "PR Sentinel"
CHECK_CONCLUSION = {"pass": "success", "warn": "neutral", "fail": "failure"}


def load_review_config(path: Path = CONFIG_PATH) -> dict:
    """prsentinel.yml if present, otherwise the built-in defaults."""
    from autoreview_config import DEFAULTS, load_config as load_yaml
    if not path.exists():
        return dict(DEFAULTS)
    try:
        return load_yaml(path)
    except (ValueError, OSError) as e:
        print(f"[run] ignoring invalid {path}: {e}", file=sys.stderr)
        return dict(DEFAULTS)


def agent_config(env, review_cfg: dict) -> dict:
    """The knobs the agent phases care about, from env + prsentinel.yml."""
    provider = providers.resolve(review_cfg)
    return {
        "provider": provider,
        "model": provider.model,
        "claims_model": provider.claims_model,
        "allow_bash": review_cfg.get("allow_bash", False),
        "max_turns": review_cfg.get("max_turns", 60),
        "max_budget_usd": review_cfg.get("max_budget_usd"),
    }


def _load_or_skip(name: str, session_dir: Path, force: bool) -> dict | list | None:
    path = session_dir / name
    if path.exists() and not force:
        return json.loads(path.read_text())
    return None


def _write_failed_report(session_dir: Path, error: Exception) -> None:
    lines = [
        "# Review FAILED",
        "",
        f"- Error: {error}",
        "- Failed phase: see stderr",
        f"- Existing artifacts: {[p.name for p in sorted(session_dir.iterdir()) if p.is_file()]}",
        "",
    ]
    (session_dir / "report.md").write_text("\n".join(lines))


def _bump_rounds(session_dir: Path) -> None:
    """Increment the review-round counter (once per verify pass)."""
    path = session_dir / "rounds.txt"
    try:
        current = int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        current = 0
    path.write_text(str(current + 1))


def _remediate(review_cfg: dict, cfg: dict, owner: str, repo: str, num: int,
               workspace: Path, session_dir: Path, snapshot: dict, findings: dict,
               post: bool) -> str:
    """Draft doc fixes and deliver them. Returns markdown for the summary comment."""
    import remediate

    if not remediate.fixable_docs(findings):
        return ""
    if not (review_cfg.get("inline_suggestions", True) or review_cfg.get("docs_fix_pr")):
        return ""
    try:
        patches = _load_or_skip("patches.json", session_dir, False)
        if patches is None:
            patches = remediate.draft_patches(findings, cfg, workspace, session_dir)
    except RuntimeError as e:
        print(f"[run] doc patch drafting failed: {e}", file=sys.stderr)
        return ""
    if not patches:
        return ""

    leftover = patches
    if post and review_cfg.get("inline_suggestions", True):
        _, leftover = remediate.post_suggestions(owner, repo, num, patches, snapshot)
    if post and leftover and review_cfg.get("docs_fix_pr"):
        try:
            url = remediate.create_docs_fix_pr(owner, repo, num, leftover, snapshot, workspace)
            if url:
                return f"Documentation fixes opened as a follow-up PR: {url}"
        except RuntimeError as e:
            print(f"[run] docs-fix PR failed: {e}", file=sys.stderr)
    return remediate.comment_section(leftover)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pr-sentinel")
    parser.add_argument("pr", help="<owner>/<repo> <pr-number> or owner/repo#n")
    parser.add_argument("number", nargs="?", type=int,
                        help="PR number (omit if pr = owner/repo#n)")
    parser.add_argument("--skip-human", action="store_true",
                        help="don't ask, mark questions as SKIPPED")
    parser.add_argument("--force", action="store_true",
                        help="re-run phases that already have results")
    parser.add_argument("--no-post", action="store_true",
                        help="don't post anything to the PR")
    parser.add_argument("--dry-run", action="store_true",
                        help="only build the report, don't post")
    parser.add_argument("--reply", action="store_true",
                        help="answer new replies on the PR by resuming the previous "
                             "review session instead of re-reviewing from scratch")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: post, label, publish a check run, and exit "
                             "non-zero when the gate fails")
    parser.add_argument("--fixtures", type=Path, default=None,
                        help="directory with snapshot.json/claims.json/findings.json "
                             "(for e2e, skips GitHub and the model)")
    args = parser.parse_args(argv)

    base = args.pr.split("#")[0]
    parts = base.split("/")
    if len(parts) != 2 or (args.number is None and "#" not in args.pr):
        print("usage: python -m src.run <owner>/<repo> <pr-number>", file=sys.stderr)
        return 2
    owner, repo = parts
    num = str(args.number if args.number is not None else args.pr.split("#")[1])
    if not num.isdigit():
        print(f"invalid PR number: {num}", file=sys.stderr)
        return 2

    env = load_config()
    review_cfg = load_review_config()
    try:
        cfg = agent_config(env, review_cfg)
    except ValueError as e:
        # A YAML typo is caught by providers.validate() at load time; an env
        # override (PRS_PROVIDER) bypasses that and must not surface as a
        # raw traceback.
        print(f"Error: {e}", file=sys.stderr)
        return 2
    skip_human = args.skip_human or args.ci
    post = not (args.no_post or args.dry_run or args.fixtures is not None)

    if args.fixtures is None:
        provider = cfg["provider"]
        if not providers.has_auth(provider):
            print(providers.auth_hint(provider), file=sys.stderr)
            return 3
        if review_cfg.get("max_budget_usd") and not provider.reports_cost:
            print(f"[run] max_budget_usd is ignored: provider "
                  f"{provider.name!r} does not report cost", file=sys.stderr)
        if not gh_available():
            print("gh CLI not installed or not authenticated (gh auth login)",
                  file=sys.stderr)
            return 2

    session_dir = env.session_root / owner / repo / f"pr-{num}"
    session_dir.mkdir(parents=True, exist_ok=True)
    extra_comment = ""

    try:
        if args.fixtures is not None:
            for name in ("snapshot.json", "claims.json", "findings.json"):
                src = args.fixtures / name
                if not src.exists():
                    print(f"missing fixture: {src}", file=sys.stderr)
                    return 2
                (session_dir / name).write_text(src.read_text())
            findings = json.loads((session_dir / "findings.json").read_text())
        else:
            from claims import extract_claims
            from describe import comment_section, draft_description, needs_description
            from snapshot import build_snapshot
            from tickets import fetch_tickets
            from tiers import classify, settings as tier_settings
            from verify import run_verify, setup_workspace

            snapshot = _load_or_skip("snapshot.json", session_dir, args.force)
            if snapshot is None:
                snapshot = build_snapshot(owner, repo, int(num), session_dir)

            if review_cfg.get("tiered_budget", True):
                tier = classify(snapshot, review_cfg.get("gate"))
                knobs = tier_settings(tier)
                cfg["effort"] = knobs["effort"]
                cfg["max_turns"] = knobs["max_turns"]
                cfg["allow_bash"] = knobs["allow_bash"]
                if knobs["use_claims_model"]:
                    cfg["model"] = cfg["claims_model"]
                print(f"[run] tier {tier}: effort {knobs['effort']}, "
                      f"max_turns {knobs['max_turns']}, "
                      f"bash {'on' if knobs['allow_bash'] else 'off'}")

            ticket = _load_or_skip("ticket.json", session_dir, args.force)
            if ticket is None:
                ticket = fetch_tickets(snapshot, session_dir,
                                       review_cfg.get("jira") or {})

            if needs_description(snapshot):
                draft = _load_or_skip("description.json", session_dir, args.force)
                if draft is None:
                    draft = draft_description(snapshot, cfg, session_dir)
                if post and review_cfg.get("auto_describe"):
                    from gh import edit_pr_body
                    edit_pr_body(owner, repo, int(num), draft["description"])
                    snapshot["body"] = draft["description"]
                    (session_dir / "snapshot.json").write_text(json.dumps(snapshot, indent=2))
                else:
                    extra_comment = comment_section(draft)

            claims = _load_or_skip("claims.json", session_dir, args.force)
            if claims is None:
                claims = extract_claims(snapshot, cfg, session_dir)

            findings = _load_or_skip("findings.json", session_dir, args.force)
            workspace = session_dir / "workspace"
            if findings is None:
                setup_workspace(owner, repo, int(num), workspace)
                findings = run_verify(cfg, workspace, session_dir, snapshot, claims,
                                      ticket=ticket)
                _bump_rounds(session_dir)
            elif args.reply:
                import threads

                fresh = threads.unseen(session_dir,
                                       threads.fetch_replies(owner, repo, int(num)))
                if not fresh:
                    print("No new replies — nothing to do.")
                    return 0
                print(f"Answering {len(fresh)} new repl(y|ies) on #{num}.")
                old_shas = {c["sha"] for c in snapshot.get("commits", [])}
                snapshot = build_snapshot(owner, repo, int(num), session_dir)
                new_commits = [c for c in snapshot["commits"] if c["sha"] not in old_shas]
                setup_workspace(owner, repo, int(num), workspace)
                try:
                    findings = threads.run_followup(cfg, workspace, session_dir,
                                                    snapshot, fresh, new_commits)
                except RuntimeError as e:
                    print(f"[run] follow-up could not resume ({e}) — full re-review",
                          file=sys.stderr)
                    findings = run_verify(cfg, workspace, session_dir, snapshot, claims,
                                          ticket=ticket)
                # Only what this run answered: a reply that landed while the
                # follow-up was running stays unseen, so the next run takes it.
                threads.save_replies(session_dir, fresh)
                (session_dir / "answers.json").unlink(missing_ok=True)
                _bump_rounds(session_dir)

        scores = compute_score(findings, review_cfg.get("gate"))
        (session_dir / "score.json").write_text(json.dumps(scores, indent=2))

        answers = _load_or_skip("answers.json", session_dir, args.force)
        if answers is None:
            answers = run_gate(findings, session_dir, interactive=not skip_human)

        snapshot = json.loads((session_dir / "snapshot.json").read_text())
        claims = json.loads((session_dir / "claims.json").read_text())

        if args.fixtures is None:
            section = _remediate(review_cfg, cfg, owner, repo, int(num),
                                 session_dir / "workspace", session_dir,
                                 snapshot, findings, post)
            extra_comment = "\n\n".join(x for x in (extra_comment, section) if x)

        report = build_report(snapshot, claims, findings, answers, session_dir,
                              scores=scores, cost_usd=total_cost(session_dir))
        print(f"Report: {session_dir / 'report.md'}")
        print(f"Gate: {scores['gate']} | verification score "
              f"{scores['verification_score']:.0%} | risk {scores['business_risk']}")

        if post:
            body = build_comment(snapshot, claims, findings, answers,
                                 report_content=report, scores=scores, extra=extra_comment)
            if post_comment(owner, repo, int(num), body):
                print("Posted comment to PR.")
            else:
                print("Comment exists — updated in place.")
            if args.ci:
                add_labels(owner, repo, int(num), scores["labels"])
                create_check_run(
                    owner, repo, snapshot.get("head_sha", ""), name=CHECK_NAME,
                    conclusion=CHECK_CONCLUSION.get(scores["gate"], "neutral"),
                    title=f"Gate {scores['gate']} — verification "
                          f"{scores['verification_score']:.0%}",
                    summary="\n".join(f"- {r}" for r in scores["reasons"]) or "No blocking findings.")

        if env.slack_webhook and args.fixtures is None:
            notify(env.slack_webhook,
                   build_payload(snapshot, findings, scores, _overall_verdict(findings)))

        jira_cfg = review_cfg.get("jira") or {}
        if post and jira_cfg.get("comment_result") and args.fixtures is None:
            import jira_client
            import jira_report
            key = (ticket or {}).get("primary", "")
            if key and jira_report.post_result(
                    jira_client.load_config(), key,
                    jira_report.build_body(snapshot, findings, scores)):
                print(f"Posted the verdict to {key}.")

        if args.ci and scores["gate"] == "fail":
            print("Gate failed — blocking merge.", file=sys.stderr)
            return 1
        return 0
    except (RuntimeError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        _write_failed_report(session_dir, e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
