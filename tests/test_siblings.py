import json

from siblings import (MAX_OPEN_PRS, MAX_SIBLING_FILES, fetch_siblings,
                      our_paths, overlap_of, rank)

SENSITIVE = ["**/payment*/**", "**/migrations/**"]


def _snap(files, pruned=()):
    return {"files": [{"filename": f} for f in files],
            "pruned": list(pruned)}


def test_our_paths_takes_reviewed_files():
    assert our_paths(_snap(["src/a.py", "src/b.py"])) == {"src/a.py", "src/b.py"}


def test_our_paths_keeps_a_file_whose_patch_was_only_truncated():
    snap = _snap(["src/a.py"], [{"filename": "src/big.py",
                                 "reason": "patch truncated", "dropped": False}])
    assert our_paths(snap) == {"src/a.py", "src/big.py"}


def test_our_paths_drops_generated_files():
    snap = _snap(["src/a.py", "yarn.lock", "dist/bundle.js"])
    assert our_paths(snap) == {"src/a.py"}


def test_a_shared_file_is_a_file_overlap():
    kind, paths = overlap_of({"src/a.py", "src/b.py"}, {"src/b.py"}, SENSITIVE)
    assert (kind, paths) == ("file", ["src/b.py"])


def test_a_shared_sensitive_directory_is_a_module_overlap():
    kind, paths = overlap_of({"src/payment/charge.py"}, {"src/payment/refund.py"},
                             SENSITIVE)
    assert (kind, paths) == ("module", ["src/payment"])


def test_a_shared_directory_holding_a_contract_is_a_module_overlap():
    kind, paths = overlap_of({"api/openapi.yml"}, {"api/handlers.py"}, SENSITIVE)
    assert (kind, paths) == ("module", ["api"])


def test_a_shared_ordinary_directory_is_not_an_overlap():
    # otherwise every PR in a repo whose source lives under src/ is a sibling
    assert overlap_of({"src/a.py"}, {"src/b.py"}, SENSITIVE) == ("", [])


def test_a_file_overlap_wins_over_a_module_overlap():
    kind, _ = overlap_of({"src/payment/charge.py"}, {"src/payment/charge.py"},
                         SENSITIVE)
    assert kind == "file"


def test_disjoint_trees_do_not_overlap():
    assert overlap_of({"web/a.ts"}, {"api/b.py"}, SENSITIVE) == ("", [])


def _cand(pr, overlap, paths, updated):
    return {"pr": pr, "overlap": overlap, "overlap_paths": paths,
            "updated_at": updated}


def test_rank_puts_file_overlaps_first():
    cands = [_cand(1, "module", ["src/payment"], "2026-08-17"),
             _cand(2, "file", ["src/a.py"], "2026-08-10")]
    assert [c["pr"] for c in rank(cands, 5)] == [2, 1]


def test_rank_prefers_more_overlapping_paths_then_recency():
    cands = [_cand(1, "file", ["a.py"], "2026-08-10"),
             _cand(2, "file", ["a.py", "b.py"], "2026-08-09"),
             _cand(3, "file", ["c.py"], "2026-08-17")]
    assert [c["pr"] for c in rank(cands, 5)] == [2, 3, 1]


def test_rank_applies_the_cap():
    cands = [_cand(i, "file", ["a.py"], "2026-08-0%d" % i) for i in range(1, 6)]
    assert len(rank(cands, 3)) == 3


SNAPSHOT = {"owner": "demo", "repo": "app", "pr": 7, "base": "main",
            "files": [{"filename": "src/payment/invoice.py"}], "pruned": []}
CFG = {"enabled": True, "max_siblings": 3, "include_drafts": False}
GATE = {"sensitive_areas": SENSITIVE}


def _node(number, paths, *, title="other work", login="dev_b", draft=False,
          base="main", updated="2026-08-16T09:00:00Z"):
    return {"number": number, "title": title, "isDraft": draft,
            "baseRefName": base, "headRefName": f"feat/{number}",
            "updatedAt": updated, "url": f"https://github.com/demo/app/pull/{number}",
            "author": {"login": login},
            "files": {"nodes": [{"path": p} for p in paths]}}


def _gh(nodes, files=None, *, calls=None, graphql_error=False, files_error=False):
    """A fake gh: one GraphQL call for the PR list, one REST call per diff."""
    def call(args, **kw):
        if calls is not None:
            calls.append(args)
        if "graphql" in args:
            if graphql_error:
                raise RuntimeError("gh api failed: 502")
            return {"data": {"repository": {"pullRequests": {"nodes": nodes}}}}
        if files_error:
            raise RuntimeError("gh api failed: 404")
        return files or []
    return call


DIFF = [{"filename": "src/payment/invoice.py", "status": "modified",
         "additions": 3, "deletions": 1,
         "patch": "@@ -1,3 +1,3 @@\n-def createInvoice(a):\n+def createInvoice(a, b):"}]


