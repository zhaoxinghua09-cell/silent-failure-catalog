# Example: S5 gate-register crosswalk (UC-21, Annex S5 sections 7-10 / Annex T08)

A runnable companion to the FG-TIDA contribution (use-cases #21): the
scenario-local gate register **Q0–Q6** and its two diagnostic trace shapes
(`capability-absent`, `ineffective-control`) are made **executable**, and
cross-walked to the four-case negative-control matrix of
[`examples/T08-S5Q2`](../T08-S5Q2/).

Annex source pinned at commit `aec08fb5b0fac2ee399372370e9ee2a82a2d5779`
(scenarios/S5.md, technology/T08.md, CONVENTIONS.md).

**Revision 2026-10-06** — the run is now a **blinded experiment**. It answers the
five points the adversarial review of 2026-10-05 raised before this example may
join a joint comparison; see "Review feedback" below.

**Revision 2026-10-07** — a third review pass asked for four tightenings, all
applied here: (1) the crosswalk agreement gate now compares **every column**, not
just the gate name, and is given a negative control; (2) the post-verdict freeze
is delivered to the runner as an **effective timestamp**, not a pre-classified
label — Q6 derives the lost binding itself; (3) the exit status is re-derived
from the *final* verdict and checked for coherence against the rest of the
record; (4) the mutant suite now states each mutant's **class** (input fault
injection vs post-decision deviation), instead of a single claim that was untrue
of one of them.

## Three files, and why the split

| File | Role | Knows the branch identity? |
|---|---|---|
| `harness.py` | holds the branch table, builds the observables, injects the mutants, probes the target state | **yes — only here** |
| `implementation.py` | the artifact under test: the I0/I1/I2 gate runners | **no** |
| `simulation.py` | the entry point (CLI) | reads it from the harness; never passes it on |

The split is what makes the blinding more than a convention: the
implementation module does not import the harness, so no branch table exists
anywhere in its name space, and the observation it receives carries no branch
name. Stated plainly, the boundary closes only the *ordinary* escape. The
resourceful routes — a lazy `import harness`, reading `fixture_spec.json` off
disk, or `os.environ` / `sys.modules` machinery — are not closed by module
boundaries; they are scanned for by `_assert_blind` and fail the selftest if
any of them appears in the implementation's executable code. Detection, not
invisibility.

## What it shows

| Profile (local simulation) | Gate trace | Outcome on `supersession` |
|---|---|---|
| `I0-ordinary` | Q1/Q2/Q4 `CAPABILITY_ABSENT` — no semantic basis object at all (S5 §10.1) | stale patch **executes during the breach** |
| `I1-defended` | Q2 passes superficially; Q3 reads a 5-minute cache, Q4 omits the superseding generation — `CONTROL_EXECUTED_FAILED` (S5 §10.2) | stale patch **executes during the breach** |
| `I2-complete` | every gate evidenced incl. Q6 recheck-to-act binding | **REASSESS → blocked** |

> **Naming note:** `I0/I1/I2` here are **local simulation profiles** of this
> example only. They are distinct from T08's `AWS-I2` walkthrough (the *same
> strong implementation retained under context drift*), which this example
> does not claim to implement; `I2-complete` corrects selected known branches
> inside a documentary evaluator, nothing more.

## Fixture branches, with Patch B and the freeze decoupled

The review asked for the two material controls to be independent rather than
set together on one branch. They now are: `patch_b` and `freeze` are separate
inputs, all four combinations are separate branches, and each is ruled on by
exactly the control that applies.

| Branch | `patch_b` | `freeze` | Correct ruling |
|---|---|---|---|
| `continuity` | no | no | `EXECUTE` (positive control — a deny-all runner fails it) |
| `supersession` | yes | no | `BLOCK_REASSESS` → affected generation requalified |
| `prohibition` | no | yes | `DENY` (prohibition: the freeze alone blocks) |
| `patch-and-freeze` | yes | yes | `BLOCK_REASSESS` (Patch B drives; the freeze does not hide it) |
| `act-window` | no | no — a freeze becomes effective *inside* the act window (`t_check <= t_freeze <= t_act`) | blocked at the action boundary (Q6) |
| `ambiguity` | no | no (`source_available: false`) | bounded HOLD / escalation — an unknown state is not permission |

