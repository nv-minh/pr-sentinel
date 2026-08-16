# Review PR #8 — Speed up checkout by caching prices

- Author: dev2 | Base: main → Head: perf/price-cache
- Files changed: 3 | Commits: 1
## Verdict: MISLEADING

- Gate: **BLOCKED** | Verification score: 33% | Business risk: high
  - verification score 33% below 80%
  - 1 core doc(s) out of sync: docs/checkout.md
  - SCHEMA_MIGRATION_RISK in db/migrations/0042_drop_price_history.sql: DROP TABLE price_history is destructive and has no down migration
  - BROKEN: Discount codes apply at checkout — a discount applied within the 5-minute TTL is not reflected in the price
  - caller broken: price_for(cart) used at src/api/checkout.py:120, src/admin/quotes.py:57

## Claims

| Claim | Content | Status | Evidence | Notes |
|---|---|---|---|---|
| C1 | Caches prices for 5 minutes | Matches | src/checkout/pricing.py:18 | CACHE_TTL = 300 |
| C2 | No behaviour change | Mismatch | src/checkout/pricing.py:74, db/migrations/0042_drop_price_history.sql:1 | discount codes are resolved before the cache, so a code applied within the TTL is ignored; the migration also drops price_history |
| C3 | Fully covered by tests | Mismatch | tests/test_pricing.py:12 | one test, and it asserts nothing about the cached path |

## Docs vs reality

| Doc | Status | Difference |
|---|---|---|
| docs/checkout.md | FABRICATED | describes a per-customer cache key that does not exist in the code |
| docs/pricing-history.md | WRONG | documents the price_history table this PR drops |

## Requirement impact

| Requirement | Impact | Area | Detail |
|---|---|---|---|
| Discount codes apply at checkout | BROKEN | payment | a discount applied within the 5-minute TTL is not reflected in the price |
| Price history is auditable | BROKEN | data | the audit table is dropped with no replacement |

## Callers outside the diff

| Symbol | Defined at | Callers | Risk | Notes |
|---|---|---|---|---|
| price_for(cart) | src/checkout/pricing.py:41 | src/api/checkout.py:120, src/admin/quotes.py:57 | BROKEN | admin quotes rely on an uncached price and will now serve stale values |

## Contract changes

| Kind | Path | Status | Detail |
|---|---|---|---|
| SCHEMA | db/migrations/0042_drop_price_history.sql | SCHEMA_MIGRATION_RISK | DROP TABLE price_history is destructive and has no down migration |

## Test integrity

| Target | Assertions | Uncovered edge cases | Notes |
|---|---|---|---|
| tests/test_pricing.py:test_price_for | MISSING | a discount applied inside the cache TTL → tests/test_pricing.py:test_price_for<br>cache expiry boundary at exactly 300s → tests/test_pricing.py:test_price_for | no test exercises the cached branch at all |

## Review threads

- (none)

## Excluded from review context

| File | Reason | Dropped |
|---|---|---|
| package-lock.json | lockfile | yes |

## Confirmation log

- **Should dropping price_history be a separate, reviewed migration?** → SKIPPED

_Review cost: $0.3410_
