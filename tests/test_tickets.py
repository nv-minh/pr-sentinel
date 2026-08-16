from tickets import find_keys


def _snap(*, title="", body="", head=""):
    return {"title": title, "body": body, "head": head}


PROJECTS = ["ABC", "PRJ"]


def test_a_browse_link_in_the_body_is_found():
    snap = _snap(body="Context: https://acme.atlassian.net/browse/ABC-123 thanks")
    assert find_keys(snap, PROJECTS) == ["ABC-123"]


def test_a_browse_link_needs_no_allowlist():
    snap = _snap(body="https://acme.atlassian.net/browse/ZZZ-9")
    assert find_keys(snap, PROJECTS) == ["ZZZ-9"]


def test_a_title_prefix_is_found():
    assert find_keys(_snap(title="ABC-123: add retries"), PROJECTS) == ["ABC-123"]


def test_a_title_prefix_outside_the_allowlist_is_ignored():
    assert find_keys(_snap(title="XYZ-1: add retries"), PROJECTS) == []


def test_a_branch_name_key_is_found():
    assert find_keys(_snap(head="feature/ABC-123-add-retries"), PROJECTS) == ["ABC-123"]


def test_utf_8_in_a_title_prefix_is_not_a_ticket():
    assert find_keys(_snap(title="UTF-8: fix encoding"), PROJECTS) == []


def test_a_cve_in_a_title_prefix_is_not_a_ticket():
    assert find_keys(_snap(title="CVE-2024-1234: bump the parser"), PROJECTS) == []


def test_the_browse_link_wins_over_the_title_and_branch():
    snap = _snap(title="PRJ-2: work", body="see https://x.atlassian.net/browse/ABC-1",
                 head="feature/PRJ-3-work")
    assert find_keys(snap, PROJECTS)[0] == "ABC-1"


def test_every_source_contributes_after_the_primary():
    snap = _snap(title="PRJ-2: work", body="https://x.atlassian.net/browse/ABC-1",
                 head="feature/PRJ-3-work")
    assert find_keys(snap, PROJECTS) == ["ABC-1", "PRJ-2", "PRJ-3"]


def test_duplicate_keys_across_sources_appear_once():
    snap = _snap(title="ABC-1: work", body="https://x.atlassian.net/browse/ABC-1",
                 head="feature/ABC-1-work")
    assert find_keys(snap, PROJECTS) == ["ABC-1"]


def test_at_most_three_tickets_are_returned():
    body = " ".join(f"https://x.atlassian.net/browse/ABC-{i}" for i in range(1, 8))
    assert len(find_keys(_snap(body=body), PROJECTS)) == 3


def test_a_lowercase_browse_key_is_normalised():
    snap = _snap(body="https://x.atlassian.net/browse/abc-7")
    assert find_keys(snap, PROJECTS) == ["ABC-7"]


def test_the_allowlist_is_matched_case_insensitively():
    assert find_keys(_snap(title="abc-9: work"), PROJECTS) == ["ABC-9"]


def test_a_bare_key_in_the_body_is_not_a_source():
    assert find_keys(_snap(body="relates to ABC-5 somehow"), PROJECTS) == []


def test_no_sources_yields_nothing():
    assert find_keys(_snap(title="fix things", head="fix-things"), PROJECTS) == []


def test_an_empty_allowlist_still_honours_browse_links():
    snap = _snap(title="ABC-1: work", body="https://x.atlassian.net/browse/ABC-2")
    assert find_keys(snap, []) == ["ABC-2"]
