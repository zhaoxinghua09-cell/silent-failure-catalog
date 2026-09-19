# SF-000 · <name the failure mode in ≤ 8 words>

**Status**: `draft` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: high ｜ **as of** YYYY-MM-DD

<!--
Replace SF-000 with the next free number (append-only, never reuse).
Family must be one of:
  A · Vacuous Verification · B · Uncounted Absence · C · Wrong Evidence
  D · Drifting Oracle · E · Process & Environment
Confidence describes how well-supported the pattern is, not how common it is.
Every section below is required. Empty sections fail `check-catalog.py`.
Keep the heading text exactly as written — it is parsed.
-->

> **One line.** What it looks like from the outside, in a single sentence.

## Symptom

What the operator observes. Be specific about the *absence* of signals: which logs are quiet, which statuses stay green, what the UI shows. This is the section a search engine will match on.

## Why it is silent

The mechanism. Explain the missing part from the four-part model — which of *something to check*, *a way for absent to count*, *a signal that can prove the claim*, *an oracle that keeps discriminating* — is absent, and why nothing else in the system notices.

## Minimal reproduction

```python
# Runnable, or explicitly mark the block "# illustrative".
# Keep it under ~15 lines. If it needs more, the entry is too broad.
```

Observed: `<what you see>` — Expected after fix: `<what you should see>`

## Self-check

How a reader determines whether *their* system has this. Give a command, a query, or a two-step manual procedure. If the check is itself silent when it finds nothing, say so.

## Fix

The concrete change. Then, **mandatory**:

| Negative control | Expected result |
|---|---|
| Break `<the guarded thing>` | the check now fails with `<message>` |

A fix without a negative control is not a fix — see `CONTRIBUTING.md`.

## Related

- `SF-nnn` — how it differs
- External: link established practice (mutation testing, negative controls) rather than restating it
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md)

---

## 中文要点

- **一句话**：<用一句话说清这个失败形态>
- **为什么会静默**：<机制>
- **怎么自查**：<最短路径>
- **修法要点**：<关键改动 + 反向对照>
