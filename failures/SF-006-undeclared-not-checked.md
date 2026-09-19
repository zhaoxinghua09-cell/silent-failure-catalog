# SF-006 · Undeclared means unchecked

**Status**: `stable` ｜ **Family**: B · Uncounted Absence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** The validator checks exactly what the registry declares, so anything the registry forgot to declare is never checked — and never missed.

## Symptom

A validator is **registry-driven**: it iterates over a declaration file and verifies each declared item against reality. It is exhaustive and correct *with respect to the registry*.

```
checked 47 items — all consistent
```

The 47 is the count of **declared** items, not the count of items that exist. If the registry omits an item — a new artifact nobody registered, a category that was never added — the validator will never look at it, never compare it, and never report it.

The registry's **coverage** is the actual input, and nothing verifies it.

## Why it is silent

There is no error state, because from the check's point of view nothing is wrong: every declared item is consistent. The uncovered item is outside the check's **frame**, and a check cannot report on what is outside its frame.

This is subtly worse than `SF-005`. In SF-005 the item is *missing* and mis-reported as neutral. Here the item is *present in reality* and simply not in the list — so there is no row, no note, no evidence that anything was skipped.

**The design is comprehensible and, in isolation, defensible.** Iterating a curated registry is how you avoid false positives. The trap is that "curated" quietly became "authoritative", and no process keeps the registry complete.

## Minimal reproduction

```python
# registry.toml declares 3 items; reality has 4
declared = load_registry()          # ["a", "b", "c"]
for key in declared:
    assert verify(key)              # all pass
print(f"checked {len(declared)} — all consistent")
raise SystemExit(0)
```

`d` exists, is published, and is unverifiable by this gate. The gate reports a clean bill of health.

Observed: `checked 3 — all consistent` (4 exist) — Expected after fix: `1 item exists outside the registry` → exit 1

## Self-check

Ask two questions, in this order:

1. **Reverse coverage.** Enumerate what *exists* (list the published artifacts, the deployed services, the rows in the source of truth) and diff it against what is *declared*. Any existence not in the registry is unchecked.
2. **Who owns registry completeness?** If the answer is "whoever remembers", coverage will decay. If the answer is "an assertion in the gate", it will not.

A practical technique: the registry should be **derived** where possible — generated from the same source that produces the artifacts — rather than hand-maintained alongside them.

## Fix

Add a reverse-coverage assertion: compare the declared set against the discovered set, and treat the difference as failure in **both** directions.

```python
declared  = set(load_registry())
discovered = set(enumerate_existing())

undeclared = discovered - declared
if undeclared:
    raise SystemExit(f"FATAL: {len(undeclared)} items exist but are not declared: {sorted(undeclared)}")

stale = declared - discovered
if stale:
    raise SystemExit(f"FATAL: {len(stale)} declared items do not exist: {sorted(stale)}")
```

Then the frame is closed: nothing can exist outside it without failing the gate.

**Where derivation is not possible**, the minimum viable control is a **total count assertion** — if the registry is expected to have N entries, assert N. It is crude and it catches the common case (an item added without registering).

| Negative control | Expected result |
|---|---|
| Create a new artifact without declaring it | gate exits **non-zero**, naming it as undeclared |
| Delete a declared item from reality | gate exits **non-zero**, naming it as stale |
| Add and declare symmetrically | gate exits 0 |

## Related

- `SF-005` — the item is declared and mis-reported; here it is not declared at all
- `SF-007` — the field-level instance of the same frame problem
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § B

---

## 中文要点

- **一句话**：校验器**只核对登记表里声明过的东西** → 登记表漏掉的条目，永远不会被检查、也永远不会被发现。
- **为什么会静默**：它对自己的框架而言是完全正确的（声明的都一致）。漏洞在**框架的覆盖率**上，而检查器无法报告框架之外的东西。比 SF-005 更隐蔽：那里至少还有一行中性记录，这里**连行都没有**。
- **怎么自查**：**反向覆盖**——枚举"实际存在的东西"，与"已声明的"做差集。差集非空 = 有东西在门外。
- **进一步问一句**：登记表的完整性由谁负责？如果答案是"谁记得谁来"，覆盖率必然衰减。
- **修法要点**：加**双向**断言（未声明但存在 → 失败；已声明但不存在 → 失败）；能派生就派生的登记表（从产出源自动生成），比手工维护可靠。
- **反向对照**：新建一个不登记的产物 → 必须指名报错并非零退出。
