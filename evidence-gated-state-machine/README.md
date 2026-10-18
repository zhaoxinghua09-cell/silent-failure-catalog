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

## Reproduce

```
python evidence_gated_state_machine.py   # 7 PASS, exit 0
python demo_tamper_check.py              # negative control: tamper detected, exit 0
```

Requires Python 3 (verified on 3.13.16, 2026-10-19).
