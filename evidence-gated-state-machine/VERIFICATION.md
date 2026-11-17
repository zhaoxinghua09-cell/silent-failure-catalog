# VERIFICATION.md — evidence-gated state machine (fixed release)

> Publication record for the fixed reference implementation
> `evidence_gated_state_machine.py` in this folder (SHA-256 `26ED6159…`).

## What this is

A minimal, runnable reference implementation of evidence-gated lifecycle
governance constructs (registry spine with hash-chained audit trail,
evidence-gated transitions, silent-failure detectors, human-authorized
capability expansion). Apache-2.0, Python standard library only.

## Defect found and fixed (independent rerun, 2026-10-19)

An independent rerun with a negative control (QC-07: relevant errors must be
able to fail) exposed a real defect in the earlier version of
`verify_chain()`:

- **Defect:** the original `verify_chain()` called `e.materialize(prev)`, which
  recomputes **and overwrites** `e._hash` in place. "Recompute then compare"
  was therefore always equal — a permanent blind spot: tampering with a
  registered entity's data after registration was never detected.
- **Fix:** `verify_chain()` now recomputes each link **without side effects**
  (plain `hashlib.sha256` over the current payload) and compares against the
  stored hash. In-place tampering with a registered entity's fields is now
  detected.
- **Impact on normal path:** none — the 7 self-checks still pass, exit code 0.

## What this fix does not cover (measured 2026-10-28)

The fix closes one vector, and this record used to stop at "tampering is now
detected", which an independent review measured as too wide. Three further
vectors survive in this version, each reproduced on the published artefact:

- deleting the last registered entity leaves `verify_chain()` true (the walk
  covers `self.entities`, never `self.chain`, so chain length is not compared
  against the number of registration events);
- `chain.append(...)` after registration leaves `verify_chain()` true, same
  cause;
- tampering with an entity and then re-registering it recomputes a consistent
  hash, and no append-only record of prior hashes exists to contradict it.

They are recorded as open defects in the repository's defect ledger, not
resolved here. Read the sentence above as "in-place modification is detected",
not as "the chain is tamper-proof".

## This artefact is executed by the repository's gate list

Added 2026-10-28. Before this, all seventeen gates ran without ever executing
this folder: a marker side effect planted in the implementation was seen by none
of them, and replacing `verify_chain()` with `return True` still let
`.githooks/pre-commit` print `all gates passed`. `tools/state-machine-negative-control.py`
now runs the demonstration, requires the negative control to bite, and kills two
mutants in a throw-away copy — including that exact `return True` edit. Its
output also prints the three vectors above as declared non-coverage, so the
gate states what it does not see instead of implying it sees everything.

## Reproduction four-tuple

| Element | Value |
|---|---|
| Artefact by digest | SHA-256 (pre-fix) `243D553A98E9382B81126C94B94ACED1659CAA0CD9A49981C3F2B98DEB3E4964` → SHA-256 (post-fix) `26ED61598E1C68AC5B3C1AF60B49D1C192AF3EEDF184B47C69BC41B8EBEF747C` |
| Tool version | Python 3.13.16 (Windows, `python -X utf8`) |
| Moment | 2026-10-19 (evaluation date) |
| Method | `python evidence_gated_state_machine.py` (7 self-checks) + `python demo_tamper_check.py` (negative control) |

## Full test run (captured)

See `TEST-RUN.txt` in this folder — captured stdout of both runs with exit
codes (7 PASS, exit 0; negative control detects tampering, exit 0).

## Worked example (D5-style)

AI-assisted diagnosis agent `diag-agent v1.0` (model `rev-Q3`, tool
`imaging-db`, dataset `train-set-v3`) registered into the spine (chain
depth 5). A claimed model update to `rev-Q4` requires `version_manifest` +
`benchmark_rerun`; missing evidence ⇒ **DENIED with receipt** (invalid, not
discouraged). A capability expansion (e.g., automated prescription suggestion)
is denied even with evidence until a **distinct human-authorization flag** is
set (authority ≠ capability). Post-deployment detectors fire on subgroup
drift / expired input / out-of-envelope paths. Return-to-service requires
fresh reverification evidence (non-monotonic, re-earned).

## Boundary

Self-reported reference implementation for standards discussion — not a
certified standard, not a medical device, no clinical claim. Users must
confirm against current official texts.
