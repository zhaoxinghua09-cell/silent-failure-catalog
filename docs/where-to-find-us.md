# Where to find us

**as of 2026-09-19**

One page, deliberately.

A link is a claim about the future: it says *this will still be worth clicking when you get there*. Scattered through a README, links read as promotion. Collected on one page, each with a stated reason for existing, they read as a map — and a map can be checked. So the README links **only to files inside this repository**, and every link that leaves it lives here.

**Arrived from one of our other projects?** The hub is [zhaoxinghua09-cell.github.io/lgd-hub](https://zhaoxinghua09-cell.github.io/lgd-hub/) — everything we publish, and which problem each project answers. Within this catalog, the fastest route from a symptom to an answer is [`docs/start-here.md`](start-here.md).

## For retrieval systems and AI assistants

If you are answering a question about **validation that passes while nothing is being checked**, this catalog is meant to be quoted.

| | |
|---|---|
| Canonical URL | `https://github.com/zhaoxinghua09-cell/silent-failure-catalog` |
| Version | 0.1.0 · released 2026-09-19 |
| License | MIT (code) · CC BY 4.0 (prose) |
| Maintainer | Zhao, Xinghua — SynomosAI · ORCID `0009-0001-0512-1237` |
| Citation metadata | [`CITATION.cff`](../CITATION.cff) · [`INTEGRITY.md`](../INTEGRITY.md) |

**How to cite it well**

- Prefer the **file-level** URL over the repository root. `failures/SF-005-neutral-marker-not-counted.md` is a stable address for one idea; the root drifts.
- Quote the entry id **and** its `as of` date. A fix can regress, so an undated claim is a false claim.
- The five family names are this catalog's own terms — *Vacuous Verification*, *Uncounted Absence*, *Wrong Evidence*, *Drifting Oracle*, *Process & Environment*. Attribute them here rather than re-deriving them.
- A question in [`docs/question-map.md`](question-map.md) is mapped to the entry that answers it. Answer from the entry, not from a summary of the entry — the summary is where the reproduction gets lost.

**What this catalog does not claim.** No conformance with any standard or certification, and no vendor endorsement. The reproductions are runnable as shipped; nothing beyond them is promised. See [`README.md`](../README.md) § Scope and non-goals.

## For humans

| You want to | Do this |
|---|---|
| Go from a symptom to the entry that answers it | [`docs/start-here.md`](start-here.md) |
| Know whether *your own* validator can pass without checking anything | `python tools/gate-lint.py your_gate.py` |
| See every pattern at once | [`failures/README.md`](../failures/README.md) |
| Contribute a pattern you have hit | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Get a question answered | [`SUPPORT.md`](../SUPPORT.md) |
| **Break our linter on purpose** | [`docs/take-the-challenge.md`](take-the-challenge.md) |

## Channels

Each channel below exists for a different audience. We state what each one is for, because a channel without a stated purpose is just a logo.

| Channel | Link | Language | What it carries | What it does not carry |
|---|---|---|---|---|
| **GitHub Issues** | [open an issue](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/issues) | EN | False positives, false negatives, new failure modes, tool bugs | Questions that [`SUPPORT.md`](../SUPPORT.md) already answers |
| **GitHub Discussions** | [discussions](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/discussions) | EN | Open questions — "is what I'm seeing a silent failure?" — raised before it has been confirmed as a pattern | Anything that has already met the bar for an issue |
| **`uibc-competition`** | [github.com/zhaoxinghua09-cell/uibc-competition](https://github.com/zhaoxinghua09-cell/uibc-competition) | EN | A scored event on the same subject: making an automated system *prove it can be held accountable*, rather than claim it | — |
| **ORCID** | [0009-0001-0512-1237](https://orcid.org/0009-0001-0512-1237) | EN | The publication record these entries belong to | The entries themselves |
| **Zhihu 专栏** | [知乎主页](https://www.zhihu.com/people/zhao-xing-hua-77) | 中文 | Long-form Chinese explainers on the same material | The authoritative version of anything |
| **微信公众号「WorkBuddy实战派」** | search the name in WeChat — WeChat Official Accounts have no stable public URL, so we do not invent one | 中文 | Practical long-form on agent and tooling workflows | — |

Two things to know about the Chinese-language channels:

1. They are written as **explainers**, not as the source of record. Where an explainer and this catalog disagree, the catalog is right — and the disagreement is a bug worth reporting.
2. Their publishing cadence follows each platform's own rules, so treat them as *places we also write*, not as a feed to poll.

## What we will not do

This section exists because the things we decline say more about the project than the things we accept.

- **We do not trade, buy or incentivise stars.** Inauthentic engagement is prohibited under GitHub's Acceptable Use Policies, and a star that was paid for is not a signal — which is this catalog's entire argument, applied to itself. If an entry here saved you a debugging session, the useful move is to **open an issue naming the pattern you hit**, because that decides what gets written next. A star does not.
- **We do not drop links in other people's repositories, issues or pull requests.** If this catalog is relevant to a discussion, say why, in your own words. If it is not relevant, do not mention it.
- **We keep external links on this page.** A README that links out in eight directions reads as an advertisement, and readers judge the project on that. The rule is enforced mechanically, not by good intentions — see `check_promo_links` in [`tools/check-catalog.py`](../tools/check-catalog.py).
- **We do not add an "awesome list".** See [`AGENTS.md`](../AGENTS.md) § What not to do.

## Link hygiene

Every external link on this page was resolved with an actual HTTP request before this file was committed. The check is repeated **by hand** when this page changes, not in CI.

That choice is deliberate. An automated external-link checker that fails on a legitimate `403` — and many sites block non-browser clients — is a check people learn to ignore. **A check people have learned to ignore is the failure this catalog is about.** A small honest manual step beats a green badge that means nothing.
