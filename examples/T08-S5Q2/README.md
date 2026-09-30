# T08-S5Q2 · Example — a stateful pre-flight that cannot fail, and the control that makes it fail

**Status**: `example` ｜ **Source**: FG-TIDA use-cases #21, Annex T08 (AWS Step Functions / RDS) · UC-21, requirement S5-Q2 ｜ **as of** 2026-09-30

> **One line.** A Step-Functions-style pre-flight gate evaluates a declared registry against a queue-time snapshot, so a precondition that was never declared — and one that changed while the item sat in the queue — passes green at use time. Four commands reproduce it; the same trace with the reverse-coverage control fails non-zero, naming the undeclared precondition.

© 2026 赵兴华 / Steven Zhao · China. Rights reserved; theoretical text not under Apache-2.0.

---

## What this demonstrates

UC-21's S5 scenario carries a **Must** requirement:

> **S5-Q2** *(Technical, Must)* — *Material preconditions are reassessed at use, not inherited from queue time.*

In a T08-style implementation, preconditions are typically encoded as a declared registry that a pre-flight check iterates. Two catalog entries describe exactly why that shape fails silently:

- [SF-006 · Undeclared = unchecked](../../failures/SF-006-undeclared-not-checked.md) — the check is exhaustive *with respect to the registry*; anything the registry forgot is never checked, and never missed.
- [SF-011 · The always-green oracle](../../failures/SF-011-always-green-oracle.md) — a check that cannot fail on the input it exists to catch is not a check; it is decoration. The control below is proven able to fail, which is the only evidence it can discriminate.

## How to run

stdlib only, Python 3.9+, no network, deterministic:

```
python simulation.py                  # selftest: runs both traces, asserts they discriminate
python simulation.py --trace before   # the silent failure: exits 0 (green) on a violated world
python simulation.py --trace after    # the SF-006 control: exits 2, naming 'freeze_still_holds'
```

## The trace, step by step

Both modes run the **identical world**: the material is enqueued while a freeze holds (`t0`), the freeze is lifted while the item sits in the queue (`t1`), and the gate runs at use time (`t2`). Only the validator differs.

**`--trace before`** — the registry-driven check evaluates the declared registry against the *queue-time snapshot*:

```
t2  PREFLIGHT registry-driven check: 3 declared precondition(s) evaluated against the queue-time snapshot
t3  PREFLIGHT verdict: PASS  <-- the violated, undeclared precondition was never in the frame
t4  EXECUTED  remediation executed; the system fails silently
```

PASS on a world that breaches S5-Q2. No error, no row, no evidence of the skip — controls work, system fails.

**`--trace after`** — the same trace with the reverse-coverage control applied:

```
t2  PREFLIGHT reverse-coverage control: actual-at-use vs declared, 4 vs 3 item(s)
t3  ABORTED   verdict: FAIL  -- ['freeze_still_holds'] exist but are undeclared (S5-Q2 breach)
```

The failure names the undeclared precondition. That is the point: **the negative control is observed to fail**, which is what makes the before-verdict mean something.

## What it proves, and what it does not

- **Proves:** the negative-control method localizes *where* the T08 pre-flight is blind to S5-Q2 — at the registry's coverage boundary and at the queue-time snapshot, not inside the asserted logic. The selftest asserts both halves, so a future edit that makes the two traces stop discriminating turns red here first.
- **Does not prove:** full S5 verification. This covers *one* requirement (S5-Q2) through *one* gate (SF-006). The remaining S5-Q0…Q5 and the other eight technology profiles are follow-on work, not claimed here.

## Files

| File | Purpose |
|---|---|
| [`simulation.py`](simulation.py) | the stateful simulation and its selftest (this example's only code) |
| `README.md` | this page |
