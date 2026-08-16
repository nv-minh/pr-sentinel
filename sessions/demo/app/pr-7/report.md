# Review PR #7 — Add Google sign-in

- Author: dev1 | Base: main → Head: feat/google-signin
- Files changed: 3 | Commits: 2
## Verdict: PARTIAL

- Gate: **WARNING** | Verification score: 67% | Business risk: medium
  - verification score 67% below 80%
  - 1 core doc(s) out of sync: docs/auth.md
  - RISK: Sessions expire predictably — rotation shortens the effective refresh window from 30 to 7 days
  - caller needs update: Session.refresh()

## Claims

| Claim | Content | Status | Evidence | Notes |
|---|---|---|---|---|
| C1 | Adds Google OAuth sign-in | Matches | src/auth/google.py:22, src/auth/google.py:64 | sign_in() exchanges the code and creates a session |
| C2 | Refresh tokens are rotated on every use | Partial | src/auth/session.py:46 | rotation happens on refresh, but not on the initial sign-in path |
| C3 | Updates docs/auth.md | Matches | docs/auth.md:31 | the Google section was added |

## Docs vs reality

| Doc | Status | Difference |
|---|---|---|
| docs/auth.md | STALE | still documents the 30-day refresh window; the code now expires refresh tokens after 7 days |
| README.md | MATCH | auth section is accurate |

## Requirement impact

| Requirement | Impact | Area | Detail |
|---|---|---|---|
| Users can sign in | CHANGED | auth | a third sign-in provider is now available |
| Sessions expire predictably | RISK | auth | rotation shortens the effective refresh window from 30 to 7 days |

## Callers outside the diff

| Symbol | Defined at | Callers | Risk | Notes |
|---|---|---|---|---|
| Session.refresh() | src/auth/session.py:52 | src/api/middleware.py:88, src/jobs/nightly_sync.py:31 | NEEDS_UPDATE | both callers assume refresh() returns the same token; it now returns a rotated one |

## Contract changes

| Kind | Path | Status | Detail |
|---|---|---|---|
| API | openapi.yml | COMPATIBLE | POST /auth/google added; no existing field changed |

## Test integrity

| Target | Assertions | Uncovered edge cases | Notes |
|---|---|---|---|
| tests/test_google.py:test_sign_in | STRONG | - | asserts the session payload and the failure path |
| tests/test_session.py:test_rotate | WEAK | a refresh token reused after rotation must be rejected → tests/test_session.py:test_rotate<br>rotation during a concurrent refresh → tests/test_session.py:test_rotate | calls rotate_refresh_token() but only asserts it returns a string |

## Review threads

| Comment | Status | Notes |
|---|---|---|
| Does this handle a reused refresh token? | STILL_VALID | no code path rejects a token that was already rotated |

## Excluded from review context

| File | Reason | Dropped |
|---|---|---|
| yarn.lock | lockfile | yes |
| public/google-logo.svg | binary asset | yes |

## Confirmation log

- **Is the 7-day refresh window intended, or should docs/auth.md stay at 30?** → 7 days is intended — update the doc
- **Doc docs/auth.md: refresh window differs. Is the doc wrong?** → y

_Review cost: $0.2855_
