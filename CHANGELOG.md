# Changelog

All notable changes to this catalog. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

Entries are append-only. A retired entry is marked `deprecated` and kept online.

## [Unreleased]

Gates 9 and 10, three new hard rules, and the closure of an external review round.

### Added

- **`tools/impl-mutation.py` (gate 12)** — systematically mutates `implementation.py` itself
  (five first-order operator classes over the token stream: comparison flip, boolean
  negation, boolean-operator swap, numeral edit, literal flip) and requires every
  non-equivalent mutant to be killed by the S5 selftest, reporting a mutation score against
  a break threshold and classifying 10x-baseline timeouts as killed. Grounded by
  `SENTINEL-noop` / `SENTINEL-fatal` (grounding sentinels are reported but excluded from
  the mutant count and the score). An initial run left several real mutants alive; the
  survivors drove four new decision-point negative controls (exit-code contract, per-key
  missing-timestamp refusal, freeze-window boundary equality, per-profile
  source-unavailable traces); the suite now kills 11 of the 12 real mutants, with the
  one survivor disclosed as equivalent under the current observation contract
  (`EXIT_FAIL` numeral, no numeric contract in the fixture).
- **Metamorphic relations MR-1/2/3** in the S5 harness — oracle-independent invariance
  checks across every (profile, branch) pair: unrelated-key invariance, uniform time-shift
  invariance, older-prefix lineage monotonicity; the relation checker carries a negative
  control (a magnitude-leaking stub must be flagged). Narrows the shared-provenance oracle
  gap (Barr et al. 2015 pseudoracle class) without claiming to close it.
- **`tools/checker-mutation.py`** — mutates this repository's own checks and requires each
  mutation to break a selftest, so "our checks can fail" is a checked property. Its first run
  found that 7 of the S5 selftest's 12 decision points had never been shown capable of failing.
- **`tools/defect-closure.py`** — reads `docs/defect-ledger.json` and fails if any recorded
  defect is open or missing evidence; it also resolves every path-like token in `gate_added`
  and requires it to exist and (for tools) to be invoked by `.githooks/pre-commit`.
- **`docs/defect-ledger.json`** — one structured record per defect (class, escape cause, root
  cause, gate, evidence); nineteen entries.
- **`AGENTS.md` rule 13** (every check must be shown able to fail), **rule 14** (every external
  correction closes the loop), **rule 15** (a count is stated once), and a **Gate 0** section.
- A **gate-count consistency check** in `tools/verify_release_consistency.py`: a live document
  that states a gate count must agree with `.githooks/pre-commit` (the single source).

### Changed

- `.githooks/pre-commit`, `.github/workflows/gates.yml` and `AGENTS.md` no longer restate a
  gate count; they point at the hook. The stale "seven gates" literal is gone.
- `README.md` and `index.md` corrected; the defect count now points at its source.
- `.github/PULL_REQUEST_TEMPLATE.md` no longer tells contributors to run "four gates" — it
  runs the whole hook.

### Fixed

- `gate-lint.py` crashed with `KeyError: 'PARSE'` on an unparseable file (the `PARSE` finding
  was emitted but never registered in `RULES`). Covered by a new selftest case.
- `defect-closure.py` no longer fails open when the hook cannot be read.

## [0.1.1] — 2026-10-07

Release-integrity patch. The catalogue content is unchanged; what changed is the layer that
guarantees a reader holds the bytes the release claims. See `REVIEW.md`, "Second review round".

### Added

- **`examples/S5-Qregister/harness.py`** and **`examples/S5-Qregister/implementation.py`** —
  the S5 gate-register example is now a *blinded experiment*. The harness holds the branch
  table and builds the observation; the implementation under test receives only observables
  (current generation, source state/version, freeze state, supersession lineage, timestamps,
  authority/policy state, binding tokens) and cannot see which fixture produced them. The
  harness also measures the target state on its own instead of believing the runner's
  self-reported repair flag, and injects the four mutants after the runner has ruled.

### Changed

- **`examples/S5-Qregister/` is split into three files** (`harness.py` / `implementation.py` /
  `simulation.py`). The blinding is a module boundary, not a convention.
- **`Patch B` and the freeze are separate controls** (`patch_b` × `freeze`), so all four
  combinations are distinct branches with distinct rulings; the previously-merged
  `supersession` branch is joined by `prohibition` (freeze only) and `patch-and-freeze`
  (both). This was review point R-4.
- **The mutation suite was re-cut on the review's points**: the I2 layer's mutants are now
  `M1–M4`, and the kill criterion is the three-channel observation
  (guard decision, attempted action, independently probed target state) rather than a
  runner-supplied boolean — review point R-5.
- **Gate 8**: `.github/workflows/gates.yml` and `.githooks/pre-commit` both run
  `examples/S5-Qregister/simulation.py --selftest`, so the blinded example is exercised by CI
  and not only by whoever remembered to run it (review point R-2).
