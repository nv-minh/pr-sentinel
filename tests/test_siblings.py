from siblings import our_paths, overlap_of, rank

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
