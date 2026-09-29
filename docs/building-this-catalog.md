# Building this catalog

**as of 2026-09-29**

A catalog about checks that pass while nothing is verified has an obvious obligation: **it must not be one.** This page records the defects found in this repository's own tooling while building it, and how each was found.

It is kept because the method is the point. Every defect below was invisible to ordinary review — all of them were found by *running the check against an input that must make it fail*, which is Rule 2 of the [taxonomy](taxonomy.md).

---

## The two controls used

| Control | What it does | Why nothing else finds this class |
|---|---|---|
| `gate-lint.py --selftest` | Runs every rule against a bundled **bad** sample it must flag and a **good** sample it must not | A rule that silently stops working is invisible; it produces no output either way |
| Reverse-control suite | Mutates the repository's own state (remove a link, point at a missing file, remove all negative samples) and asserts the tool **exits non-zero** | Confirms the gate can fail, not merely that it ran |

A third, unintentional control: **running the linter on its own source.** Several defects were found simply by pointing the tool at the tool.

---

## Defects found in the tools themselves

### 1. A verdict issued without enforcing its own precondition

`_silent_body_kinds()` is documented as "describe a handler body **if every statement discards the failure**". The implementation accumulated silent statement kinds and returned them if non-empty — it never verified that *every* statement was silent.

Result: this handler, which correctly records a failure, was reported as `except block only does: continue`:

```python
except OSError as e:
    store.add(rel(p), "could not be read: %s" % e)
    continue
```

**Found by:** running the linter on its own source.
**Fixed by:** returning `[]` as soon as any statement is not a discard.

### 2. A guard detected by substring, not by structure

`SFL-005` searched the raw source text for the word `collected` to decide whether a test runner's output was guarded. The **bad** sample's docstring happened to contain the phrase *"without checking that it collected anything"* — so the rule concluded a guard existed and stayed silent.

This is `SF-012` (substring match standing in for identity) inside the linter.

**Found by:** `--selftest` — the bad sample was not flagged.
**Fixed by:** detecting a guard *construct* (`Compare` over a string literal, or a pattern-match call) via the AST, rather than a mention in prose.

### 3. A substring test in the catalog validator

`check-catalog.py` asserted that each entry id appeared in the index files using `if eid in text`. After an entry's link was deliberately mangled to `SF-014-REMOVED`, the assertion **still passed**, because `"SF-014"` occurs inside the mangled string.

Same failure family as #2 — and it was in the validator whose job is to catch exactly that.

**Found by:** reverse control A (mangle a link, assert non-zero exit).
**Fixed by:** asserting that the entry's **filename** is linked, not that its id occurs as text.

### 4. A missing target treated as success

`gate-lint.py /nonexistent/path.py` printed `no Python files found` and exited **0**. Being asked to check something that does not exist and reporting success is `SF-006` — undeclared means unchecked.

**Found by:** reverse control B.
**Fixed by:** explicit targets that do not exist are a failure; so is "nothing was linted".

### 5. Findings reported but not counted

Tree-level findings (`SFL-006`) were printed but never added to the severity counters. The visible output contained a finding while `--strict` exited **0** — the exit code did not reflect what the tool had just reported.

**Found by:** reverse control C run in strict mode.
**Fixed by:** tree-level findings enter the same counters as file-level ones.

### 6. The suppression directive matched its own documentation

`# gate-lint: ignore SFL-001` was matched with a plain regex over the source. But `gate-lint.py`'s own docstring **quotes that directive while documenting it** — so the file suppressed `SFL-001` for itself, and the linter never checked itself for the rule it had just implemented.

**Found by:** reading the "inline suppressions" note in the linter's own output and asking why that file had one.
**Fixed by:** honouring the directive only inside a `tokenize.COMMENT` token. If the source cannot be tokenised, suppressions are **ignored**, not guessed — failing toward "checked" is the only safe direction.

### 7. An unreadable file printed and then forgotten

Unreadable files were announced on stdout and then dropped. An announcement is not a signal: the run could still exit 0. An unlinted file is an unverified file.

**Found by:** reading the SFL-002 finding on the linter's own source.
**Fixed by:** unreadable files are counted, listed, and force a non-zero exit.

### 8. A rule shipped with unmeasured severity

`SFL-003` was released at `medium`. Measured against two files of ordinary tooling it produced **four findings and zero true positives**, while affecting the exit code.

**Found by:** running the linter on its own source and reading every finding.
**Fixed by:** demoting it to `low` / confidence `low`, scoping it to module level and check-shaped functions, and stating the measured precision in the rule's own false-positives note. A rule's stated confidence should be the measured one, or it is decoration.

### 9. A report that disagreed with the artifact it reported on

`make-manifest.py` computes a set digest over every file, writes it into `INTEGRITY.md`, and prints it. The per-file table was emitted with:

```python
for path, digest in entries:      # rebinds `digest`
    lines.append("| `%s` | `%s` |" % (digest, path))
return digest                     # now the hash of the LAST file, not the set digest
```

The name `digest` was already bound to the set digest. The loop **rebound it** to each file's hash in turn, so the function returned the hash of the last file in the list.

