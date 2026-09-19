# SF-011 · The always-green oracle

**Status**: `stable` ｜ **Family**: D · Drifting Oracle ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** An exemption clause fires on any match, so the check passes unconditionally — including on the exact input it exists to catch.

## Symptom

The oracle **starts correct** and decays into decoration, usually across several well-intentioned iterations.

A representative history, where each step is a reasonable response to a false positive:

| Iteration | Change | Why it was made | Effect |
|---|---|---|---|
| 1 | sentence-level match | first implementation | correct but noisy |
| 2 | add block-level match | reduce noise | better |
| 3 | **add "if any match, exempt the block"** | false positives on legitimate quoting | **now unconditionally green** |
| 4 | silence the case that "looks fine" | it kept firing | worse |

At iteration 3 the oracle passes when 100% of the content is copied verbatim, because copying is a match, and a match exempts.

```
oracle verdict: PASS    (content: 400-word verbatim reproduction)
```

The check never crashes, never errors, and never becomes suspicious. It reports `PASS` faster than before because it exits on the first match.

## Why it is silent

*An oracle that keeps discriminating* is missing. Two compounding mistakes:

1. **Match ⇒ exempt.** The exemption was meant for *legitimate short quotes*. It is written as *any* match, so it applies to the pathological case as well. The exemption has no lower bound and no upper bound.
2. **The counter-proof was never run.** No one fed the oracle the thing it exists to catch. Had they, the `PASS` on verbatim reproduction would have been obvious in one line.

The second mistake is the generalisable one: **an oracle that has never been seen failing has not been shown to be capable of failing.** This is what "no negative control means no evidence" means in practice.

## Minimal reproduction

```python
def originality_check(article, sources):
    for s in sources:
        if s.excerpt in article:            # 1) any match …
            return "PASS"                   # 2) … exempts everything
    return "REVIEW"

# the pathological input the oracle exists to catch
print(originality_check(verbatim_copy_400_words, sources))
# → PASS
```

Observed: `PASS` on a 400-word verbatim reproduction — Expected after fix: `FAIL`, with the matched span and ratio reported

## Self-check

1. **Countersign test.** Feed the oracle the exact input it was built to reject. If it stays green, stop here — it does not discriminate.
2. **Bound audit.** For each exemption clause, ask: *is there a lower bound? an upper bound? a maximum share?* An exemption with only a lower bound ("if it matches at all, skip") is unbounded above.
3. **Self-test in CI.** Keep the pathological input as a fixture. A rule without a failing fixture is untested.

## Fix

Make the criterion **proportional and bounded**, and ship the counter-example as a test.

```python
def longest_common_run(a, b):
    """Longest run of consecutive matching characters."""
    ...

MAX_RUN_CHARS  = 30        # no single verbatim run beyond this
MAX_MATCH_RATIO = 0.20     # and no more than this share of the document

def originality_check(article, sources):
    worst_run, worst_ratio = 0, 0.0
    for s in sources:
        run = longest_common_run(article, s.text)
        worst_run = max(worst_run, run)
        worst_ratio = max(worst_ratio, run / max(len(article), 1))
    if worst_run > MAX_RUN_CHARS or worst_ratio > MAX_MATCH_RATIO:
        return ("FAIL", worst_run, worst_ratio)
    return ("PASS", worst_run, worst_ratio)
```

Principles:

- **Bound every exemption** — a maximum run length *and* a maximum share. One bound alone is escapable.
- **Exempt per span, not per document.** "This block is a quotation" is checkable; "this document contains a quotation" is not.
- **Report the measured value on PASS.** A passing result that carries no number cannot be distinguished from a passing result produced by a broken oracle.

| Negative control | Expected result |
|---|---|
| Feed a verbatim copy | `FAIL`, reporting run length and ratio |
| Feed a genuinely original text | `PASS`, with a near-zero ratio |
| Feed a text with one legitimate 20-char quote | `PASS` — proves the exemption still works as intended |

## Related

- `SF-003` / `SF-004` — other ways a check loses its power; here it is the *criterion*, not the plumbing
- `SF-012` — an oracle that still fails, but blames the wrong thing
- External: mutation testing — the practice of proving a check can fail
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § D

---

## 中文要点

- **一句话**：一句豁免条件"命中即免"，使检查**无条件通过** —— 连它本来专门要抓的那个输入也照样通过。
- **为什么会静默**：两处叠加。① **命中即豁免**没有上下界（豁免本意是"合法短引用"，写成了"只要命中就免"，于是对病态输入同样生效）；② **从没跑过反证** —— 喂一次它本该抓的东西，一行就能看出问题。**从未被观察到失败的判据，没有被证明过它能失败。**
- **怎么自查**：**反证测试**（喂给它本该拒绝的输入）；**边界审计**（每个豁免子句问：有下界吗？有上界吗？有占比上限吗？）；把病态输入固化成 fixture 进 CI。
- **修法要点**：改成**有比例、有上限**的判据（最长连续匹配字数 + 占全文比例，两者都要）；**按片段豁免而非按文档豁免**；**PASS 也要带测量值**（不带数字的 PASS 与坏判据产出的 PASS 无法区分）。
- **反向对照**：喂逐字照搬 → 必须 FAIL 并报出连长度与占比；喂原创文本 → PASS；喂 20 字合法引用 → 仍 PASS（证明豁免本身还有效）。
