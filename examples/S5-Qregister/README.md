# Example: S5 gate-register crosswalk (UC-21, Annex S5 sections 7-10 / Annex T08)

A runnable companion to the FG-TIDA contribution (use-cases #21): the
scenario-local gate register **Q0–Q6** and its two diagnostic trace shapes
(`capability-absent`, `ineffective-control`) are made **executable**, and
cross-walked to the four-case negative-control matrix of
[`examples/T08-S5Q2`](../T08-S5Q2/).

Annex source pinned at commit `aec08fb5b0fac2ee399372370e9ee2a82a2d5779`
(scenarios/S5.md, technology/T08.md, CONVENTIONS.md).

## What it shows

| Profile (T08 route) | Gate trace | Outcome on `supersession` |
|---|---|---|
| `I0-ordinary` | Q1/Q2/Q4 `CAPABILITY_ABSENT` — no semantic basis object at all (S5 §10.1) | stale patch **executes during the breach** |
| `I1-defended` | Q2 passes superficially; Q3 reads a 5-minute cache, Q4 omits the Patch B generation — `CONTROL_EXECUTED_FAILED` (S5 §10.2) | stale patch **executes during the breach** |
| `I2-complete` | every gate evidenced incl. Q6 recheck-to-act binding | **REASSESS → blocked** |

Fixture branches (per S5 §7.1): `continuity` (positive control — a deny-all
implementation fails it), `supersession`, `act-window` (residual TOCTOU), and
`ambiguity` (**UNKNOWN is not permission** — bounded non-execution/escalation).

## Crosswalk: S5 register ↔ four-case matrix ↔ T08 tests

| S5 gate | Four-case matrix (examples/T08-S5Q2) | T08 test |
|---|---|---|
| Q1 explicit basis | case A (SF-006 omission) | Test B prep |
| Q2 use-time recheck | case B (temporal drift) | Test B (base Semantic TOCTOU) |
| Q3 source freshness | *assumption* in T08-S5Q2 (declared out of scope there) | Test C/D evidence |
| Q4 supersession | case B variant (state transition) | Test C (D1 drift) |
| Q5 bounded ambiguity/scope | *extension*: UNKNOWN is not permission | Test E (D3/D4/D5) |
| Q6 recheck-to-act binding | case D (act-window) | Test B/C residual window |
| positive continuity control | case C (clean baseline) | Test A (continuity admission) |

Reading: the register supplies **per-gate evidence granularity** that the
four-case matrix abstracts into pass/fail; the matrix supplies the
**discriminative-power discipline** (hardcoded expectations, mutation
killing) that makes the register's traces auditable instead of narrative.

## Who tests the tester (gate layer)

Four mutants of the `I2` gate evaluator, each killed on exactly its crosswalk
branches:

| Mutant | Defect | Killed by |
|---|---|---|
| `G1-no-supersession` | Q4 dropped | `supersession` |
| `G2-cache-read` | Q3 reverts to the cache | `supersession`, `ambiguity` |
| `G3-no-binding` | Q6 dropped | `act-window` |
| `G4-blanket-deny` | Q5 scope bug | `continuity` |

Expected outcomes are hardcoded from the published register, never derived
from running the mutated code. A design observation the register itself
predicts: `G2` is *not* killed on `act-window`, because Q6 binds against the
live actuation state — the gates are not interchangeable, and the mutation
matrix documents which gate absorbs which defect.

## Product anchors (verified against AWS documentation, 2026-10-01)

- **Q2 is structural, not optional**: Step Functions passes the start input as
  a snapshot; live external state requires an explicit Task state
  (docs.aws.amazon.com/step-functions/latest/dg/concepts-input-output-filtering.html).
- **Q6 has a native lever**: `StopExecution` stops a running Standard
  execution and is observable via EventBridge *Execution Status Change* —
  "freeze before use" maps to a real product mechanism
  (docs.aws.amazon.com/step-functions/latest/apireference/API_StopExecution.html).
- **Q4/Q6 binding primitives**: DynamoDB conditional writes + optimistic
  locking (version attribute) implement compare-before-act
  (docs.aws.amazon.com/amazondynamodb/latest/developerguide/BestPractices_OptimisticLocking.html).
- RDS has no native change-freeze feature; enforcement is external
  (IAM deny on `rds:RebootDBInstance` / SCP), and the maintenance window does
  not gate user-initiated reboots.

## Qualifications

- A model result, **not an AWS product execution** — matching the annexes'
  own framing ("documentary walkthroughs ... still require
  execution-based verification").
- Source freshness is a boolean here; deep Q3 semantics (clock skew, logical
  ordering) stay out of scope, as in `examples/T08-S5Q2`.
- Reference completeness: stipulated for the bounded fixture, auditable via
  `fixture_spec.json` (the simulation fails loudly at startup on divergence).

## Usage

```
python simulation.py                    # selftest (default)
python simulation.py --branch supersession
python simulation.py --branch continuity | act-window | ambiguity
python simulation.py --crosswalk        # crosswalk table + product anchors
python simulation.py --mutants          # gate-layer kill matrix
```
