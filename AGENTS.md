# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this repo is

A catalog of **silent failure modes** — validation that passes while nothing is being checked.

Two kinds of artifact:

| Path | Kind | Rule |
|---|---|---|
| `failures/SF-*.md` | prose entries | One file = one failure mode. Never merge two. |
| `tools/*.py` | runnable checks | stdlib-only, no network, Python 3.9+ |
| `docs/start-here.md` | **index** | Must link every `SF-*.md` file. `check-catalog.py` fails if it does not. |
| `docs/where-to-find-us.md`, `docs/start-here.md` | **entry pages** | The only files allowed outbound links to our own channels. See rule 9. |
| `docs/taxonomy.md` | **class source** | The `SF-nnn` ids and their names. Read them here; do not restate them elsewhere. See rules 14 and 15. |
| `docs/defect-ledger.json` | **defect ledger** | One record per defect, closed by gate 10. A fix with no ledger entry is a fix that nothing can interrogate. See rule 14. |
| `.githooks/pre-commit` | **hook** | Runs every gate before each commit — the full list lives here and *only* here; no document restates the count in prose (a mirror may label its steps). Enable with `git config core.hooksPath .githooks`. Never hard-code an interpreter path here. |
| `.github/workflows/gates.yml` | **CI** | The same gates as the hook, plus the negative control, on every push and pull request. `.githooks/pre-commit` is the specification; this is its echo — change one list and the other is wrong. |
| `INTEGRITY.md`, `manifest.sha256` | generated | Never edit by hand. Regenerate — see rule 7. |

## Before you change anything (Gate 0)

Ask one question first: **can this change be shown to fail?**

A check, a test, a rule, or a measurement that no input can break is decoration, not
a gate. If nothing you can imagine would make it fail, that is the defect — build the
input that breaks it *first*, so the change has something to be measured against. This
is the same rule as the `checker-mutation` gate in `.githooks/pre-commit`, one layer up:
it applies to your reasoning, not only to the code you are about to write.

## Hard rules

1. **One failure mode per file.** Do not combine. A reader (or a retrieval system) must be able to fetch one entry and get one complete answer.
2. **Every entry must have a reproduction.** A description without a reproduction is an anecdote and will be rejected.
3. **Every fix must state a negative control.** The fix is not "add a check" — it is "add a check *and* show that it fails when the thing is broken."
4. **No vendor claims, no standard conformance claims.** Never write "compliant with X" unless a normative reference is quoted.
5. **Generalize incidents.** If an entry came from a real incident, strip client names, internal paths, hostnames, ticket ids and personal data. See `CONTRIBUTING.md` § De-identification.
6. **IDs are append-only.** `SF-nnn` is permanent. Deprecate by adding `**Status**: deprecated` plus the superseding ID — never renumber, never reuse.
7. **Change content → regenerate the manifest in the same commit.** `python tools/make-manifest.py`. CI runs `--check` and will fail otherwise. Also: placeholders must be written without an `@` (use `example.invalid`, not an address-shaped string) — a scanner that fires on placeholders trains people to ignore it.
8. **Never use a loop variable that shadows a name you return.** Defect 9 in `docs/building-this-catalog.md` was exactly this: the artifact was correct and the printed report was wrong, and only a second independent computation caught it.
9. **Outbound links to our own channels go on the entry pages only** — `docs/where-to-find-us.md` and `docs/start-here.md`, listed in `ENTRY_PAGES`. Everywhere else they are a failure, enforced by `check_promo_links` in `tools/check-catalog.py`; run `python tools/check-catalog.py --selftest` after touching that rule. Links to *this* repository (clone URLs, badge URLs, `/issues`) are structural and always allowed.
10. **Do not assert a necessity you have not measured.** A comment in this repository once claimed a regex token was load-bearing without testing it (defect 10, `docs/building-this-catalog.md`). If a comment says "without this it breaks", go break it and check.
11. **An unknown fact is marked, never guessed.** When a figure, date, version, parameter or behaviour cannot be verified from a primary source, write `[NEEDS CLARIFICATION: <the specific question>]` where the fact belongs and leave it visible. Do not fill the gap with a plausible value, do not soften the sentence until it is unfalsifiable, and do not drop the claim silently. A plausible guess is indistinguishable from a verified fact once it is written down — that is exactly the failure this repository documents, one layer up. Recorded instances: the exact CLI parameters of an external tool were cited from a secondary summary rather than the tool's own source, and a note that "JSON is less likely to be corrupted than Markdown" was read in an article *citing* the original — both were written up as leads, explicitly marked as unverified.
12. **A check that cannot run is a check that failed.** If an interpreter, a dependency or a required file is missing, the gate exits non-zero. Never `|| true`, never an unreadable file treated as an empty one, never a skip. The hook in `.githooks/pre-commit` refuses to commit when no Python interpreter can be found, rather than passing quietly.
13. **Every check must be shown able to fail.** A gate that has never been *observed* failing is a claim, not a check. `tools/checker-mutation.py` (its own gate) mutates this repository's own checks and requires each mutation to break a selftest; if you add or edit any check, register it there (or with an equivalent negative control) so that "it can fail" is exercised, not asserted. On 2026-10-07 this rule was added after twelve checks were audited and **seven of them had never been shown able to fail**.
14. **Every external correction closes the loop.** A defect report is not fixed by editing the named site. It is fixed by (a) classifying it against `docs/taxonomy.md` (`SF-xxx`); (b) naming the escape cause — **E1** no check existed / **E2** a check existed without a negative control / **E3** it was reported but not load-bearing / **E4** it was never fed a hard input; (c) adding the mechanical gate that kills the *class*, not the instance; (d) scanning every sibling artifact for the same class; (e) recording it in `docs/defect-ledger.json`. `tools/defect-closure.py` (its own gate) fails if any ledger entry is open or lacks evidence.
15. **A count is stated once.** Any number that describes this repository — how many gates, how many entries — is read from its single source and never repeated as a literal in prose. `tools/verify_release_consistency.py` fails if a gate-count written in the docs disagrees with `.githooks/pre-commit`. Repeated literals drift, and the drift is invisible until someone counts by hand (2026-10-07: three living docs stated a stale gate count while the hook already ran more).

