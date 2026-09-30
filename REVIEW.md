# Review Log — Silent Failure Catalog

> Review / process documentation. **Code: MIT. Content: All Rights Reserved**
> (citation with attribution permitted — see `LICENSE-CONTENT`).
> © 2026 赵兴华 / Steven Zhao·China.

## Why this file exists

This catalog's argument is that *a check which only verifies what it can find will
always pass*. That applies to the catalog's own review process as much as to anyone
else's gates. So the review of this catalog is recorded here as a **log with evidence
and a recorded defect** — not as a sentence saying "reviewed".

This file is the companion to the FG-TIDA submission (`FG-TIDA/use-cases#23`, themes
**#6** / **#7**) and to the prior-art review published to `FG-TIDA/themes#30`.

## What was reviewed

| Item | Where | Status |
|---|---|---|
| 14 silent-failure entries (SF-001 … SF-014) | `failures/` | reviewed; each carries a negative control |
| `tools/gate-lint.py` (static linter, `--selftest`) | `tools/` | reviewed; self-tests |
| `tools/check-catalog.py` (consistency + link discipline) | `tools/` | reviewed; self-tests |
| `tools/make-manifest.py` + `INTEGRITY.md` (content integrity) | `tools/`, root | reviewed |
| Prior-art review (6 one-source-verified threads) | FG-TIDA/themes #30 | published, dated |
| T08 negative-control demo (SF-006 / SF-011 → AWS Step Functions / RDS S5-Q2) | FG-TIDA/use-cases #21 | published, dated |

## The review mechanisms

1. **Document-layer gate (`external-rights-gate`).** Every external-facing document is
   run through a machine gate that checks, among other things:
   - a correct © line (natural-person attribution, *not* a brand);
   - the originality / no-prior-claim ban (no false "first" / "novel" claims);
   - date and DOI anchors that are **verified, not estimated**.
   This gate is real and it fired — an early draft of the method spec was rejected for a
   calendar-day date that had not been verified, and corrected before publication.

2. **Peer / expert review for the FG-TIDA submission.** The prior-art review and the T08
   demo were each taken through the same gate and through manual expert scrutiny before posting.

## The gap the review exposed (and why that proves it was real)

The document-layer gate is necessary but **not sufficient**: it covers *documents*, not
*repository release artifacts*. On 2026-09-30 a cross-check of the published claims
against the actual repository found a three-way inconsistency in the **canonical pin** —
the single reference every citation is supposed to resolve to:

| Source | Stated canonical pin |
|---|---|
| `README.md` | `v0.1.0` @ `e977a04a…` |
| `v0.1.0` git tag (actual object) | `68f1f815583…` (≠ `e977a04a`) |
| `e977a04a` snapshot's own `README.md` | self-referenced `82018d3c…` (a *withdrawn* revision) |

Plus the set digest was written two different ways in two files (`a5b9c7a7` in one,
`c8abdecb` in the other).

None of the document-layer review steps would have caught this, because none of them
inspect the tag object or the manifest against the README. That is the failure class
this catalog documents — *the absence of a check is recorded as the presence of one* —
found in the catalog's own release process, by a check that the catalog's own philosophy
says must exist. So the review did **not** rubber-stamp; it surfaced a genuine defect.

## The fix (and the new gate)

- The `v0.1.0` tag was unified to a single immutable commit
  (`475a877ffd27db9d525196c9de6337efe0625d43`); the withdrawn `82018d3c` is no longer
  reachable as a canonical reference.
- A new repository-level gate, `tools/verify_release_consistency.py`, was added and wired
  as **gate #6** in `.github/workflows/gates.yml`. It asserts: README canonical ==
  INTEGRITY canonical; the set digest is written identically in both; the LICENSE /
  LICENSE-CONTENT rights lines are present; the withdrawn commit is never cited as
  canonical; and the tag object resolves to a snapshot whose own README agrees.
- All published documents (README, method spec, prior-art review) now cite `v0.1.0` as
  the canonical pin.

The gate is not documentation — it runs in CI on every push and pull request, on Python
3.9 and 3.12, and it carries its own negative control (a byte is corrupted on purpose and
the check is required to fail).

## Outcomes

| Result | Evidence |
|---|---|
| 14 entries, each with a named failure, a minimal repro, a fix, and a negative control | `failures/` |
| Linter and checker prove they can fail (self-tests) | `tools/* --selftest` |
| Content integrity verifiable from any checkout | `make-manifest.py --check`, `INTEGRITY.md` |
| Immutable, citable release | tag `v0.1.0`, Zenodo DOI `10.5281/zenodo.23051638` |
| Review surfaced a real release-pipeline defect and it was fixed | this file + gate #6 |

## Positioning vs MedXpertQA (honest comparison)

MedXpertQA (TsinghuaC3I; arXiv 2501.18362; ICML 2025; 4,460 questions across 17
specialties / 11 body systems; MIT; public leaderboard) is an excellent *domain
benchmark*: it measures how accurately models answer expert-level medical questions.
This catalog is a different object — a *verifier-side* catalog of the ways a validation
can pass while checking nothing.

They are not in competition, but on the **verifier-side axis** this catalog is ahead on
four controls the benchmark genre does not provide:

1. **Negative control on every entry.** Each fix must demonstrate the check *can* detect a
   real break — `SF-011 · The always-green oracle` (Status: stable, Family D, Confidence:
   high) is the canonical example. A benchmark reports accuracy; it does not prove its own
   scorer can fail.
2. **A runnable linter for *your* gates.** `gate-lint.py` scans the reader's own CI gates /
   validators for silent-pass patterns — the catalog is also a tool, not only a dataset.
3. **Content integrity + immutable citation.** A SHA-256 manifest over every file, an
   immutable release tag, and a Zenodo DOI let a reader confirm they hold the exact bytes
   cited.
4. **A review process that found a defect in itself.** Documented above — the review is
   evidence-backed, not asserted.

What MedXpertQA has that this catalog does not: a large labelled dataset, a public
leaderboard, and model-accuracy results. Those are the right things for a *benchmark*;
they are out of scope for a *verifier-side catalog*, and we do not claim them.

The ambition is not to "beat" a medical benchmark at its own game, but to be the
reference others cite when they ask *"how do I know my check is not silently passing?"* —
the question MedXpertQA's own multi-round expert review implicitly depends on.

## Residual items (next review)

- [ ] Deepen the stateful-simulation negative-control demo (the T08 demo is static-declarative
      today; a step-execution simulation that proves a verifier can fail would be the next
      axis of "超出").
- [ ] Add a runnable `examples/T08-S5Q2/` to the catalog so the demo is reproducible from the
      repo, not only from the thread.
- [ ] Schedule the next review pass when the catalog reaches v0.2 (post SF-011 helper
      absorption + the five-point roadmap).

## Review log (dated)

| Date | Event | Evidence |
|---|---|---|
| 2026-09-30 | Prior-art review published to FG-TIDA/themes #30 (6 one-source-verified threads) | themes #30 |
| 2026-09-30 | T08 negative-control demo published to FG-TIDA/use-cases #21 | use-cases #21 |
| 2026-09-30 | Cross-check found a 3-way canonical-pin inconsistency; tag unified to `475a877…`; gate #6 (`verify_release_consistency.py`) added | this file, `gates.yml` |
| 2026-09-30 | REVIEW.md (this file) authored and added to `main` | git history |

---

© 2026 赵兴华 / Steven Zhao·China · Code [MIT](LICENSE) · Content [All Rights Reserved](LICENSE-CONTENT)
