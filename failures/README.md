# Catalog Index

**14 entries** · **as of 2026-09-19** · Status legend: `stable` · `draft` · `deprecated`

One file = one failure mode. Each entry is self-contained and safe to quote directly.

---

## A · Vacuous Verification

*The check runs. It has no discriminating power.*

| ID | Entry | Symptom in one line | Status |
|---|---|---|---|
| [SF-001](SF-001-zero-items-pass.md) | Zero items collected, exit 0 | The suite is green because nothing ran | `stable` |
| [SF-002](SF-002-early-return-as-skip.md) | Early return as an implicit skip | The test body exits on a condition — invisibly | `stable` |
| [SF-003](SF-003-swallowed-exception.md) | Swallowed exception | `try/except: pass` deletes the failure signal | `stable` |
| [SF-004](SF-004-sentinel-value.md) | Sentinel value on failure | A crash is indistinguishable from a bad result | `stable` |

## B · Uncounted Absence

*Something required is missing, and missing does not count as failure.*

| ID | Entry | Symptom in one line | Status |
|---|---|---|---|
| [SF-005](SF-005-neutral-marker-not-counted.md) | Neutral marker not counted | "Expected but absent" is logged, not counted | `stable` |
| [SF-006](SF-006-undeclared-not-checked.md) | Undeclared means unchecked | The validator only checks what was declared | `stable` |
| [SF-007](SF-007-empty-value-is-silent.md) | Empty value is silent | An empty required field breaks nothing | `stable` |

## C · Wrong Evidence

*The signal used cannot prove the conclusion drawn from it.*

| ID | Entry | Symptom in one line | Status |
|---|---|---|---|
| [SF-008](SF-008-loading-artifact-as-evidence.md) | Loading artifact as evidence of use | A startup file proves loading, not use | `stable` |
| [SF-009](SF-009-exposure-counted-as-usage.md) | Exposure counted as usage | Ambient presence inflates a usage metric | `stable` |
| [SF-010](SF-010-local-green-not-remote-green.md) | Local green is not remote green | Local gates pass, the published state differs | `stable` |

## D · Drifting Oracle

*The check itself degrades.*

| ID | Entry | Symptom in one line | Status |
|---|---|---|---|
| [SF-011](SF-011-always-green-oracle.md) | The always-green oracle | An exemption clause makes the check unconditional | `stable` |
| [SF-012](SF-012-misattributed-failure.md) | Misattributed failure | It fails, but blames the wrong thing | `stable` |

## E · Process & Environment

*The logic is correct. The environment lies to it.*

| ID | Entry | Symptom in one line | Status |
|---|---|---|---|
| [SF-013](SF-013-stale-copy-contaminates-check.md) | Stale copy contaminates the check | A backup inside the checked tree is read as input | `stable` |
| [SF-014](SF-014-zombie-process-looks-alive.md) | Zombie process looks alive | A hung process reports nothing and never dies | `stable` |

---

## Roadmap

Planned / welcome as contributions — see [`../CONTRIBUTING.md`](../CONTRIBUTING.md):

- Clock and locale assumptions in oracles (`timezone-shifted oracle`)
- Time-based checks that silently skip on a date boundary
- Retry logic that converts a hard failure into a soft one
- Pagination truncation read as a complete result set
- Cache-hit read as a fresh verification
- Aggregation over an empty partition
- Idempotency checks that pass because the second run never executed

## Adding an entry

```bash
cp TEMPLATE.md SF-<next>-<slug>.md
python ../tools/check-catalog.py     # must exit 0
```

Also update this file, the taxonomy table in `../README.md`, and `../CHANGELOG.md` — in the same commit.
