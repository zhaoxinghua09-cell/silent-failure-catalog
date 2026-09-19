# SF-004 · Sentinel value on failure

**Status**: `stable` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A function returns `0.0` / `""` / `[]` when it fails, so a crash becomes indistinguishable from a bad result.

## Symptom

```python
def f1_score(preds, labels) -> float:
    try:
        ...
    except Exception:
        return 0.0            # ← the bug
```

The evaluation script now reports `F1 = 0.0`. That number is **ambiguous**: it is what you would see if the model performed terribly, and also what you would see if the code threw at line 47. The two situations require completely different responses and are indistinguishable in the report.

Common sentinels and their collisions:

| Sentinel | Collides with |
|---|---|
| `0.0` | a genuinely zero metric |
| `""` | an empty-field case (see `SF-007`) |
| `[]` | "no results found" — a legitimate, meaningful outcome |
| `-1` | any legitimate negative count that is not supposed to occur, until it does |
| `None` | "not computed yet", "not applicable", "failed" — three different states |

## Why it is silent

*A signal that can prove the claim* is missing: the return channel carries a **plausible value** instead of a distinguishable state.

The failure is not that the error was lost — the error was **laundered into data**. Downstream consumers see a valid value, aggregate it, plot it, and reason about it. The error has become a finding.

This is the most expensive of the Family A entries, because it does not merely hide a problem — it **manufactures a false observation** that other people then act on.

## Minimal reproduction

```python
def score(preds, labels):
    try:
        assert len(preds) == len(labels)
        return sum(p == l for p, l in zip(preds, labels)) / len(preds)
    except Exception:
        return 0.0

print(score([1, 0], [1, 0, 1]))    # length mismatch — a bug
# → 0.0   indistinguishable from "the model got everything wrong"
```

Observed: `0.0` — Expected after fix: an exception, or a structured `{ok: false, reason: ...}`

## Self-check

For each function that returns a value in a `try`/`except`:

1. Enumerate every sentinel it can return, and every legitimate value it can return.
2. If the two sets intersect, you have this bug.
3. Grep for `except` blocks containing `return` — each is a candidate.

A useful sharper question: **"if this function fails, what will the report say, and is that distinguishable from a real result?"**

## Fix

Raise. Let the failure be a failure.

```python
def f1_score(preds, labels) -> float:
    if len(preds) != len(labels):
        raise ValueError(f"length mismatch: {len(preds)} vs {len(labels)}")
    if not preds:
        raise ValueError("empty input — cannot compute a metric")
    ...
```

Where the caller genuinely needs a value back, return an **explicitly typed** outcome rather than an in-band sentinel:

```python
@dataclass
class Outcome:
    ok: bool
    value: float | None
    reason: str | None
```

and make the aggregation fail on any `ok=False`.

**Note for metric code specifically:** a metric function that returns `0.0` on error means every evaluation table in the project silently mixes *"the model is bad"* with *"this code is broken"*. Refuse both: raise on bad input, and assert non-empty input.

| Negative control | Expected result |
|---|---|
| Pass inputs of mismatched length | raises `ValueError`, run **aborts**; no `0.0` is ever produced |
| Pass an empty input list | raises; never reports a metric for zero records |

## Related

- `SF-003` — the same erasure via `pass` instead of a sentinel
- `SF-007` — the downstream consumer's half of this problem: an empty value that breaks nothing
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § A

---

## 中文要点

- **一句话**：出错时返回 `0.0`／`""`／`[]`，于是"代码崩了"和"结果很差"变得**无法区分**。
- **为什么会静默**：错误没有被丢弃，而是被**洗成了数据** —— 下游看到的是一个合法数值，会聚合、画图、据此下结论。这是 A 族里最贵的一条，因为它不只是掩盖问题，而是**伪造了一个观测**。
- **怎么自查**：列出该函数的哨兵返回值集合与合法返回值集合，二者若相交即中招；grep `except` 块里的 `return`。
- **修法要点**：直接 `raise`；确需返回值时用显式的 `Outcome(ok=..., value=..., reason=...)`，聚合适配器对 `ok=False` 一律失败。
- **反向对照**：传长度不匹配的输入 → 必须抛异常中止，**绝不产出 0.0**。
