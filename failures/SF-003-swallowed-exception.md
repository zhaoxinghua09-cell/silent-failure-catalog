# SF-003 · Swallowed exception

**Status**: `stable` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A `try/except` added "for robustness" deletes the failure signal.

## Symptom

A check wraps its own work in an exception handler that discards the exception. The check then reports success — having verified nothing.

```python
try:
    result = verify_all(records)
    assert result.ok
except Exception:
    pass          # "for robustness"
```

Two variants that look different and are the same bug:

```python
# variant B — "resilient" collector
for r in records:
    try:
        results.append(check(r))
    except Exception:
        pass                       # the record vanishes; the run stays green
```

In variant B the failure is not just hidden — the **denominator changes**. A run that checked 3 of 100 records reports exactly what a run that checked 100 of 100 reports.

## Why it is silent

*A way for "absent" to count* is missing, and the exception channel — which would otherwise be loud — has been wired into silence.

This pattern is almost always introduced with good intent, which is why it survives review: "don't let one bad record crash the whole batch". The correct form of that intent is *"don't abort the batch, but record the bad record and fail at the end"* — not *"don't abort, and forget"*.

Agents introduce it readily: prompted to make a pipeline resilient, the shortest edit is a bare `except`. It is worth putting the rule in the project's agent-instruction file.

## Minimal reproduction

```python
def check_all(items):
    ok = 0
    for i in items:
        try:
            if validate(i):     # raises on malformed input
                ok += 1
        except Exception:
            pass
    return ok

print(check_all([{"id": 1}, None, None, None]))
# → 1   and the caller sees no indication that 3 items were never examined
```

Observed: `1` — Expected after fix: `1` **plus** a recorded count of 3 unexamined items, and a non-zero exit

## Self-check

1. Grep for `except` blocks whose body is only `pass`, `continue`, `...`, or a log call with no counter increment.
2. Grep for `except Exception` broadly — every one is a candidate.
3. Compare the number of **input** items against the number of items actually examined, and assert equality.

## Fix

Never discard. Either re-raise, or record a counted failure.

```python
failures = []
examined = 0
for i in items:
    try:
        validate(i)
        examined += 1
    except Exception as e:
        failures.append((i, repr(e)))     # recorded, counted, reported

if failures:
    raise SystemExit(f"{len(failures)} items could not be verified: {failures[:3]}")
if examined == 0:
    raise SystemExit("FATAL: nothing was examined")
```

Where a batch genuinely must continue past a bad record, the end-of-run assertion is the part that matters — *failures recorded* must be non-empty → non-zero exit.

`.github`-level enforcement that helps: a `ruff`/`flake8` rule for bare `except: pass`, or a CI grep that fails the build on new occurrences.

| Negative control | Expected result |
|---|---|
| Pass one malformed item | the run reports it and exits **non-zero** |
| Pass only malformed items | exits **non-zero** with "nothing was examined"; never `0 ok` + exit 0 |

## Related

- `SF-002` — the `return` variant of the same "be resilient" intent
- `SF-004` — returning a sentinel instead of raising; same erasure, different mechanism
- `SF-012` — when a failure *is* raised but attributed to the wrong cause
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § A

---

## 中文要点

- **一句话**：为了"健壮"加的 `try/except: pass`，把失败信号直接删掉了。
- **为什么会静默**：异常本是响渠道，被接成了静音；更隐蔽的是**分母被改**——查了 100 条里的 3 条，与查满 100 条报得一模一样。
- **怎么自查**：grep 体里只有 `pass` / `continue` / `...` 的 `except` 块；对比"输入条数"与"实际被检查条数"。
- **修法要点**：不许吞。要么重抛，要么**记录并计数**，最后按计数非零退出；并断言 `examined > 0`。
- **反向对照**：塞一条畸形数据 → 必须被报出且非零退出。
