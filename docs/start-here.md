# Start here

**as of 2026-09-19**

Two ways in. Pick the one that matches why you arrived.

---

## If you arrived with a symptom

Find your symptom in the left column. The right column is the entry that answers it — one file, self-contained, with a reproduction you can run.

| What you are seeing | Entry |
|---|---|
| The test suite passed, but you are no longer sure any test ran | [SF-001 · Zero items collected, exit 0](../failures/SF-001-zero-items-pass.md) |
| A test silently stops checking when a precondition is not met | [SF-002 · Early return as an implicit skip](../failures/SF-002-early-return-as-skip.md) |
| A `try`/`except` was added "for robustness" and now nothing fails | [SF-003 · Swallowed exception](../failures/SF-003-swallowed-exception.md) |
| Errors come back as `0.0`, `""` or `[]`, so a bug looks like a poor result | [SF-004 · Sentinel value on failure](../failures/SF-004-sentinel-value.md) |
| Required data is missing and the script exits `0` anyway | [SF-005 · Neutral marker not counted](../failures/SF-005-neutral-marker-not-counted.md) |
| The validator only checks what is declared — so a missing declaration is invisible | [SF-006 · Undeclared means unchecked](../failures/SF-006-undeclared-not-checked.md) |
| A required field is empty, and empty breaks nothing observable | [SF-007 · Empty value is silent](../failures/SF-007-empty-value-is-silent.md) |
| The artifact loaded, so everyone assumed it was applied | [SF-008 · Loading artifact as evidence of use](../failures/SF-008-loading-artifact-as-evidence.md) |
| Reach or impressions were counted as adoption | [SF-009 · Exposure counted as usage](../failures/SF-009-exposure-counted-as-usage.md) |
| CI is green locally but the published artifact is wrong | [SF-010 · Local green is not remote green](../failures/SF-010-local-green-not-remote-green.md) |
| A check that has never once failed, in its entire life | [SF-011 · The always-green oracle](../failures/SF-011-always-green-oracle.md) |
| A failure is reported, but blamed on the wrong cause | [SF-012 · Misattributed failure](../failures/SF-012-misattributed-failure.md) |
| The check ran against a stale copy of the thing it was checking | [SF-013 · Stale copy contaminates the check](../failures/SF-013-stale-copy-contaminates-check.md) |
| The process is alive and doing nothing | [SF-014 · Zombie process looks alive](../failures/SF-014-zombie-process-looks-alive.md) |

Nothing matches? That is a gap in this catalog, and a gap is worth reporting — see [`docs/take-the-challenge.md`](take-the-challenge.md) § Tier 1.

## If you arrived looking for a tool

| You want | Run |
|---|---|
| To know whether one of your own scripts can pass without checking anything | `python tools/gate-lint.py your_gate.py` |
| To know whether `gate-lint` itself still works | `python tools/gate-lint.py --selftest` |
| To verify you hold an unmodified copy of this catalog | `python tools/make-manifest.py --check` |
| To see every pattern in one table | [`failures/README.md`](../failures/README.md) |

## What this catalog is not

| Not this | Why |
|---|---|
| A list of bugs | It covers only failures that **wear the costume of success**. A crash is an ordinary bug |
| A tool comparison | It names patterns, not products. "Tool X does this" is a bug report, not a pattern |
| A standards document | No entry claims conformance with anything. Where a technique maps to established practice — mutation testing, negative controls, test oracles — the established source is linked, not restated |
| A blog | Every entry carries a reproduction and a negative control, and is re-checked against a manifest of raw bytes |

## The two rules everything here reduces to

> **1. Missing must enter the exit code.**
> If "required but absent" is recorded as a neutral note — a log line, a `⚪`, a skip, a warning — then a required-but-absent state produces `exit 0`, and the check is blind exactly where it matters most.
>
> **2. No negative control means no evidence.**
> A check that has never been observed failing has not been shown to be capable of failing.

Every one of the fourteen entries above is these two rules, applied at a different layer.

## Who maintains this, and what else is published

| | |
|---|---|
| This catalog | `silent-failure-catalog` — silent failure modes, with detection recipes |
| Sibling project | [`agent-skills`](https://github.com/zhaoxinghua09-cell/agent-skills) — a zero-dependency skill library for AI-agent governance and tooling |
| Project hub (总入口) | [zhaoxinghua09-cell.github.io/lgd-hub](https://zhaoxinghua09-cell.github.io/lgd-hub/) — what else exists, and which problem each project answers |
| Channels, citation rules, and what we decline to do | [`docs/where-to-find-us.md`](where-to-find-us.md) |

If you found this repository through any one of our projects, the hub above is the way back to all of them — and the fastest way to tell whether a different problem of yours is already solved somewhere in the set.