A runner that merges the two controls cannot produce more than one of these
right, which is what the selftest now asserts mechanically.

## Crosswalk: S5 register ↔ four-case matrix ↔ T08 tests

| S5 gate | Four-case matrix (examples/T08-S5Q2) | T08 test |
|---|---|---|
| Q1 explicit basis | case A (SF-006 omission) | Test B prep |
| Q2 use-time recheck | case B (temporal drift) | Test B (base Semantic TOCTOU) |
| Q3 source freshness | *assumption* in T08-S5Q2 (declared out of scope there) | Test C/D evidence |
| Q4 supersession | case B variant (state transition) | Patch B supersession branch — **separate from D1**: D1 changes the applicable policy/source set *after* the corrected strong baseline is frozen, which is a different scenario |
| Q5 bounded ambiguity/scope | *extension*: an unknown state is not permission | Test E (D3/D4/D5) |
| Q6 recheck-to-act binding | case D (act-window) | Test B/C residual window |
| positive continuity control | case C (clean baseline) | Test A (continuity admission) |

Reading: the register supplies **per-gate evidence granularity** that the
four-case matrix abstracts into pass/fail; the matrix supplies the
**discriminative-power discipline** (hardcoded expectations, mutation
killing) that makes the register's traces auditable instead of narrative.

## Who tests the tester (gate layer)

Four mutants of the `I2` gate layer, in **two classes**. They are stated as what
they are, rather than bundled under one claim that fits only some of them:

- **input fault injection** — the observation handed to the runner is altered
  *before* it rules (`M2-cache-read` serves the use-time read from the stale,
  pre-event view);
- **post-decision deviation** — the verdict is rewritten *after* the runner has
  ruled (`M1`, `M3`, `M4`).

Neither class edits `implementation.py` itself. A **source-code mutation** — a
defect written into the artifact under test — is deliberately *not* used here,
because such a defect would be one we authored rather than one we measured. Each
mutant is killed on at least its crosswalk branch, and **no mutant may survive
anywhere**.

| Mutant | Defect | Class | Killed by |
|---|---|---|---|
| `M1-no-supersession` | Q4 outcome discarded | post-decision deviation | `supersession`, `patch-and-freeze` |
| `M2-cache-read` | the use-time read is served from the stale pre-event view | input fault injection | `supersession`, `patch-and-freeze` |
| `M3-no-binding` | Q6 recheck-to-act binding skipped | post-decision deviation | `act-window` |
| `M4-blanket-deny` | scope bug: every gate satisfied and the target still untouched; a blanket stop, so the positive control breaks | post-decision deviation | `continuity` |

The kill criterion is the **three-channel observation**:

1. **guard decision** — what the runner ruled (`EXECUTE` / `BLOCK_REASSESS` /
   `DENY` / `BLOCK_BOUNDARY` / `HOLD_ESCALATE`);
2. **attempted action** — whether the repair was pushed at the target;
3. **target state** — read back from the harness's own stateful target model
   (`TargetModel`) after the harness's actuator performed the attempted
   action; *not* reported by the runner.

Channel 3 is the point of the last review point: an implementation that graded
its own homework would return `repair_applied=False` and be believed; here the
harness owns a target model its actuator rewrites, and the probe reads that
model — a blocked branch is evidenced by "the target is still at its baseline
generation", not by anything the runner says. The selftest also fails if a
runner ever grows an input that is not an `Observation`.

Row 4 of the truth table (`patch-and-freeze`, MUST M2): the `(T,T)` and `(T,F)`
branches share a guard decision, so the trace is where the second reason must
show — the `(T,T)` trace records **both reasons present** (supersession AND
the freeze prohibition), and the selftest asserts that marker exists there and
is absent from the `(T,F)` trace.

