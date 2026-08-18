import pytest

import github_projects as gp


def _payload(*repos):
    return {"data": {"viewer": {"login": "nv-minh",
                                "repositories": {"nodes": list(repos)}}}}


def _repo(name, *, prs=(), total=None, archived=False, private=False,
          pushed="2026-08-18T10:00:00Z"):
    nodes = [{"number": n, "title": f"T{n}", "isDraft": False,
              "updatedAt": pushed, "author": {"login": "dev1"}} for n in prs]
    return {"nameWithOwner": name, "isPrivate": private, "isArchived": archived,
            "pushedAt": pushed,
            "pullRequests": {"totalCount": total if total is not None else len(nodes),
                             "nodes": nodes}}


def test_account_repos_parses_repos_and_their_open_prs():
    data = gp.account_repos(gh=lambda args, **kw: _payload(_repo("o/r", prs=[7, 8])))

    assert data["login"] == "nv-minh"
    assert len(data["repos"]) == 1
    record = data["repos"][0]
    assert (record["owner"], record["repo"]) == ("o", "r")
    assert record["open_pr_count"] == 2
    assert [p["pr"] for p in record["prs"]] == [7, 8]
    assert record["prs"][0]["title"] == "T7"
    assert record["prs"][0]["author"] == "dev1"
    assert record["truncated"] is False


def test_the_query_asks_for_every_affiliation_the_account_has():
    seen = {}

    def fake(args, **kw):
        seen["args"] = args
        return _payload()

    gp.account_repos(gh=fake)
    query = " ".join(seen["args"])
    assert "OWNER" in query and "COLLABORATOR" in query
    assert "ORGANIZATION_MEMBER" in query


def test_archived_repos_are_dropped():
    data = gp.account_repos(gh=lambda args, **kw: _payload(
        _repo("o/live", prs=[1]), _repo("o/dead", prs=[2], archived=True)))
    assert [r["repo"] for r in data["repos"]] == ["live"]


def test_a_repo_with_more_prs_than_the_page_says_so():
    data = gp.account_repos(gh=lambda args, **kw: _payload(
        _repo("o/r", prs=[1, 2], total=41)))
    record = data["repos"][0]
    assert record["open_pr_count"] == 41
    assert len(record["prs"]) == 2
    assert record["truncated"] is True


def test_repos_with_open_prs_come_first_then_most_recently_pushed():
    data = gp.account_repos(gh=lambda args, **kw: _payload(
        _repo("o/idle-new", pushed="2026-08-18T00:00:00Z"),
        _repo("o/busy", prs=[1, 2], pushed="2026-01-01T00:00:00Z"),
        _repo("o/idle-old", pushed="2026-02-01T00:00:00Z"),
        _repo("o/some", prs=[3], pushed="2026-03-01T00:00:00Z"),
    ))
    assert [r["repo"] for r in data["repos"]] == [
        "busy", "some", "idle-new", "idle-old"]


def test_graphql_errors_are_raised_not_returned_as_an_empty_list():
    payload = {"errors": [{"message": "Resource not accessible by personal "
                                      "access token"}]}
    with pytest.raises(RuntimeError, match="not accessible"):
        gp.account_repos(gh=lambda args, **kw: payload)


def test_a_non_dict_reply_is_an_error():
    with pytest.raises(RuntimeError, match="graphql failed"):
        gp.account_repos(gh=lambda args, **kw: "not json")
