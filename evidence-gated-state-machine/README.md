# evidence-gated-state-machine

> Minimal, runnable reference implementation of evidence-gated lifecycle
> governance constructs for agentic AI — registry spine with hash-chained
> audit trail, evidence-gated transitions (invalidity, not discouragement),
> silent-failure detectors, and human-authorized capability expansion.
> Apache-2.0, Python standard library only, no network access required.

This folder is part of the [silent-failure-catalog](..) verifier-side
reference corpus. It supports FG-TIDA themes #39/#40 (to be resubmitted as a
formal Input Document for the 1st FG-TIDA Meeting, Paris, 30 Nov – 1 Dec 2026).

## Files

| File | Purpose |
|---|---|
| `evidence_gated_state_machine.py` | The reference implementation (7 self-checks, exit 0). SHA-256 `26ED61598E1C68AC5B3C1AF60B49D1C192AF3EEDF184B47C69BC41B8EBEF747C` |
| `demo_tamper_check.py` | Negative control (QC-07): proves tampering with registered data is detected |
| `VERIFICATION.md` | Fix record (pre/post SHA, four-tuple, defect description, worked example) |
| `TEST-RUN.txt` | Captured full test run: 7 PASS + negative control, with exit codes |
| `LICENSE` | Apache-2.0 — the licence this folder's files declare in their headers. The repository root carries MIT for the rest of the corpus; this folder is separately licensed on purpose and says so here. |

## Known limits (measured, not asserted)

An independent review on 2026-10-28 executed this folder against adversarial
edits. Five limits were measured and are listed rather than left to be
discovered by a reader who trusts the code:

1. `verify_chain()` walks the registered entities and compares each against the
   hash stored at registration. It does **not** compare the chain length against
   the number of registration events, so **deleting the last registered entity
   still verifies true**, and so does appending an entry directly to `chain`.
2. Tampering with an entity and then re-registering it recomputes a consistent
   hash; with no append-only record of prior hashes, the tamper becomes
   invisible.
3. Expiry comparison is a string comparison, not a parsed-date comparison, so
   mixed date formats (`2026-9-1` vs `2026-10-01`) can be ordered wrongly and
   silently.
4. `human_authorized` is a boolean the caller supplies. It records that a
   decision was made; it carries no approver identity, signature or receipt
   hash, so it is not authentication.
5. Receipts accumulate in memory and are not written to the chain, so they are
   not tamper-evident.

These are limits of a **demonstration of expressibility**, which is what this
folder claims to be. They are not limits of the proposal: each names a
requirement the full construct must meet, and each is tracked in the
repository's defect ledger rather than described away here.

What the folder does now prove, and did not before: the repository gate list
**executes** this code (`tools/state-machine-negative-control.py`), and that
gate kills a copy of the implementation whose verifier is reduced to
`return True`. Before the gate existed, that exact edit passed every check.

## Reproduce

```
python evidence_gated_state_machine.py   # 7 PASS, exit 0
python demo_tamper_check.py              # negative control: tamper detected, exit 0
```

Requires Python 3 (verified on 3.13.16, 2026-10-19).
