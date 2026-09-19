# SF-002 · Early return as an implicit skip

**Status**: `stable` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A guard exits the test body instead of reporting a skip — so the test appears to have passed.

## Symptom

A test that is supposed to be conditional silently becomes a no-op.

```python
def test_metric():
    if not torch.cuda.is_available():
        return                      # ← the bug
    result = compute_metric(model, data)
    assert result > 0.5
```

On a CPU-only runner this test **passes**. Test counts stay the same, coverage attribution is unchanged, and the suite is green — indefinitely.

The distinguishing property: a **skipped test is honest and visible**; a test that returns early is invisible and reports as a pass. Skips get counted and displayed. Early returns get nothing.

The same shape appears outside test suites: a validator that `return`s early when its precondition is unmet, leaving the caller to interpret "no output" as "no problem".

## Why it is silent

*Something to check* is present. *A way for "absent" to count* is **missing**: the branch means "this assertion did not run", but the runner records only "no assertion failed".

This is a **proxy** failure nested in an absence failure: `did not fail` is used as a proxy for `passed`, and the two are equal only if the assertion actually ran.

Agents compound it. Asked to "make the test more resilient", a model will often add exactly this guard — it is a locally reasonable edit that removes the failure signal.

## Minimal reproduction

```python
def test_something():
    if not precondition():
        return                        # invisible skip
    assert compute() > 0
```

Run on a machine where `precondition()` is false: the suite is green and the test count is unchanged.

Observed: `1 passed` — Expected after fix: `1 skipped` (visible, counted)

## Self-check

1. Grep your suite for bare `return` statements inside test functions, and for `if not <condition>` guards with no `else`.
2. Compare the reported test count against the number of test functions. Equal counts with unexpected green is the signature.
3. Run the suite in both environments (with and without the precondition met) and diff the skip counts.

## Fix

Convert the silent exit into an explicit skip, or into an outright failure if the precondition is required.

```python
import pytest

def test_metric():
    if not torch.cuda.is_available():
        pytest.skip("requires GPU")          # honest: visible, counted, reported
    result = compute_metric(model, data)
    assert result > 0.5
```

For a validator, the early-return must become a **recorded, counted** outcome:

```python
if not precondition():
    record_failure("precondition unmet — cannot verify")   # counts, affects exit code
    return
```

Also worth enforcing mechanically — these rules fit in a project's agent-instruction file and prevent the next agent run from re-introducing the pattern:

- tests use `pytest.skip(reason=...)`, never a bare `return`
- `try/except` in tests must re-raise or assert; never silently pass

| Negative control | Expected result |
|---|---|
| Force `precondition()` to return `False` | test reports **skipped** (or **failed** if required) — never `passed` |
| Delete the guarded assertion entirely | suite reports a **different** count / a skip; the change is visible |

## Related

- `SF-001` — empty selection; SF-002 is per-test rather than per-run
- `SF-003` — the `except` variant of the same intent ("make it resilient")
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § A

---

## 中文要点

- **一句话**：本该"跳过"的条件分支写成了 `return`，于是测试**看起来通过了**。
- **为什么会静默**：跳过是可见且被计数的；提前 `return` 什么都不留。运行器只记录"没有断言失败"，而断言根本没跑。
- **怎么自查**：grep 测试函数里的裸 `return`；对比"测试函数个数"与"报告的执行条数"；在满足/不满足前提的两种环境下跑一遍，diff 跳过数。
- **修法要点**：改成 `pytest.skip("requires GPU")`（可见、被计数）；校验器里的提前返回必须**落一条计入失败的记录**。
- **反向对照**：强制前提为假 → 必须显示 skipped 或 failed，**绝不能是 passed**。
