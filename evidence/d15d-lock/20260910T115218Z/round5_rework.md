# Round 5 rework evidence

Run ID: `20260910T115218Z`

## Scope

Reviewer E accepted the Round 4 fail-closed C2 invalidation and required three
documentation/evidence corrections. No production code, builder, frozen tar,
or runtime evidence was changed.

## Findings and closures

| Finding | Closure |
|---|---|
| MEDIUM-1: C2 evidence incorrectly said all seven prefix hits would enter the package | `c2_main_drift_invalidation.md` and the manifest now distinguish 7 C2 policy hits, 3 actual `evaluation/` package-content hits, and 4 `tests/` hits excluded by the builder. TaskCard uses the same distinction. |
| MEDIUM-2: Execution Plan retained an executable old `306c15e` decision path | The old selection question is explicitly historical. The active flow selects a new release commit `R` from current main or later, verifies C1/C2, rebuilds, and reruns the full identity chain. Phase 0 no longer instructs checkout of `306c15e`. |
| MEDIUM-3: Runbook C2 omitted `config/` | C2's locked-prefix diff scope now includes `config/`. A provenance guard asserts this. |

## Maintained conclusion

`C2` remains `FAIL_INVALIDATED`; the explicit conclusion remains
`TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY`. The old frozen tar remains historical
only. A clean rebuild, new package identity, full consistency rerun, and
required Kylin VM evidence remain required before G-D7.

## Boundary

This run makes no new L2/L3 claim and does not modify the builder to exclude
`memory-service/evaluation/`.
