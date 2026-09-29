# Changelog

All notable changes to this catalog. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

Entries are append-only. A retired entry is marked `deprecated` and kept online.

## [Unreleased]

### Changed

- **Licence notice made consistent: the prose content is all rights reserved.**
  `LICENSE-CONTENT` described the content as CC BY 4.0 while the rights notice at the
  top of `README.md` reserved all rights. A file whose two ends disagree about its own
  licence is the same shape as the failures this catalog documents, so the badges, the
  page footer, `CITATION.cff`, `.zenodo.json`, `SUPPORT.md`, `docs/where-to-find-us.md`,
  `docs/question-map.md` and `llms.txt` now say what the notice says. Code stays MIT,
  and citation with attribution stays permitted. **A licence already granted for copies
  obtained earlier is not affected** — a licence is not revoked; this governs copies
  obtained from here on.

### Added

- **`.githooks/pre-commit`** — the five gates, moved in front of the commit.
  Enable with `git config core.hooksPath .githooks`. The hook discovers its
  interpreter (never hard-codes a path) and **refuses to commit when it cannot
  run**: an unrunnable check is not a passed check. It is a required file, so
  `check-catalog.py` fails if it goes missing — otherwise every gate becomes
  something a human has to remember, and the run where they forget is
  indistinguishable from the run where it passed.
- **AGENTS.md rule 11 — an unknown fact is marked, never guessed.** Use
  `[NEEDS CLARIFICATION: <question>]` where the fact belongs. A plausible guess
  is indistinguishable from a verified fact once it is written down.
- **AGENTS.md rule 12 — a check that cannot run is a check that failed.**
- Cross-reference from the entry page to **`assayance`**, the doctrine these
  entries are evidence for. The two are kept separate on purpose: this
  repository is the catalogue, that one is the doctrine, and neither is a copy
  of the other.

### Changed

- `docs/where-to-find-us.md` gains an `assayance` row in both the human and the
  channel tables.

## [0.1.0] — 2026-09-19

Initial release.

### Added

- **Taxonomy** (`docs/taxonomy.md`): five families — Vacuous Verification, Uncounted Absence,
  Wrong Evidence, Drifting Oracle, Process & Environment — and the shared root cause.
- **Question Map** (`docs/question-map.md`): four levels of search intent with citable answers.
- **14 entries**:

  | Family | Entries |
  |---|---|
  | A · Vacuous Verification | SF-001 zero items collected · SF-002 early return as skip · SF-003 swallowed exception · SF-004 sentinel value |
  | B · Uncounted Absence | SF-005 neutral marker not counted · SF-006 undeclared means unchecked · SF-007 empty value is silent |
  | C · Wrong Evidence | SF-008 loading artifact as evidence of use · SF-009 exposure counted as usage · SF-010 local green is not remote green |
  | D · Drifting Oracle | SF-011 the always-green oracle · SF-012 misattributed failure |
  | E · Process & Environment | SF-013 stale copy contaminates the check · SF-014 zombie process looks alive |

- **`tools/gate-lint.py`**: static linter for silent-pass patterns, with a `--selftest` mode
  that runs the linter against its own bundled bad/good samples.
- **`tools/check-catalog.py`**: internal consistency validation (required sections, id uniqueness,
  index sync, link resolution) plus a heuristic leak scan.
- **`tools/make-manifest.py`** + `INTEGRITY.md` + `manifest.sha256`: content integrity — a
  SHA-256 per file and one digest over the set, with `--check` to verify a checkout.
  Includes its own negative control in CI.
- **`.gitattributes`** with `* -text`: byte-exact checkouts, so the digests are the same on
  every platform. Without it, Git's end-of-line translation would silently change the bytes
  and the manifest would be wrong on one platform only.
- **AI-readable skeleton**: `AGENTS.md`, `llms.txt`, `CITATION.cff`, per-file Markdown.
- **Entry layer**, so that a reader arriving from any one of our projects can find the rest:
  - `docs/start-here.md` — symptom → entry, in one table. Now a required index target, so a
    new entry that is not indexed there fails validation.
  - `docs/where-to-find-us.md` — the single page carrying every outbound link, plus citation
    rules for retrieval systems and an explicit list of what this project declines to do.
  - `docs/take-the-challenge.md` — three tiers from "run the linter on your own gate" to
    "break our linter", each with a stated outcome and a credit policy.
- **Community files**: `SUPPORT.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  `.github/PULL_REQUEST_TEMPLATE.md`, and three issue forms
  (`.github/ISSUE_TEMPLATE/` — new failure mode, linter false positive, contact links).
- **`.zenodo.json`**, so a GitHub release can be archived to a DOI with the creator's ORCID
  attached, instead of the metadata having to be re-typed into a web form.
- **`check_promo_links`** in `tools/check-catalog.py`: outbound links to our own channels are
  permitted only in the two entry pages, and a violation is a validation failure. It ships
  with `--selftest`, which asserts a sample pair (one input it must flag, one it must not),
  a negative control with the rule set emptied, and that the rule neither always fires nor
  never fires. CI runs it.
- **`docs/building-this-catalog.md`**: the ten defects found in this repository's own
  tooling while building it, with the control that found each one. Defect 10 is a comment
  asserting a regex token was load-bearing; testing the claim showed it was not.
- **CI** (`.github/workflows/validate.yml`): runs the tools on every push and pull request,
  including a negative control that corrupts one byte and requires the integrity check to fail.

### Notes

- License split: MIT for code, CC BY 4.0 for prose content.
- No entry claims conformance with any standard.
- Changing any content file requires regenerating the manifest in the same commit. The
  friction is deliberate: a manifest permitted to drift is worse than none, because it is
  read as evidence.
- **The tooling was developed by feeding it its own medicine.** Running the
  selftest and a reverse-control suite against the tools found ten defects in
  the tools themselves. All are fixed; the record is kept in
  [`docs/building-this-catalog.md`](docs/building-this-catalog.md) because a
  catalogue about silent passes that was itself silently passing would be worth
  nothing.
