# Taxonomy

**as of 2026-09-19** · Status: `stable`

---

## One bug, five layers

Every family in this catalog is the same bug seen at a different layer of a system:

> ### The absence of evidence is recorded as evidence of absence of a problem.

A gate that checks only what it can find will always pass. The only kind of gate that can fail is one that **also asserts that the expected thing exists**.

Concretely, a check has four parts, and a silent failure is always one of them missing:

| Part | If missing → | Family |
|---|---|---|
| **1. Something to check** | the check runs over an empty set and passes | A · Vacuous Verification |
| **2. A way for "absent" to count** | required-but-missing is recorded as a neutral note | B · Uncounted Absence |
| **3. A signal that can prove the claim** | the evidence cannot support the conclusion | C · Wrong Evidence |
| **4. An oracle that keeps discriminating** | the check degrades until it always passes | D · Drifting Oracle |

Family E is separate: the logic is correct, but the **environment around it lies** — a stale artifact, a hung process.

---

## A · Vacuous Verification

*The check runs. It has no discriminating power.*

| ID | Name | The shape |
|---|---|---|
| [SF-001](../failures/SF-001-zero-items-pass.md) | Zero items collected, exit 0 | The runner ran and collected nothing. A green suite that never ran |
| [SF-002](../failures/SF-002-early-return-as-skip.md) | Early return as an implicit skip | A guard exits the test body instead of reporting a skip — an invisible skip |
| [SF-003](../failures/SF-003-swallowed-exception.md) | Swallowed exception | `try/except: pass` added "for robustness" deletes the failure signal |
| [SF-004](../failures/SF-004-sentinel-value.md) | Sentinel value on failure | Errors returned as `0.0` / `""` / `[]`, so a crash looks like a bad result |

**Family signature:** the test exists, the run is green, the assertion never had a chance to be wrong.

## B · Uncounted Absence

*Something required is missing, and missing does not count as failure.*

| ID | Name | The shape |
|---|---|---|
| [SF-005](../failures/SF-005-neutral-marker-not-counted.md) | Neutral marker not counted | Required-but-absent is reported as a neutral note, so it never increments the failure counter |
| [SF-006](../failures/SF-006-undeclared-not-checked.md) | Undeclared means unchecked | The validator verifies declared items only — a missing declaration is invisible |
| [SF-007](../failures/SF-007-empty-value-is-silent.md) | Empty value is silent | An empty required field breaks nothing observably |

**Family signature:** this is the **most dangerous family**, because the failure mode is *nothing*. No error, no exception, no drift. The artifact simply lacks something, and every consumer downstream renders that as fine.

> **The one rule that kills this family:** *missing must enter the exit code.*
> If "expected but absent" only produces a log line, a neutral marker, a warning or a skip, then a required-but-absent state yields `exit 0` — the gate is blind exactly where it matters most.
> A useful diagnostic habit: count the check's possible outputs. If there are N states and only N−1 of them can produce a non-zero exit, the missing one is your bug.

## C · Wrong Evidence

*The signal cannot prove the conclusion drawn from it.*

| ID | Name | The shape |
|---|---|---|
| [SF-008](../failures/SF-008-loading-artifact-as-evidence.md) | Loading artifact as evidence of use | A file written at startup proves "loaded", not "used" |
| [SF-009](../failures/SF-009-exposure-counted-as-usage.md) | Exposure counted as usage | Content present in every request inflates a count into a fake usage metric |
| [SF-010](../failures/SF-010-local-green-not-remote-green.md) | Local green is not remote green | All local gates pass; the published artifact still disagrees |

**Family signature:** the number is real and the conclusion is false. These are **proxy** failures — a convenient signal is standing in for the signal you actually need.

**Test to apply:** state the claim, then ask *"could this evidence be true while the claim is false?"* If yes, the evidence is a proxy.

## D · Drifting Oracle

*The check itself degrades until it stops discriminating.*

| ID | Name | The shape |
|---|---|---|
| [SF-011](../failures/SF-011-always-green-oracle.md) | The always-green oracle | An exemption clause that fires on any match makes the check unconditionally pass |
| [SF-012](../failures/SF-012-misattributed-failure.md) | Misattributed failure | The check fails, but blames the wrong cause — so the real defect survives |

**Family signature:** the oracle **starts** correct and decays. SF-011 usually arrives as a well-meant exemption; SF-012 usually arrives as a heuristic that is right most of the time.

**Test to apply:** the **countersign test**. Feed the oracle the exact thing it is supposed to catch. If it stays green, it does not discriminate. (This is why every fix in this catalog must carry a negative control.)

## E · Process & Environment

*The logic is fine. The environment misleads it.*

| ID | Name | The shape |
|---|---|---|
| [SF-013](../failures/SF-013-stale-copy-contaminates-check.md) | Stale copy contaminates the check | A backup written inside the checked directory is read as fresh input |
| [SF-014](../failures/SF-014-zombie-process-looks-alive.md) | Zombie process looks alive | A hung process reports no error, holds no CPU and never exits |

**Family signature:** reproduce it and it works. The defect is in *state*, not in *code* — which is why these are the ones people dismiss as flaky.

## Cross-cutting: two mechanical rules

Everything above reduces to two rules that can be enforced by tooling.

### Rule 1 — Missing must enter the exit code

```
required-but-absent  →  non-zero exit
```

Any neutral representation of a required item's absence (a note, a ⚪, a `warn`, a `skip`, a log line) is a **silent pass** in waiting.

### Rule 2 — No negative control means no evidence

```
a check that has never been seen failing
        ==
a check that has not been shown to be capable of failing
```

Every fix should ship with the input that makes it fail. This is the same principle as mutation testing, applied beyond test suites: break the thing the check guards, confirm the check notices, restore.

> These two rules are what `tools/gate-lint.py` looks for mechanically.

---

## Why naming matters

An unnamed phenomenon cannot be searched for, cited, or fixed.

Before this catalog, the phenomenon described by SF-005 was typically reported as *"the check passed but the data was missing"* — a sentence that describes a symptom without identifying a mechanism. Once it has a name and an ID, it can be:

- **referenced** in a review comment (`this is SF-005`)
- **searched** (`neutral marker not counted`)
- **tested for** (`SFL-001`)
- **cited** with a date, so a regression becomes visible

## Related

- [Question Map](question-map.md) — the questions this catalog answers, by search intent
- [Catalog index](../failures/README.md) — all entries
- [Contributing](../CONTRIBUTING.md) — how entries are added and why the bar is where it is
