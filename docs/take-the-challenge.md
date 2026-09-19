# Take the challenge

**as of 2026-09-19**

You have just read that a check can pass while checking nothing. The fastest way to make that real is to produce one — and then to prove you did.

Three tiers, increasing effort. Each states its outcome up front, so you can tell whether the effort is worth it **before** you spend it.

---

## Tier 1 · Bring us a gate that cannot fail — about 5 minutes

```bash
git clone https://github.com/zhaoxinghua09-cell/silent-failure-catalog.git
cd silent-failure-catalog
python tools/gate-lint.py path/to/a/validator/you/already/trust.py
```

Most people have a script like this: a pre-commit hook, a data-quality check, a compliance checklist runner, a CI job that prints `OK`. It has never failed. **That is the interesting part.**

**You win if** the linter stays silent *and* you can show the script exiting `0` on input it was written to reject. That is a **false negative**, and it is the most valuable report this project can receive.

What happens to it:

| Outcome | What ships |
|---|---|
| The shape generalises | A new rule, plus a `bad` sample it must flag and a `good` sample it must not — in the same commit. You are credited in `CHANGELOG.md` by handle. |
| It is genuinely one-off | A new catalog entry, or a documented known false negative in that rule's docstring. |
| It was our bug | Fixed, credited, and the fix gets its own negative control. |

**Before you report:** strip anything client-specific. See [`CONTRIBUTING.md`](../CONTRIBUTING.md) § De-identification. A report that leaks an employer's internals gets closed rather than quietly redacted.

---

## Tier 2 · Break the linter itself — about 30 minutes

[`tools/gate-lint.py`](../tools/gate-lint.py) ships six rules, `SFL-001` … `SFL-006`. Each declares its confidence level and its known false positives **in the source**, not in a wiki page. Two ways to win:

| Attack | You win when |
|---|---|
| **False negative** | A file contains a real silent pass, and the linter says nothing |
| **False positive** | A file is genuinely correct, and the linter fires |

**A false positive counts as much as a false negative.** That is not politeness — it is the same claim. A linter that cries wolf gets switched off, and a switched-off linter is a silent pass with extra steps. Noise is a correctness bug here, not a UX complaint.

Both samples live in [`tools/samples/`](../tools/samples/): `bad/` holds what must be flagged, `good/` holds what must not. `python tools/gate-lint.py --selftest` runs them. A rule whose two samples do not both behave is not merged.

Rules of engagement:

- **Reproductions, not arguments.** A file we can run beats a paragraph explaining why the heuristic is wrong.
- **Do not hand-edit `manifest.sha256`.** Run `python tools/make-manifest.py`.
- **One failure mode per report.** Two in one issue is two issues.

---

## Tier 3 · Make a scoreboard lie — then make it unable to

Tier 1 and Tier 2 are the same skill as Tier 3, pointed at code instead of at a system that *claims* to be accountable.

We also run a scored event on exactly this problem: an automated system has to **demonstrate** that its work can be traced, bounded and audited — scored mechanically, not by a judge's impression. Entry is designed to cost one API call, from a human with `curl` or from an agent over MCP.

You will find it in the Channels table of [`docs/where-to-find-us.md`](where-to-find-us.md). It is linked from there as a **repository, not an API host**, on purpose: that hostname has already moved once, so a page that pinned it would have become a silent failure of exactly the kind this catalog documents.

**If you can make that scoreboard report success while nothing was verified, we want to know before someone else finds out.** Report it the way you would report a security issue — see [`SECURITY.md`](../SECURITY.md). Do not submit a bypass as a competition entry.

---

## What we will not do with your report

- **Turn it into an accusation.** Vendor-specific reports are rewritten as the pattern the tool demonstrated. Naming the tool is not the point; naming the failure is.
- **Ask you to sign anything.** No NDA, and no contributor agreement beyond the repository licence.
- **Sit on a confirmed false negative.** If it is real and it generalises, it becomes a rule.
- **Close it as "working as intended" without naming the line and file that makes it intended.** That sentence is a silent pass written in prose.

## Why we ask at all

The premise of this catalog is that a check nobody has ever seen fail is not evidence of anything. **That applies to the catalog itself.** Every rule here ships a sample it must flag, and the integrity manifest has a CI step that corrupts a file on purpose and *requires* the check to notice.

Everything above is an invitation to attack that claim. If it holds, the catalog gets stronger. If it does not, we would rather hear it from you than from a stranger's post.