def test_fetch_writes_the_artifact(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"])], DIFF)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert result["scanned"] == 1
    assert result["skipped"] == ""
    sibling = result["siblings"][0]
    assert sibling["pr"] == 456
    assert sibling["author"] == "dev_b"
    assert sibling["overlap"] == "file"
    assert "createInvoice" in sibling["files"][0]["patch"]
    assert json.loads((tmp_path / "siblings.json").read_text()) == result


def test_only_the_overlapping_files_of_the_sibling_are_kept(tmp_path):
    diff = DIFF + [{"filename": "docs/unrelated.md", "status": "modified",
                    "additions": 1, "deletions": 0, "patch": "@@ -1 +1 @@\n+x"}]
    gh = _gh([_node(456, ["src/payment/invoice.py", "docs/unrelated.md"])], diff)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert [f["filename"] for f in result["siblings"][0]["files"]] == \
        ["src/payment/invoice.py"]


def test_the_pr_under_review_is_not_its_own_sibling(tmp_path):
    gh = _gh([_node(7, ["src/payment/invoice.py"])], DIFF)
    assert fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_drafts_are_excluded_by_default(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"], draft=True)], DIFF)
    assert fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_drafts_are_included_when_configured(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"], draft=True)], DIFF)
    cfg = {**CFG, "include_drafts": True}
    assert len(fetch_siblings(SNAPSHOT, tmp_path, cfg, GATE, gh=gh)["siblings"]) == 1


def test_a_pr_targeting_another_base_is_excluded(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"], base="release/2.0")], DIFF)
    assert fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_bot_pull_requests_are_excluded(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"], login="dependabot[bot]")], DIFF)
    assert fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_a_shared_lockfile_is_not_an_overlap(tmp_path):
    snap = {**SNAPSHOT, "files": [{"filename": "yarn.lock"}]}
    gh = _gh([_node(456, ["yarn.lock"])], DIFF)
    assert fetch_siblings(snap, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_a_sibling_that_only_touches_a_generated_file_is_not_an_overlap(tmp_path):
    # `_candidates` must filter the SIBLING's paths through prune.classify too,
    # not just ours — otherwise a shared directory containing only a generated
    # file on their side wrongly reports a `module` overlap on src/payment.
    gh = _gh([_node(456, ["src/payment/invoice.min.js"])], DIFF)
    assert fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)["siblings"] == []


def test_no_overlap_records_why_and_fetches_no_diff(tmp_path):
    calls = []
    gh = _gh([_node(456, ["web/ui.ts"])], DIFF, calls=calls)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert result["siblings"] == []
    assert "no other open pull request" in result["skipped"]
    assert len(calls) == 1                      # the GraphQL query, nothing else


def test_the_cap_limits_how_many_diffs_are_fetched(tmp_path):
    calls = []
    nodes = [_node(n, ["src/payment/invoice.py"]) for n in range(100, 110)]
    gh = _gh(nodes, DIFF, calls=calls)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert len(result["siblings"]) == 3
    assert len(calls) == 4                      # 1 GraphQL + 3 diffs


def test_a_graphql_failure_is_recorded_not_raised(tmp_path):
    gh = _gh([], graphql_error=True)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert result["siblings"] == []
    assert "could not list open pull requests" in result["skipped"]
    assert json.loads((tmp_path / "siblings.json").read_text()) == result


def test_graphql_errors_in_the_payload_are_recorded(tmp_path):
    def gh(args, **kw):
        return {"errors": [{"message": "Bad credentials"}]}

    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert "could not list open pull requests" in result["skipped"]


def test_a_sibling_whose_diff_cannot_be_read_is_dropped(tmp_path):
    gh = _gh([_node(456, ["src/payment/invoice.py"])], files_error=True)
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    assert result["siblings"] == []
    assert result["scanned"] == 1
    # Overlapping PRs WERE found; only their diffs were unreadable — the
    # opposite claim ("no other open pull request...") would mislead the
    # reader into thinking nothing overlaps at all.
    assert "found 1 overlapping open pull request" in result["skipped"]
    assert "could not read" in result["skipped"]
    assert "no other open pull request" not in result["skipped"]


def test_a_full_page_of_open_prs_marks_the_scan_truncated(tmp_path):
    nodes = [_node(100 + i, ["web/ui.ts"]) for i in range(MAX_OPEN_PRS)]
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=_gh(nodes, DIFF))
    assert result["truncated"] is True


def test_a_sibling_with_a_full_page_of_files_marks_the_scan_truncated(tmp_path):
    # A single node whose files list hit the per-PR cap means that PR's own
    # file list is incomplete, even though far fewer than MAX_OPEN_PRS PRs
    # were returned overall.
    paths = [f"src/f{i}.py" for i in range(MAX_SIBLING_FILES)]
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE,
                            gh=_gh([_node(456, paths)], DIFF))
    assert result["truncated"] is True


def test_a_sibling_patch_is_trimmed(tmp_path):
    big = {"filename": "src/payment/invoice.py", "status": "modified",
           "additions": 900, "deletions": 0,
           "patch": "@@ -1 +1 @@\n" + "\n".join(f"+line {i}" for i in range(900))}
    gh = _gh([_node(456, ["src/payment/invoice.py"])], [big])
    result = fetch_siblings(SNAPSHOT, tmp_path, CFG, GATE, gh=gh)
    patch = result["siblings"][0]["files"][0]["patch"]
    assert len(patch.splitlines()) < 900
    assert "patch truncated" in patch
    assert result["siblings"][0]["pruned"]