- **`_print_crosswalk()` output and the Q6 anchor text now match `README.md`**: the Q4 row no
  longer says "Test C (D1 drift)" (D1 is a different scenario), and the `StopExecution` line
  reads as an *abort lever* with freeze semantics explicitly not a native feature, rather than
  as a freeze mechanism — review point R-1.
- **`_print_crosswalk()` moved to `examples/S5-Qregister/harness.py`** in the three-file
  split (the entry point reaches it via `simulation.py --crosswalk`); its rows now live in one
  module-level table shared with the README agreement gate below.
- **`examples/` added to the MIT grant.** `LICENSE` now names `examples/` alongside
  `tools/`, `.githooks/` and `.github/`, and states explicitly that the grant covers the
  example-level README files there; `LICENSE-CONTENT` records the same. Raised when a
  participant asked which terms cover `examples/S5-Qregister` and `examples/T08-S5Q2`
  before redistributing the runnable companion — the previous text named three
  directories, so the examples were covered by neither licence.

### Review round 2 (2026-10-06, MUST M1–M4)

- **Truth-table row 4 is asserted on the trace**: `patch-and-freeze` records **both reasons
  present** (supersession AND the freeze prohibition) in its `I2` trace; the selftest
  distinguishes `(T,T)` from `(T,F)` on that marker — the two branches share a guard decision,
  so the trace is the only place the second reason can be told apart (`examples/S5-Qregister/`).
- **The target-state channel is a state read, not a formula**: the harness owns a stateful
  `TargetModel` its own actuator rewrites, and `probe_target_state()` reads the model's
  pre/post snapshots instead of being a function of (guard decision, attempted action). A
  blocked branch is evidenced by "the target is still at its baseline generation"
  (`examples/S5-Qregister/`).
- **`_assert_blind()` closed the three escape routes review round 2 named**: a lazy
  `import harness`, a `fixture_spec.json` read, and any `open()` / `os.environ` /
  `sys.modules` machinery in the implementation's executable code now fail the selftest
  (string-literal dynamic-import shapes included). The earlier "closed by module boundaries"
  sentence in the harness docstring was judged false by the review and is rewritten: the
  boundary closes the ordinary escape; detection closes the resourceful ones.
- **`examples/T08-S5Q2/`: the action-boundary re-verification is unconditional** — it runs
  before *every* permitted actuation rather than only when the fixture declares a post-verdict
  event; most runs re-verify an unchanged world (visible in the case-C trace), case D is where
  it bites.
- **`examples/T08-S5Q2/`: `M4-polarity-flip` replaced by `M4-blanket-deny`** — every gate
  satisfied yet the action still refused; the clean baseline (case C) kills it. The old
  polarity-flip mutant also flipped the exit code without inverting `repair_applied` (an
  internally inconsistent mutant); it is removed, not patched.
- **README/code agreement gate (S1)**: the S5-Qregister selftest parses
  `examples/S5-Qregister/README.md` and fails if the crosswalk table or the mutant
  "killed by" columns drift from `CROSSWALK_ROWS` / `MUTANT_KILLERS`.
- **SHIPPED expectations in the fixture specs (S4)**: the shipped triples (guard, action,
  target) are recorded per branch in `examples/S5-Qregister/fixture_spec.json`
  (`expected_action`, `expected_target_changed`) and the shipped after-implementation pairs in
  `examples/T08-S5Q2/fixture_spec.json` (`shipped_after`); both are asserted at startup.

### Fixed

- **The canonical tag did not pass the check its own README invites.** `v0.1.0` was tagged at
  the commit that added the release-consistency gate, and that commit did not regenerate
  `manifest.sha256` — so on `v0.1.0`, `python tools/make-manifest.py --check` reports one file
  modified (`.github/workflows/gates.yml`) and one file not listed
  (`tools/verify_release_consistency.py`), while the same command passes on `main`. Three
  independent gaps made it invisible: the gate did not look at the manifest, the tag triggered
  no CI run, and the gate's own tag-resolution step silently skipped (below). A corrected
  release is tagged `v0.1.1`. The `failures/` and `docs/` trees are byte-identical between
  `v0.1.0` and `v0.1.1`, so every entry id, title and `as of` date still resolves — the defect
  is in the manifest layer, not the cited layer.

- **`tools/verify_release_consistency.py` now covers the content manifest.** It previously
  checked only that the documents agreed with each other; it had no view of the documents
  against the tree. It now delegates to `make-manifest.py --check` rather than re-implementing
  hashing, so the manifest rules keep exactly one implementation. The consequence of the old
  shape, on tag `v0.1.0`: `make-manifest.py --check` reported FAIL while this gate reported
  "✅ 一致" — two integrity checkers disagreeing about the same object.

