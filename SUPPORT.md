# Support

**as of 2026-09-19**

## Read this first

Most questions here already have a written answer. In order of how often they come up:

| Question | Answer is in |
|---|---|
| "Is the thing I'm seeing a silent failure?" | [`docs/taxonomy.md`](docs/taxonomy.md) — match the symptom against the five families |
| "How do I run the linter on my own script?" | [`README.md`](README.md) § Quick start |
| "The linter fired on code I believe is correct." | [`docs/take-the-challenge.md`](docs/take-the-challenge.md) § Tier 2 — a false positive is a bug here, and this is how to report it |
| "Will you accept my incident write-up?" | [`CONTRIBUTING.md`](CONTRIBUTING.md) — an entry needs a reproduction and a negative control |
| "Can I quote this / translate this / put it in a course?" | [`LICENSE-CONTENT`](LICENSE-CONTENT) — quoting with attribution: yes. Translating or republishing: ask first — the content is all rights reserved |
| "Is this compliant with <standard>?" | No, and nothing here claims to be. [`README.md`](README.md) § Scope and non-goals |

If the answer is in there, an issue asking for it will be closed with a link. That is not rudeness — it is the same rule this catalog applies to checks: a question with a written answer is not a support load, it is a **documentation defect**, and the fix belongs in the document.

## Where to ask

| You have | Use |
|---|---|
| A false positive, a false negative or a broken tool | **[Open an issue](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/issues)** — use the matching template |
| A new failure mode with a reproduction | Issue, using the *new failure mode* template |
| An open question, or a "is this one?" triage request | Discussions, if enabled on this repository — otherwise an issue is fine |
| A way to defeat the tooling, or a problem with the CI workflow | **[`SECURITY.md`](SECURITY.md)** — reported privately, not as a public issue |
| Anything about the scored event | See the Channels table in [`docs/where-to-find-us.md`](docs/where-to-find-us.md) |

## What to include

A report is actionable when it contains **a file we can run**. Specifically:

1. the smallest input that reproduces it — under ~20 lines if you can manage it
2. the exact command you ran, and the exact output you got
3. what you expected instead, and why
4. the versions: Python, OS, and the commit hash of this repository

Reports without (1) and (2) usually cannot be reproduced, and an unreproducible report gets closed with a request for the missing pieces rather than guessed at.

## What this project does not offer

- **No support contract, no SLA.** This is a personal project. There is no rotation and no on-call. Expect a first response in days, not hours.
- **No private consulting through the issue tracker**, and no promise to review your internal system. Generalize the case and ask here instead.
- **No de-identification service.** If your report contains an employer's internals, it will be closed. Strip it yourself first — see [`CONTRIBUTING.md`](CONTRIBUTING.md) § De-identification.

## Never paste into an issue

Credentials, tokens, API keys, session cookies, customer data, or an unredacted log from a production system.

A public issue is indexed permanently within minutes. If you have already pasted a secret, **rotate it first** and then ask for the post to be edited — rotation is the only step that actually matters, because the edit does not reach anything that already copied it.
