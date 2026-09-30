# T08-S5Q2 · Example — three contrasting cases: omission, value drift, clean baseline

**Status**: `example` (v2) ｜ **Source**: FG-TIDA use-cases #21, Annex T08 (AWS Step Functions / RDS) · UC-21, requirement S5-Q2 ｜ **as of** 2026-09-30

> **One line.** A Step-Functions-style pre-flight gate is compared against a controlled implementation on **three contrasting cases** — an omitted condition, a declared condition whose value changes between queue and use, and a clean baseline — each with an explicit prevention trace (attempted action → disposition → resulting target state).

© 2026 赵兴华 / Steven Zhao · China. Rights reserved; theoretical text not under Apache-2.0.

---

## What this demonstrates

UC-21's S5 scenario carries a **Must** requirement:

> **S5-Q2** *(Technical, Must)* — *Material preconditions are reassessed at use, not inherited from queue time.*

Semantics, aligned with S5: an **active freeze prohibits** the change; lifting it removes that restriction. The gate therefore consumes the **permitting condition `no_applicable_freeze`** — it must hold at use. A freeze may become applicable *after* the item is queued. (v1 of this example modeled the freeze as `freeze_still_holds`, an inverted and less direct framing; v2 adopts the permitting-condition naming suggested in the joint review.)

Two catalog entries describe why the registry-driven shape fails silently:

- [SF-006 · Undeclared = unchecked](../../failures/SF-006-undeclared-not-checked.md) — the check is exhaustive *with respect to the registry*; anything the registry forgot is never checked, and never missed.
- [SF-011 · The always-green oracle](../../failures/SF-011-always-green-oracle.md) — a check that cannot fail on the input it exists to catch is not a check; it is decoration.

## The three cases

Each case runs **two implementations on the identical world trace**: `before` evaluates the declared registry over the **queue-time snapshot**; `after` first diffs declared coverage against a stipulated-complete reference, then evaluates the declared conditions against state **read at use time**, then emits the prevention trace.

| Case | Declared | World event | `before` (snapshot) | `after` (use-time read) | What it isolates |
|---|---|---|---|---|---|
| **A-omitted** | 3 items (freeze not declared) | freeze becomes applicable | PASS, repair **executed during the breach** | FAIL — coverage gap named (SF-006) | detection of an *omission* relative to the reference |
| **B-temporal** | 4 items (freeze declared) | freeze becomes applicable | PASS — stale snapshot; repair executed during the breach | FAIL — value changed between queue and use; repair **blocked**, target unchanged | *use-time reassessment* — the decisive temporal case for S5-Q2; set-difference alone finds nothing here |
| **C-clean** | 4 items | none | PASS, legitimate repair executed | PASS, legitimate repair executed | the legitimate-activity control: reassessment must not over-block |

## How to run

stdlib only, Python 3.9+, no network, deterministic:

```
python simulation.py                  # selftest: runs all three cases on both
                                      # implementations, asserts they discriminate
python simulation.py --case A-omitted   # paired traces for one case
python simulation.py --case B-temporal
python simulation.py --case C-clean
```

`--case` exits 0 when the two implementations agree on the verdict, 1 when they discriminate (the interesting outcome).

## What it proves, and what it does not

- **Proves (A):** SF-006 detects an omission relative to the reference.
- **Proves (B):** coverage completeness alone is *not* use-time reassessment — a declared condition whose value drifts passes a snapshot-reading check and is caught only by reading state at use. The prevention trace shows the repair blocked and the target unchanged, keeping detection and prevention distinct.
- **Proves (C):** the controlled implementation preserves legitimate activity.
- **Stipulated, not proven:** the reference's completeness is an assumption of the bounded fixture (its provenance is an open architectural question — how the reference is obtained or created is not solved here). A use-time read implements reassessment in this model; establishing the *freshness* of that read (Q3 territory) is out of scope. This is a model result, not an AWS product execution.
- **Does not prove:** full S5 verification. This covers *one* requirement (S5-Q2); the remaining S5-Q0…Q5 and the other eight technology profiles are follow-on work, not claimed here.

## Files

| File | Purpose |
|---|---|
| [`simulation.py`](simulation.py) | the stateful simulation, its three cases, and the selftest |
| `README.md` | this page |