- **The remote-tag half of gate 6 silently skipped on every CI run.** The step shells out to
  `gh api`; `GH_TOKEN` was never set, so `gh` was unauthenticated on the runner, the lookup
  failed, the script printed "⚠ 远程 tag 校验跳过" and then still reported "✅ 一致" and exited
  0. The step whose whole purpose is to resolve the anchor against the real tag object had
  never executed. A canonical ref that cannot be resolved is now a failure rather than a skip,
  and the workflow supplies the token. This is the catalogue's own subject — a check that could
  not run, recorded as a check that passed — found inside the gate written to catch it.

- **`tools/verify_release_consistency.py`** — an escaped backtick inside a non-raw docstring
  raised `SyntaxWarning: invalid escape sequence` on Python 3.12, visible in the CI log of the
  `v0.1.0`-era runs. Under `-W error` that form is a hard failure. The docstring is raw now.

- **`.github/workflows/gates.yml`** — version tags matching `v*` now trigger the workflow
  (previously the tagged commit was the one commit no gate ran on); `GH_TOKEN` is supplied to
  both jobs; the step labels read `1/8 … 8/8` instead of `1/7 … 6/7, 7/8, 8/8` against a header
  that already claimed eight gates; and a fourth negative control (D) puts the same one-byte
  drift through gate 6, requires it to fail, then restores the tree and requires it to pass
  again — because coverage that is never shown to be able to fail is coverage by assertion.

- **`tools/verify_release_consistency.py` dereferences annotated tags** before reading the
  tagged README. This repository cuts lightweight tags (`v0.1.0` is one), so the behaviour is
  unchanged today; an annotated tag would otherwise have resolved to a tag object rather than a
  commit and produced a false failure on a correct release.

### Changed

- **The release check no longer names a release version.** The literal `--ref v0.1.0` appeared
  in `.github/workflows/gates.yml`, in `.githooks/pre-commit`, and as the script's own default.
  A hard-coded version inside the release check is a second source of truth that goes stale the
  moment the anchor moves, which is the defect class the check exists to catch. The gate now
  derives the ref from `README.md`.

  This was applied to the verification path only. `.github/workflows/zenodo-deposit.yml` still
  hard-codes `version: 0.1.0` and an `sfc_v0.1.0.tar.gz` filename in the deposit it would
  create. That path performs an irreversible publish, it cannot be exercised without actually
  minting a DOI, and an untested edit to an irreversible path is the thing this catalogue is
  about — so it is recorded in `REVIEW.md` rather than edited blind.

- **`examples/S5-Qregister/simulation.py`** no longer branches on the fixture name; every
  profile takes one `Observation` and decides from observables only.

- **`index.md`** — a landing page for the documentation site, so that the repository's
  `homepage` resolves to a page instead of a 404. The alternative was to leave the field
  pointing at nothing, which is the shape this catalog documents. It is a landing page, not a
  second source of truth: where it and `README.md` disagree, `README.md` is right.

  It is listed here rather than under `0.1.0` because `v0.1.0` is a tag that already exists and
  does not contain this file. A changelog entry naming a file as part of a release that does not
  contain it is the same defect class as the rest of this file's history.

- **`REVIEW.md`** — the review log for this catalog: what was reviewed, the review mechanisms, the release-pipeline defect the review surfaced (and the gate that now prevents its return), and an honest positioning against MedXpertQA on the verifier-side axis. Added on `main` after `v0.1.0`; the canonical citation is the immutable release tag named in `README.md`.

- Landing-page rework: value proposition and badges now lead; the license notice is collapsed into a `<details>` block (rights text preserved verbatim, one-line notice stays visible); Jekyll theme enabled for GitHub Pages via `_config.yml`.

- **`examples/T08-S5Q2/` (v4)** — four contrasting cases on the UC-21 S5-Q2 requirement (T08 / AWS Step Functions-RDS profile): omitted condition (SF-006 coverage gap), declared condition whose value changes between queue and use (the decisive temporal case), clean baseline (over-blocking detector), and a world change *after* the verdict but *before* the action (the check-then-act window: the controlled implementation re-verifies at the action boundary). The reference condition set is derived from `fixture_spec.json` and asserted against the code at startup. **v4 adds a mutation suite** — four broken-validator mutants that the selftest must kill (who-tests-the-tester, mechanically), plus assertions that FAIL diagnostics name the offending condition — and CI gains gate 7 running the selftest on every push; the pre-commit hook now mirrors CI gate-for-gate (the two lists had drifted: CI six, hook five).

## [0.1.0] — 2026-09-29

