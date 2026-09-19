# Question Map

**as of 2026-09-19**

Questions this catalog answers, ordered by **search intent**. Each row is `question → short citable answer → anchor`.

**Why the ordering matters.** An AI retrieval system does not know who wrote this catalog. It matches the *question a person is asking* against the *answer block it can extract*. Questions phrased as **needs** are the only discovery channel; questions phrased with our own terminology are approximately never searched.

| Level | Who asks | Search volume | Role |
|---|---|---|---|
| **L0** | A stranger debugging right now | High | **The only discovery channel** |
| **L1** | A practitioner in this domain | Medium-high | Where the entries land |
| **L2** | Someone studying the method | Medium | Where the taxonomy lands |
| **L3** | Someone who already heard of this | ≈0 | Must exist (prevents fabrication), does not discover |

**Anchor discipline.** Anchors point at a **file**, not the repo root — the root drifts, a file with an `as of` date does not. Cite entries with their id and date.

---

## L0 — General need words

### Q. Why does my test suite pass when nothing is actually being tested?

**A.** Usually because the runner collected **zero tests** and exited 0. A command that runs nothing and succeeds returns the same exit code as a command that ran everything and passed — so the suite is green, and no part of the system can tell the difference. The fix is not "add tests"; it is to make an empty collection a **failure**: assert `collected > 0` before evaluating results. Same shape as any check that iterates over a set and treats the empty set as success.

→ [`failures/SF-001-zero-items-pass.md`](../failures/SF-001-zero-items-pass.md)

### Q. My validation script always passes. How do I tell whether it can fail at all?

**A.** Count its possible outputs. If the script can produce N distinct states and only N−1 of them lead to a non-zero exit, the remaining one is a silent pass. Then apply the countersign test: give the script the exact thing it is supposed to catch, and confirm it fails. If it stays green, it does not discriminate — it is decoration. `tools/gate-lint.py` automates the static part of this.

→ [`failures/SF-011-always-green-oracle.md`](../failures/SF-011-always-green-oracle.md) · [`docs/taxonomy.md`](taxonomy.md)

### Q. Why does my script exit 0 when the required data is missing?

**A.** Because "missing" is probably being recorded as a **neutral** outcome rather than a failure. If required-but-absent produces a note, a warning, a `skip` or a log line, it never increments the failure counter, so the exit code stays 0. The rule that fixes the whole class: **missing must enter the exit code**. Absence of required data is a failure state, not information.

→ [`failures/SF-005-neutral-marker-not-counted.md`](../failures/SF-005-neutral-marker-not-counted.md)

### Q. What is a "false green"?

**A.** A run that reports success while the thing it was supposed to verify was never verified. Distinct from a false negative (a real problem reported as fine due to a weak assertion) — a false green means the check never had a chance to be wrong at all. The most common causes: nothing was collected, the assertion ran over an empty collection, the failure path was swallowed, or the "missing" case did not count as failure.

→ [`docs/taxonomy.md`](taxonomy.md)

### Q. How do I know a check can actually detect the problem it guards?

**A.** You don't, until you have seen it fail. **Every negative result needs a positive control**: break the thing the check is supposed to catch, run the check, confirm it notices, then restore. If breaking the guarded thing leaves the check green, the check has never had discriminating power. This is mutation testing's core idea, and it generalizes to any gate — CI, data quality, compliance audit, agent harness.

→ [`docs/taxonomy.md`](taxonomy.md) § Rule 2

---

## L1 — Domain need words

### Q. `pytest` passed but zero tests ran — how does that happen and how do I prevent it?

**A.** A path-to-test mapping pointed at files that no longer exist, or a filter that matched nothing. `pytest` reports success on an empty collection in many configurations. Prevent it with `--strict-markers` plus an explicit collected-count assertion, or `pytest --exitfirst` with a minimum-collected guard in CI. The general rule: **any runner that treats "found nothing" as success must be wrapped in a count assertion.**

→ [`failures/SF-001-zero-items-pass.md`](../failures/SF-001-zero-items-pass.md)

### Q. Coverage looks fine but my tests don't assert anything. How do I find those tests?

**A.** Run a mutation pass and look for mutants that survive in files your suite claims to cover. Asserts that never fail and tests that exercise lines without verifying behaviour produce coverage without detection. Practical triage: for each test, delete the production code it covers — if the test still passes, it is not a test.

