from prune import classify, prune_files


def _file(name, patch=""):
    return {"filename": name, "status": "modified", "additions": 1,
            "deletions": 0, "patch": patch}


def test_classify_lockfiles_and_generated():
    assert classify("yarn.lock") == "lockfile"
    assert classify("frontend/package-lock.json") == "lockfile"
    assert classify("go.sum") == "lockfile"
    assert classify("web/dist/app.js") == "build output"
    assert classify("src/api/__generated__/types.ts") == "generated code"
    assert classify("public/logo.svg") == "binary asset"
    assert classify("vendor/lib/thing.go") == "vendored dependency"
    assert classify("__snapshots__/App.test.tsx.snap") == "test snapshot"


def test_classify_keeps_real_code_and_migrations():
    # migrations carry contract risk — they must never be pruned
    assert classify("db/migrations/0007_add_column.sql") is None
    assert classify("src/payment/service.py") is None
    assert classify("docs/api.md") is None


def test_prune_drops_generated_files_and_records_them():
    kept, pruned = prune_files([_file("src/app.py", "@@\n+x"), _file("yarn.lock", "@@\n+y")])
    assert [f["filename"] for f in kept] == ["src/app.py"]
    assert pruned == [{"filename": "yarn.lock", "reason": "lockfile", "dropped": True}]


def test_prune_truncates_oversized_patch_but_keeps_file():
    big = "\n".join(f"+line{i}" for i in range(50))
    kept, pruned = prune_files([_file("src/app.py", big)], max_patch_lines=10)
    assert len(kept) == 1
    assert kept[0]["patch"].count("\n") == 10  # 10 kept lines + the notice line
    assert "40 more lines" in kept[0]["patch"]
    assert pruned[0]["dropped"] is False
    assert "truncated to 10 of 50" in pruned[0]["reason"]


def test_prune_respects_total_budget():
    files = [_file(f"src/f{i}.py", "\n".join(f"+l{j}" for j in range(10)))
             for i in range(5)]
    kept, pruned = prune_files(files, max_patch_lines=10, max_total_lines=20)
    assert len(kept) == 5                       # every file still reviewed
    assert kept[-1]["patch"] == ""              # but the tail carries no diff
    exhausted = [p for p in pruned if p["reason"] == "diff budget exhausted"]
    assert len(exhausted) == 3


def test_prune_leaves_small_patches_untouched():
    kept, pruned = prune_files([_file("src/app.py", "@@\n+one\n+two")])
    assert kept[0]["patch"] == "@@\n+one\n+two"
    assert pruned == []


from prune import is_format_only

REINDENT = "@@ -1,2 +1,2 @@\n-def f():\n-  return 1\n+def f():\n+    return 1\n"
REAL = "@@ -1,1 +1,1 @@\n-    return 1\n+    return 2\n"
REWRAP = "@@ -1,2 +1,1 @@\n-foo(a,\n-    b)\n+foo(a, b)\n"
SWAP = "@@ -1,2 +1,2 @@\n-a()\n-b()\n+b()\n+a()\n"
ADDITION = "@@ -0,0 +1,1 @@\n+new_line()\n"
CONTEXT_ONLY = "@@ -1,1 +1,1 @@\n unchanged\n"


def test_a_reindent_is_format_only():
    assert is_format_only(REINDENT) is True


def test_a_rewrap_is_format_only():
    assert is_format_only(REWRAP) is True


def test_a_real_change_is_not_format_only():
    assert is_format_only(REAL) is False


def test_swapping_two_lines_is_not_format_only():
    assert is_format_only(SWAP) is False


def test_a_pure_addition_is_not_format_only():
    assert is_format_only(ADDITION) is False


def test_a_context_only_hunk_is_not_format_only():
    assert is_format_only(CONTEXT_ONLY) is False


def test_file_headers_are_not_mistaken_for_content():
    patch = "--- a/x.py\n+++ b/x.py\n" + REAL
    assert is_format_only(patch) is False


def test_an_empty_patch_is_not_format_only():
    assert is_format_only("") is False


def test_prune_empties_a_format_only_patch_without_dropping_the_file():
    kept, pruned = prune_files([{"filename": "a.py", "patch": REINDENT}])
    assert [f["filename"] for f in kept] == ["a.py"]
    assert kept[0]["patch"] == ""
    assert pruned == [{"filename": "a.py", "reason": "format-only change",
                       "dropped": False}]


def test_prune_leaves_a_real_patch_alone():
    kept, pruned = prune_files([{"filename": "a.py", "patch": REAL}])
    assert kept[0]["patch"] == REAL
    assert pruned == []