First release. The version number in `CITATION.cff` and in this file referred to no commit until
this tag existed — a claim without an anchor, which is the shape this catalog documents. The two
sections that used to sit apart (`[Unreleased]` and a dated `0.1.0`) described one unpublished
state, so they are one section here.

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
- **`docs/building-this-catalog.md`**: the eleven defects found in this repository's own
  tooling while building it, with the control that found each one. Defect 10 is a comment
  asserting a regex token was load-bearing; testing the claim showed it was not. Defect 11
  is a safeguard described in the prose and implemented nowhere.
- **`.github/workflows/gates.yml`** — the five gates run in CI, on every push and pull
  request, on Python 3.9 (the floor this repository claims) and 3.12. `.githooks/pre-commit`
  remains the specification and the workflow is its echo; if one list changes, the other is
  wrong. It also carries the negative control the other files promised — one byte is appended
  to an entry and `make-manifest.py --check` is *required* to fail, then the tree is restored
  and *required* to pass again. The second half is the half usually left out: a gate that
  cannot fail and a gate that is stuck red look identical from the outside, and only the
  restored run tells them apart.
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

- **Licence notice made consistent: the prose content is all rights reserved.**
  `LICENSE-CONTENT` described the content as CC BY 4.0 while the rights notice at the
  top of `README.md` reserved all rights. A file whose two ends disagree about its own
  licence is the same shape as the failures this catalog documents, so the badges, the
  page footer, `CITATION.cff`, `.zenodo.json`, `SUPPORT.md`, `docs/where-to-find-us.md`,
  `docs/question-map.md` and `llms.txt` now say what the notice says. Code stays MIT,
  and citation with attribution stays permitted. **A licence already granted for copies
  obtained earlier is not affected** — a licence is not revoked; this governs copies
  obtained from here on.
- `docs/where-to-find-us.md` gains an `assayance` row in both the human and the
  channel tables.

### Fixed

- **Three files stated that CI was watching, and no CI existed.** `README.md` withheld a
  badge on purpose, with a comment explaining that a badge claiming a validation run that
  does not exist "would be exactly the silent pass this repo documents" — and, eleven lines
  further down, "CI enforces this, and it also holds the check to the catalog's own
  standard". `CONTRIBUTING.md` promised that a pull request adding an entry without updating
  all six index files "will fail CI". `AGENTS.md` rule 7 said "CI runs `--check` and will fail
  otherwise". `.github/workflows/` did not exist. The reasoning behind the withheld badge was
  right and its conclusion was wrong: the honest alternative to a false badge is a workflow,
  not a note about a workflow. The badge now points at the workflow that exists.
- **`README.md`'s contact line tripped `--scan-leaks`.** The address is an
  address-shaped string and the scan is right to flag that shape. It was found by
  the first CI run, which is the point of having one: the change that added the
  licence notice reported that the gates had passed, and the gate that had not
  been run was the one that fires. The line now carries `<!-- leak-scan: allow -->`,
  so the allowance is counted and printed rather than silent.
- **`CHANGELOG.md` recorded the move away from CC BY 4.0 in one section while another
  section of the same file still declared CC BY 4.0**, and carried two `### Changed`
  headings inside one release block. Same class as the licence split: a document whose two
  ends disagree, and a reader who stops at either end is misled.

### Notes

- License split: MIT for the code in `tools/`, `.githooks/` and `.github/`; the prose content
  (this file, `README.md`, `llms.txt`, `failures/`, `docs/`) is all rights reserved, with
  citation under attribution permitted. See `LICENSE` and `LICENSE-CONTENT`.
- No entry claims conformance with any standard.
- Changing any content file requires regenerating the manifest in the same commit. The
  friction is deliberate: a manifest permitted to drift is worse than none, because it is
  read as evidence.
- **The tooling was developed by feeding it its own medicine.** Running the
  selftest and a reverse-control suite against the tools found eleven defects in
  the tools themselves. All are fixed; the record is kept in
  [`docs/building-this-catalog.md`](docs/building-this-catalog.md) because a
  catalogue about silent passes that was itself silently passing would be worth
  nothing.

## Unreleased (2026-10-01)

### Added

- **`examples/S5-Qregister/`** -- executable crosswalk of the UC-21 scenario gate
  register (Annex S5 sections 7-10, Q0-Q6) to the four-case negative-control
  matrix of `examples/T08-S5Q2/`. Three implementation profiles (I0 ordinary /
  I1 defended / I2 complete) produce per-gate traces over four fixture
  branches (continuity, supersession, act-window, ambiguity); the I0 and I1
  traces reproduce the published capability-absent and ineffective-control
  diagnostics. Four gate-layer mutants (supersession drop, cache read,
  binding drop, blanket deny) are each killed on exactly their crosswalk
  branches. Spec/code agreement is asserted at startup from
  `fixture_spec.json`. Model result, not an AWS product execution; product
  anchors verified against AWS documentation (Step Functions input snapshot,
  StopExecution, DynamoDB conditional writes) are recorded in the example
  README.