Expected outcomes are hardcoded from the published register, never derived from
running the code under test — deriving them would make every assertion
tautological.

## Product anchors (verified against AWS documentation, 2026-10-01)

- **Q2 is structural, not optional**: Step Functions passes the start input as
  a snapshot; live external state requires an explicit Task state
  (docs.aws.amazon.com/step-functions/latest/dg/concepts-input-output-filtering.html).
- **Q6 has an abort lever, not a freeze**: a stop primitive exists —
  `StopExecution` terminates a running Standard execution and is observable via
  EventBridge *Execution Status Change*. It is an **abort lever**; "freeze
  before use" has to be layered on top of such a primitive, and freeze
  semantics are not a native feature
  (docs.aws.amazon.com/step-functions/latest/apireference/API_StopExecution.html).
- **Q4/Q6 binding primitives**: DynamoDB conditional writes + optimistic
  locking (version attribute) implement compare-before-act
  (docs.aws.amazon.com/amazondynamodb/latest/developerguide/BestPractices_OptimisticLocking.html).
- **RDS**: no native change-freeze feature; enforcement is external (IAM deny on
  `rds:RebootDBInstance` / SCP), and the maintenance window does not gate
  user-initiated reboots.
- **What none of the above proves**: the presence of a stop primitive is not
  evidence that a freeze did *not* occur, and is not evidence of the freeze's
  failure either. It bounds what an implementer could have used — it does not
  establish what happened.

## Qualifications

- A model result, **not an AWS product execution** — matching the annexes'
  own framing ("documentary walkthroughs ... still require
  execution-based verification").
- Source freshness is a boolean here; deep Q3 semantics (clock skew, logical
  ordering) stay out of scope, as in `examples/T08-S5Q2`.
- Reference completeness: stipulated for the bounded fixture, auditable via
  `fixture_spec.json` (the simulation fails loudly at startup on divergence).
- The blinding is enforced by module boundary plus the `_assert_blind` scan:
  the boundary removes the ordinary escape (no name in scope), and the scan
  fails the selftest if the implementation's executable code contains a lazy
  `import harness`, a `fixture_spec.json` read, or `open()` / `os.environ` /
  `sys.modules` machinery — the routes a boundary alone does not stop. Subtler
  covert channels remain out of scope for a documentary fixture and are stated
  here rather than left implied.
- README/code agreement is itself a gate, and it compares **every column** of the
  crosswalk table (not just the gate name — the mapping columns are where a
  silent drift hides) plus the mutant table's class and "killed by" columns,
  against `CROSSWALK_ROWS` / `MUTANT_CLASS` / `MUTANT_KILLERS` at every selftest
  run. The gate is also given a **negative control**: a README with one tampered
  mapping cell must fail it, so the gate is shown to have teeth rather than
  assumed to.
- The post-verdict freeze reaches the runner as an **effective timestamp**
  (`t_freeze`), not as a pre-classified label. Deciding that it falls inside the
  check-to-act window — and so breaks the binding — is the Q6 gate's own
  inference; handing over a `post_verdict` label would have pre-classified the
  very answer Q6 exists to establish.
- The observation record is checked for **internal coherence** on every run (and
  on every mutant run): the exit status is the numeric form of the guard
  decision, an EXECUTE guard implies the repair was attempted, and the target
  moves exactly when it was — so a record such as `PASS + DENY + NONE +
  unchanged` cannot be produced and believed. That assertion, too, carries a
  negative control.

## Usage

```
python simulation.py                    # selftest (default)
python simulation.py --branch supersession
python simulation.py --branch continuity | act-window | ambiguity
                      | prohibition | patch-and-freeze
python simulation.py --crosswalk        # crosswalk table + product anchors
python simulation.py --mutants          # gate-layer kill matrix
```

Note: `--branch` and `--crosswalk` are display modes and always exit 0 —
only `--selftest` (and the CI gate that runs it) asserts anything.
