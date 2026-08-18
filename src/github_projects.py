"""Every repository the active GitHub account can reach, and its open PRs.

One GraphQL call answers "what could I review?" — REST would need a repo list
plus one `pulls` request per repo, and an account in a few organisations turns
that into dozens of round trips before the page can render.

This module only talks to GitHub. Merging the result with what is already in
`sessions/` belongs to `web.metrics`, which owns that reading.
"""
MAX_REPOS = 100
MAX_PRS = 20

# affiliations covers the three ways an account reaches a repo: it owns it, it
# was added to it, or it is in the owning org. ORGANIZATION_MEMBER is the one
# that matters most in practice — work PRs usually live there.
QUERY = """
query($limit: Int!, $prs: Int!) {
  viewer {
    login
    repositories(first: $limit,
                 affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        nameWithOwner
        isPrivate
        isArchived
        pushedAt
        pullRequests(states: OPEN, first: $prs,
                     orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            number
            title
            isDraft
            updatedAt
            author { login }
          }
        }
      }
    }
  }
}
"""


def _viewer(payload) -> dict:
    """The viewer block, or a RuntimeError carrying what GitHub complained about.

    A token without `read:org` still gets a 200 with an `errors` array, so the
    shape has to be checked rather than the status code.
    """
    if not isinstance(payload, dict) or "errors" in payload or "data" not in payload:
        raise RuntimeError(f"graphql failed: {payload}")
    viewer = (payload["data"] or {}).get("viewer")
    if not isinstance(viewer, dict):
        raise RuntimeError(f"graphql failed: {payload}")
    return viewer


def _repo(node: dict) -> dict | None:
    name = node.get("nameWithOwner") or ""
    if "/" not in name:
        return None
    owner, repo = name.split("/", 1)
    prs = node.get("pullRequests") or {}
    total = int(prs.get("totalCount") or 0)
    rows = []
    for pr in prs.get("nodes") or []:
        if not isinstance(pr, dict) or pr.get("number") is None:
            continue
        rows.append({"pr": int(pr["number"]),
                     "title": pr.get("title") or "",
                     "draft": bool(pr.get("isDraft")),
                     "updated_at": pr.get("updatedAt") or "",
                     "author": (pr.get("author") or {}).get("login") or ""})
    return {"owner": owner, "repo": repo,
            "private": bool(node.get("isPrivate")),
            "pushed_at": node.get("pushedAt") or "",
            "open_pr_count": total,
            # The query caps how many PRs come back per repo. Say so rather than
            # letting a repo with 40 open PRs quietly look like it has 20.
            "truncated": total > len(rows),
            "prs": rows}


def account_repos(*, gh=None, limit: int = MAX_REPOS,
                  prs: int = MAX_PRS) -> dict:
    """`{login, repos: [...]}` for whichever account gh is authenticated as.

    Archived repos are dropped — they cannot receive a pull request. The rest
    are ordered by how much there is to do: most open PRs first, then most
    recently pushed.
    """
    if gh is None:
        from gh import run_gh
        gh = run_gh
    viewer = _viewer(gh(["api", "graphql", "-f", f"query={QUERY}",
                         "-F", f"limit={limit}", "-F", f"prs={prs}"]))
    nodes = (viewer.get("repositories") or {}).get("nodes") or []
    repos = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("isArchived"):
            continue
        record = _repo(node)
        if record is not None:
            repos.append(record)
    # Two stable sorts, least significant first — a single compound key would
    # have to reverse an ISO string and a count together, which needs tricks.
    repos.sort(key=lambda r: r["pushed_at"], reverse=True)
    repos.sort(key=lambda r: r["open_pr_count"], reverse=True)
    return {"login": viewer.get("login") or "", "repos": repos,
            "truncated": len(nodes) >= limit}
