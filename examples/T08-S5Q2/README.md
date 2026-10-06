# T08-S5Q2 · Example — four contrasting cases: omission, value drift, clean baseline, check-then-act window

**Status**: `example` (v4) ｜ **Source**: FG-TIDA use-cases #21, Annex T08 (AWS Step Functions / RDS) · UC-21, requirement S5-Q2 ｜ **as of** 2026-09-30

> **One line.** A Step-Functions-style pre-flight gate is compared against a controlled implementation on **four contrasting cases** — an omitted condition, a declared condition whose value changes between queue and use, a clean baseline, and a world change *after* the verdict but *before* the action — each with an explicit prevention trace (attempted action → disposition → resulting target state) — and a **mutation suite** that breaks the controlled validator four ways and requires the selftest to kill every mutant.

© 2026 赵兴华 / Steven Zhao · China. Rights reserved; theoretical text not under Apache-2.0.

---

## What this demonstrates

UC-21's S5 scenario carries a **Must** requirement:

> **S5-Q2** *(Technical, Must)* — *Material preconditions are reassessed at use, not inherited from queue time.*

Semantics, aligned with S5: an **active freeze prohibits** the change; lifting it removes that restriction. The gate therefore consumes the **permitting condition `no_applicable_freeze`** — it must hold at use. A freeze may become applicable *after* the item is queued (cases A/B) or *after* the gate has already passed the item and before the action runs (case D). (v1 modeled the freeze as `freeze_still_holds`, an inverted framing; v2 adopted the permitting-condition naming suggested in the joint review.)

Two catalog entries describe why the registry-driven shape fails silently:

- [SF-006 · Undeclared = unchecked](../../failures/SF-006-undeclared-not-checked.md) — the check is exhaustive *with respect to the registry*; anything the registry forgot is never checked, and never missed.
- [SF-011 · The always-green oracle](../../failures/SF-011-always-green-oracle.md) — a check that cannot fail on the input it exists to catch is not a check; it is decoration.

## The four cases

Each case runs **two implementations on the identical world trace**: `before` evaluates the declared registry over the **queue-time snapshot** and inherits the verdict to the action; `after` first diffs declared coverage against the **spec-derived reference**, then evaluates the declared conditions against state **read at use time**, then **re-verifies at the action boundary** (atomic check-then-act), then emits the prevention trace.

| Case | Declared | World events | `before` (snapshot + inherited verdict) | `after` (use-time read + boundary re-check) | What it isolates |
|---|---|---|---|---|---|
| **A-omitted** | 3 items (freeze not declared) | freeze becomes applicable pre-gate | PASS, repair **executed during the breach** | FAIL — coverage gap named (SF-006) | detection of an *omission* relative to the reference |
| **B-temporal** | 4 items (freeze declared) | freeze becomes applicable pre-gate | PASS — stale snapshot; repair executed during the breach | FAIL — value changed between queue and use; repair **blocked**, target unchanged | *use-time reassessment* — the decisive temporal case for S5-Q2; set-difference alone finds nothing here |
| **C-clean** | 4 items | none | PASS, legitimate repair executed | PASS, legitimate repair executed | the legitimate-activity control: reassessment must not over-block |
| **D-actwindow** | 4 items | freeze becomes applicable **post-verdict, pre-action** | PASS at the gate, then **executes during the fresh breach** — a verdict alone is not a control | PASS at the gate, then **BLOCKED at the action boundary**; target unchanged | the *check-then-act gap*: use-time reassessment must be re-verified atomically at the action, not merely once before it |

## How to run

stdlib only, Python 3.9+, no network, deterministic:

```
python simulation.py                    # selftest: runs all four cases on both
                                        # implementations, asserts they discriminate
python simulation.py --case A-omitted   # paired traces for one case
python simulation.py --case B-temporal
python simulation.py --case C-clean
python simulation.py --case D-actwindow
python simulation.py --mutants      # mutation kill matrix only
```

`--case` exits 0 when the two implementations agree on the verdict, 1 when they discriminate (the interesting outcome).

## The auditable spec

The condition set is **not** hard-coded as an uncheckable assumption. [`fixture_spec.json`](fixture_spec.json) is the machine-readable source of the reference conditions and their semantics; at startup the simulation asserts that the in-code reference and the spec agree, and fails loudly on divergence:

- edit one side without the other → `SPEC/CODE DIVERGENCE` before any trace is printed;
- a case fixture whose world keys drift from the reference → `FIXTURE DIVERGENCE`.

This converts the v2 qualification ("the reference's completeness is stipulated") into an auditable artifact. What remains open — and is *not* claimed here — is how references are obtained or created at catalog scale.

## Who tests the tester (v4)

A selftest that asserts the shipped validators discriminate is itself a validator — and a validator that cannot fail on a broken input is decoration ([SF-011](../../failures/SF-011-always-green-oracle.md)). So the selftest now also runs a **mutation suite**: four programmatic mutants of the `after` implementation, each disabling exactly one defense, each required to be *killed* — its observable `(exit, target-state)` pair must deviate from a hardcoded shipped-behavior table (hardcoded, so the assertion is not derived from a run of the code it tests) on at least one case:

| Mutant | Defense disabled | Killed by |
|---|---|---|
| `M1-no-coverage-diff` | SF-006 coverage diff | **A-omitted** |
| `M2-stale-read` | use-time state read | **B-temporal** |
| `M3-no-boundary-recheck` | action-boundary re-check | **D-actwindow** |
| `M4-blanket-deny` | blocks even though every gate is satisfied | **C** (the clean baseline is the over-blocking detector) |

Each mutant corresponds to one row of the case table above — the mapping between defenses and cases is now *mechanically enforced*, not narrated. The selftest also asserts that FAIL diagnostics **name the offending condition** (`no_applicable_freeze`), not merely any failure. Gate 7 of [`.github/workflows/gates.yml`](../../.github/workflows/gates.yml) runs this selftest in CI on every push.

## What it proves, and what it does not

- **Proves (A):** SF-006 detects an omission relative to the reference.
- **Proves (B):** coverage completeness alone is *not* use-time reassessment — a declared condition whose value drifts passes a snapshot-reading check and is caught only by reading state at use.
- **Proves (C):** the controlled implementation preserves legitimate activity.
- **Proves (D):** a use-time verdict alone is not a control — the world can change between the verdict and the action. Closing the gap requires re-verification at the action boundary (atomic check-then-act). The before implementation demonstrates the residual risk: it passes the gate correctly and still executes during the fresh breach.
- **Stipulated, not proven:** reference completeness is auditable (spec file + divergence check) but its *derivation at scale* is the open architectural question. *Freshness* of the use-time read (Q3 territory: clock skew, logical ordering) is out of scope, stated in `fixture_spec.json`. This is a model result, not an AWS product execution.
- **Does not prove:** full S5 verification. This covers *one* requirement (S5-Q2); the remaining S5-Q0…Q5 and the other eight technology profiles are follow-on work, not claimed here.

## Files

| File | Purpose |
|---|---|
| [`simulation.py`](simulation.py) | the stateful simulation, its four cases, spec-agreement checks, the selftest, and the mutation suite |
| [`fixture_spec.json`](fixture_spec.json) | machine-readable source of the reference conditions; audited against the code at startup |
| `README.md` | this page |
