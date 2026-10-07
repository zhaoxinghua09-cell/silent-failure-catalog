# Silent Failure Catalog

**Validation that passes while nothing is being checked.**

A catalog of fourteen named silent-failure modes across CI gates, test suites, data pipelines
and AI-agent harnesses — each with a minimal reproduction, a self-check, a fix, and a negative
control.

## Start here

| Page | What it is |
|---|---|
| [Start here](docs/start-here.md) | symptom → entry, in one table |
| [Taxonomy](docs/taxonomy.md) | the five families, and the shared root cause |
| [The 14 entries](failures/README.md) | one file each, each with a reproduction and a negative control |
| [Question map](docs/question-map.md) | four levels of search intent, with citable answers |
| [Take the challenge](docs/take-the-challenge.md) | three tiers, up to *break our linter* |
| [Building this catalog](docs/building-this-catalog.md) | the eleven defects found in our own tooling while building it |
| [Where to find us](docs/where-to-find-us.md) | the single page carrying every outbound link |

## Verify a checkout yourself

```
python tools/make-manifest.py --check   # every file against manifest.sha256
python tools/check-catalog.py           # internal consistency
python tools/gate-lint.py --selftest    # the linter against its own samples
```

The same gates run in CI on every push, on Python 3.9 and 3.12, including both negative
controls. The list lives in one place — `.githooks/pre-commit` — and CI mirrors it
gate-for-gate; it is deliberately not counted here.

## Why this file exists

The project's main page is [`README.md`](README.md). This file exists so that the site root
resolves to a page instead of a 404 — the alternative was a `homepage` field pointing at nothing,
which is the failure shape this catalog documents. It is a landing page, not a second source of
truth: where it and `README.md` disagree, `README.md` and the entries are right, and the
disagreement is a defect worth reporting.

---

Code (`tools/`, `.githooks/`, `.github/`) is MIT. The prose content is all rights reserved, with
citation under attribution permitted. See [LICENSE](LICENSE) and
[LICENSE-CONTENT](LICENSE-CONTENT).