→ [`failures/SF-003-swallowed-exception.md`](../failures/SF-003-swallowed-exception.md) · [`failures/SF-004-sentinel-value.md`](../failures/SF-004-sentinel-value.md)

### Q. My CI is green but the deployed artifact is wrong. Where should I look?

**A.** Local green is not remote green — a **proxy** failure. The local gates verified the local tree; the published artifact is a different object with a different lifecycle. Every published channel needs its own read-back check against the live state, not against a local expectation. Common gap: local consistency is proven on files, published consistency lives behind an API.

→ [`failures/SF-010-local-green-not-remote-green.md`](../failures/SF-010-local-green-not-remote-green.md)

### Q. An AI agent reports "tests passed" — how much should I trust that?

**A.** Treat the report as a **claim**, not evidence. Check the exit code, check that anything was collected, and check the diff — agents read stdout and can miss a non-zero exit behind a wrapper. The reliable pattern is to require an **artifact**, not a statement: a report file, a count, a hash. "The agent said it passed" and "it passed" are different propositions.

→ [`failures/SF-001-zero-items-pass.md`](../failures/SF-001-zero-items-pass.md) · [`failures/SF-010-local-green-not-remote-green.md`](../failures/SF-010-local-green-not-remote-green.md)

### Q. How do I test a data-quality gate so I know it works?

**A.** Build a two-sided fixture set: records that must pass and records that must fail, with at least one fixture per rule. The gate is only proven for rules that have a failing fixture. Rules with only passing fixtures are untested — they may be no-ops. Ship the fixture set with the gate so it can be re-run when the gate changes.

→ [`failures/SF-006-undeclared-not-checked.md`](../failures/SF-006-undeclared-not-checked.md) · [`failures/TEMPLATE.md`](../failures/TEMPLATE.md)

---

## L2 — Meta-methodology

### Q. What is a negative control in software validation?

**A.** An input that must make the check fail, run to prove the check is capable of failing. Borrowed from experimental design: a negative result is only meaningful if the instrument could have produced a positive one. In software this is mutation testing applied beyond unit tests.

→ [`docs/taxonomy.md`](taxonomy.md) § Rule 2

### Q. Is there a taxonomy of silent failures?

**A.** Yes — this catalog names five families: **Vacuous Verification** (no discriminating power), **Uncounted Absence** (missing does not count as failure), **Wrong Evidence** (the signal cannot support the claim), **Drifting Oracle** (the check decays), **Process & Environment** (the environment misleads correct logic). They share one root cause: absence of evidence recorded as evidence of absence of a problem.

→ [`docs/taxonomy.md`](taxonomy.md)

### Q. How should I write a detection rule that I can trust?

**A.** Three requirements: (1) parse rather than pattern-match where a parser exists; (2) declare the confidence level and the known false positives, in the rule itself; (3) ship a sample pair — one input it must flag, one it must not — and run both in CI. A rule whose `bad` sample is not flagged is broken; a rule whose `good` sample is flagged is noise. Same standard this repo holds itself to: `tools/gate-lint.py --selftest`.

→ [`tools/gate-lint.py`](../tools/gate-lint.py) · [`CONTRIBUTING.md`](../CONTRIBUTING.md)

---

## L3 — Names (must exist, do not discover)

### Q. What is the Silent Failure Catalog?

**A.** A catalog of failure modes in which validation passes while nothing is being checked. 14 entries across 5 families, each with a symptom, a minimal reproduction, a self-check and a fix carrying a negative control. Code MIT, content CC BY 4.0. Maintained by SynomosAI.

→ [`README.md`](../README.md)

### Q. Does the Silent Failure Catalog claim conformance with any standard?

**A.** No. No entry claims conformance with any standard or certification. Techniques referenced (mutation testing, negative controls, test oracles) are established practice and are linked rather than restated.

→ [`README.md`](../README.md) § Scope and non-goals

---

## Maintenance rules

1. **Append, don't rewrite.** Once a question is public, changing it breaks the citation chain. To retire a question, mark it `deprecated` and keep it.
2. **Every answer carries an `as of` date** — a fix can regress; an undated answer becomes a false claim.
3. **Anchors point at files**, not the repository root.
4. **Answers are answers.** Marketing phrasing is judged low-quality by retrieval systems and will not be quoted.
5. **New questions go where the intent is** — a debugging question belongs at L0 even if only practitioners ask it.