The subtlety is what this did *not* do: the value written into `INTEGRITY.md` was computed **before** the loop, so the artifact was correct. Only the printed/returned value was wrong. The tool's own verifier then rejected the tool's own output — `--check` reported one digest while the generator reported another, and both were "successful".

This is the catalog's own subject one level up: not a wrong check, but **a correct artifact described by a wrong report**. Every downstream reader of the printed number would have been misled while the file on disk was fine.

**Found by:** `--check` disagreeing with the generator's own stdout. Neither run failed on its own.
**Fixed by:** renaming the loop variable (`file_digest`). Verified by re-running all three channels — generate, `--check`, `--print-digest` — and requiring one identical value.

### 10. A comment asserting a necessity the code did not have

The outbound-link rule added on 2026-09-19 scrubs this repository's own URLs from each line before looking for self-promotional links. Its first draft carried this comment:

```python
# The `(?:\.git)?` is load-bearing. Without it, `.../silent-failure-catalog.git`
# does not match here, falls through to the "sibling repository" pattern below,
# and is reported as someone else's repository. That false positive was produced
# by the first version of this regex and caught by selftest case 3.
```

Three separate claims, all checkable, all produced by reasoning rather than by running anything:

| Claimed | Actual |
|---|---|
| Without `(?:\.git)?`, the clone URL fails to match | It matches. The lookahead is `(?![\w-])`, and the character after `catalog` is `.`, which is not in `[\w-]` — so the scrub succeeds and stops before the dot |
| The leftover `.git` is then reported as a sibling repository | It is not. The sibling pattern requires a full `https://github.com/...` prefix, which the scrub has already consumed |
| Selftest case 3 caught this | It could not have. Case 3 passes under **both** regexes |

The comment described a defect that never existed, in a file whose subject is claims that were never checked. It was found the only way such a claim can be found: by **re-running the selftest against the version of the regex the comment said was broken**, and watching the case pass.

**Found by:** testing a comment instead of trusting it — loading the module, replacing `CANONICAL_RE` with the "broken" naive form, and re-running every selftest case.
**Fixed by:** replacing the comment with what the measurement showed, and keeping the token as explicitly defensive. The claim is not deleted; deleting it would remove the only evidence that the reasoning was wrong.

Note what the fix is *not*. It is not a change to the code — the code was already correct. It is a change to **a statement about the code**. Defect 9 was a tool that printed a wrong number beside a correct file; this one is a tool that documented a wrong reason beside correct logic. The class is the same, and it is the one this catalog keeps rediscovering: **a description is a claim, and a claim nobody tested is not evidence.**

### 11. A safeguard described in five places and implemented in none

`README.md` withheld a CI badge on purpose. The comment said a badge claiming a validation run
that does not exist "would be exactly the silent pass this repo documents", and pointed instead at
a check a reader could run locally right now. The reasoning was sound; the conclusion was wrong.
The honest alternative to a false badge is a workflow, not a note about a workflow.

Eleven lines below that comment, the same file said **"CI enforces this"**. `CONTRIBUTING.md`
promised that a pull request adding an entry without updating all six index files "will fail CI",
and that the manifest "has a **negative control in CI**". `AGENTS.md` rule 7 said "CI runs
`--check` and will fail otherwise".

`.github/workflows/` did not exist. There was no CI. Five statements across three files, in a
repository whose entire subject is *a check believed to be running, and not running*.

**Found by:** writing `.github/workflows/gates.yml` and pushing it. No amount of reading finds a
run that never happened: an absent run emits nothing, and nothing in the repository distinguishes
it from a run that passed. Its first execution also failed a gate that a local run had reported as
passing — the same family one level up, in a person's checklist rather than in a tool, which is why
it is recorded in `CHANGELOG.md` and not below.

**Fixed by:** adding the workflow — the five gates from `.githooks/pre-commit`, in the same order
and with the same meaning, on Python 3.9 and 3.12, plus both negative controls — and repointing the
badge at it. The claim was not deleted; it was made true. A claim deleted is a claim nobody has to
check; a claim satisfied is one that now fails loudly on the day it stops being satisfied.

---

## What this page is for

Not self-flagellation — **evidence for the general claim.** All eleven defects are of the class the catalog documents, and none of them were found by reading the code. They were found by:

- running each rule against an input that must make it fail,
- mutating the repository's state and asserting a non-zero exit,
- pointing the tool at itself,
- testing a comment rather than believing it,
- requiring two independent computations to agree with each other.

If you take one thing from this repository, take the method rather than any single entry:

> **Every negative result needs a positive control.**
> A check that has never been observed failing has not been shown to be capable of failing.

And two corollaries that cost ten rounds of review here:

> **A documented safeguard is not an implemented one.** Five of the eleven defects above involved prose that described behaviour the code did not have — including one that described a *defect* the code did not have.

> **A passing run and a correct report are two different things.** Defect 9 wrote a correct file and printed a wrong number. If a value is reported anywhere — stdout, a badge, a summary, a comment — it needs its own route to verification, because it will be read as the truth even when the artifact beside it is right.

## Related

- [Taxonomy](taxonomy.md) — the five families these defects belong to
- [Question Map](question-map.md) — the questions this catalog answers
- [Contributing](../CONTRIBUTING.md) — the sample-pair requirement exists because of items 1, 2 and 8
