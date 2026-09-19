# Security Policy

**as of 2026-09-19**

## Scope

This repository ships no service, no daemon and no network code. It is Markdown plus three stdlib-only Python scripts. So "vulnerability" here does not mean a remote exploit. It means **a way to make this project's own guarantees untrue**:

| In scope | Example |
|---|---|
| A rule in `tools/gate-lint.py` that can be defeated **silently** | An input containing a real silent pass, which the linter does not flag |
| A way to make `tools/check-catalog.py` exit `0` on a broken catalog | A missing required section that the validator cannot see |
| A way to make `tools/make-manifest.py --check` pass on modified content | A change that changes bytes but not the recorded digest — for instance, a path that is not covered by the manifest |
| A CI weakness | Something in `.github/workflows/validate.yml` that lets a pull request skip or neuter a gate |
| A leak of sensitive material | Real client data, credentials or personal information in this repository |

The first three are the serious ones. They are not "bugs" in the ordinary sense — they are **counterexamples to the catalog's central claim**, which is why they are handled privately until fixed.

**Out of scope:** the absence of a feature; the linter's documented false positives (those are declared in each rule's docstring and in the output); anything requiring write access to the repository; and any "vulnerability" that consists of running the tools on malicious Python and getting a traceback — the tools read source, they do not execute it.

## How to report

Use GitHub's **[private vulnerability reporting](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/security/advisories/new)** — *Security* tab → *Report a vulnerability*. That channel is visible only to the maintainer.

Please do not open a public issue for the four in-scope cases above. A public issue is the correct place for everything else, including ordinary bugs.

Include, if you can:

1. a minimal input file, or the exact sequence of commands
2. the observed output and the exit code
3. what the tool should have done instead, and why
4. the commit hash you tested

## What happens next

- **A first response is best-effort.** This is a personal project with no on-call rotation. Days, not hours.
- **There is no bug bounty and no payment of any kind.** Do not expect one, and please do not spend effort on the assumption that there is one.
- **Credit is offered by default**, by GitHub handle, in `CHANGELOG.md` and in the fix commit. Say so if you would rather stay anonymous — that is fine and does not change the handling.
- **Disclosure timing is yours to propose.** Once a fix is released, publishing your write-up is welcome, and a link to it will be added to the relevant entry if it generalises.
- **If it is a counterexample to a rule**, the fix ships as a rule change **plus a sample pair** — a `bad` file it must flag and a `good` file it must not — so the counterexample is retired permanently rather than patched around.

## Supported versions

The latest release on `main` is the only supported version. Entries are append-only; a superseded entry stays online marked `deprecated` so citations do not break.

## Never paste into a report

Credentials, tokens, API keys, session cookies, customer data, or an unredacted production log. If a reproduction needs one of those, replace it with a placeholder — and write an address-shaped placeholder **without** an `@` (so `name [at] example.invalid`), because a scanner that fires on placeholders is a scanner people learn to ignore.