## Adding an entry

1. Copy `failures/TEMPLATE.md` → `failures/SF-<next>-<slug>.md`
2. Fill every section. Empty sections are a validation failure, not a style choice.
3. Link the new file from **all four** index targets: `failures/README.md`, the taxonomy table in `README.md`, `llms.txt`, and `docs/start-here.md` (symptom → entry). `check-catalog.py` fails on any that is missing.
4. Add a line to `CHANGELOG.md`.
5. Run `python tools/check-catalog.py` — it must exit 0.
6. Run `python tools/make-manifest.py` — the manifest covers the new file.
7. Run the whole gate. The list is not repeated here — it has one source, `.githooks/pre-commit`, and `.github/workflows/gates.yml` mirrors it gate-for-gate. Run it directly:

```bash
bash .githooks/pre-commit
```

Every gate must exit 0. Enable the hook once per clone: `git config core.hooksPath .githooks`. A gate that depends on being remembered has a silent failure mode of its own — the run where you forget looks identical to the run where everything passed.

8. If this fixes a defect (yours or a reviewer's), add a record to `docs/defect-ledger.json` — class it (`SF-nnn`, read from `docs/taxonomy.md`), name the escape cause (`E1`–`E4`), name the gate you added, and scan the sibling entries for the same class. `tools/defect-closure.py` fails if the record is missing or open. See rule 14.
9. If you added or changed a check, register its negative control in `tools/checker-mutation.py` (or an equivalent) so it is *shown* able to fail; and if it is a new gate, add both the gate and its `--selftest` to `.githooks/pre-commit` and `.github/workflows/gates.yml`. See rule 13.

## Style

- English is the primary language. Add a `中文要点` block at the end of an entry if it is useful; do not translate the whole file.
- Section headings are fixed and machine-parsed. Do not rename them. The required set:

```
## Symptom
## Why it is silent
## Minimal reproduction
## Self-check
## Fix
## Related
```

- Code blocks used as reproductions must be runnable as-is, or explicitly marked `# illustrative`.
- Keep entries under ~120 lines. If you need more, you are describing two failure modes.

## Writing a detection rule (tools/)

- Use `ast` for Python source analysis. Do not regex source you can parse.
- **Every heuristic must declare its confidence** (`high` / `medium` / `low`) and its known false positives.
- **Every rule must have a sample pair** in `tools/samples/`: one `bad` file it must flag, one `good` file it must not. `--selftest` runs them. A rule without a sample pair is not merged.
- Do not add dependencies. If you need a library, the rule does not belong here.

## What not to do

- Do not add an "awesome list" of links. This is a catalog of *patterns*, not a link dump. If a link is genuinely our own channel, it belongs on an entry page (rule 9); if it is not, it has to earn its place by supporting a specific claim.
- Do not add entries about failures that already produce a crash or non-zero exit. Those are ordinary bugs.
- Do not soften the language into marketing. Entries are technical claims; the value is that they are falsifiable.
