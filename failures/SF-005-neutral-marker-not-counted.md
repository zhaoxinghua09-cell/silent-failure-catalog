# SF-005 · Neutral marker not counted

**Status**: `stable` ｜ **Family**: B · Uncounted Absence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** "Expected but absent" is reported as a neutral note, so it never increments the failure counter — and the gate prints PASS.

## Symptom

A checker tracks several conditions. Most outcomes drive a counter: success increments `ok`, failure increments `fail`. One outcome — **required item missing** — is rendered as a *neutral* marker instead: a `⚪`, a `note`, a `warn`, a `skip`, a grey row.

The visible report is honest. It says, in plain text, that the item is missing. The **exit code** says PASS.

```
✅ 35 一致   🔴 0 不一致   🟡 0 未核对
⚪  ORCID / work-a  登记表记：未挂（未声明应挂）
⚪  ORCID / work-b  登记表记：未挂（未声明应挂）
...
→ exit 0 — PASS
```

Four required items are missing. `fail = 0`. The gate reports success.

## Why it is silent

This is the **purest** member of the catalog. The failure mode is *nothing at all*:

- no exception
- no non-zero exit
- no drift or anomaly
- no log at the error level

And crucially, the report is **not lying**. Every line is true. The defect is in a different place: `PASS` has two possible meanings — *"everything I declared is consistent"* and *"everything is fine"* — and the code implements the first while every reader understands the second.

The neutral marker is where the semantic gap is: `⚪` means "I looked and there is nothing here". The author intended "not applicable". The reader receives "checked, fine".

**Why it is not caught by review:** the diff looks like a reporting improvement. Adding a `⚪` category reads as *more* thoroughness, not less. The bug is created by the act of making the output nicer.

## Minimal reproduction

```python
ok = fail = 0
for item in REQUIRED_ITEMS:
    live = lookup(item)
    if live:
        ok += 1
    else:
        print(f"⚪  {item}: not present")     # ← neutral: increments nothing
        # no counter touched

print(f"✅ {ok}   🔴 {fail}")
raise SystemExit(1 if fail else 0)              # fail == 0 → exit 0
```

Observed: `✅ 0  🔴 0` → exit **0** — even with every required item absent.
Expected after fix: `n required items absent` → exit **1**

## Self-check

Count the checker's output states and ask, for each, whether it can produce a non-zero exit.

```
states            = {ok, fail, neutral, skip, error, not-run}
states→non-zero   = {fail, error, not-run}
leftover          = {neutral, skip}      ← each one is a silent pass
```

Then: **declare what should be present.** A checker that only verifies what it can find will always pass. Add an expectation list, and treat unmet expectations as failures.

## Fix

Two changes, both required.

```python
if not live:
    if item.expect_present:                    # 1) declare the expectation
        report.add(item.key, "required but absent", "🔴 FAIL",
                   expected=">=1", observed="0",
                   note="absence of a required item is a failure, not a note")
        fail += 1                              # 2) missing enters the exit code
    else:
        report.add(item.key, "not declared as required", "⚪")
```

and the exit condition stays `1 if fail else 0` — now meaningful, because `fail` can be incremented by absence.

**The general rule to carry away:**

> **Missing must enter the exit code.**
> Any neutral representation of a required item's absence — a note, a `⚪`, a `warn`, a `skip`, a log line — is a silent pass in waiting.

**Corollary about honest reporting:** if the gate prints `PASS`, that word must not be reachable while any declared expectation is unmet. Rename the outcome if the scope is narrower than it sounds (`CONSISTENT` vs `PASS`), or widen the check. Do not leave a word whose meaning is broader than what was verified.

| Negative control | Expected result |
|---|---|
| Remove one required item from the source | exits **non-zero**, reporting that item by name |
| Remove **all** required items | exits **non-zero**; never `✅ 0 🔴 0` |
| Restore the items | exits 0 — proving the check now discriminates |

## Related

- `SF-006` — the neighbouring hole: an item that is neither present nor declared is invisible in both directions
- `SF-007` — the single-field version of this pattern
- `SF-011` — what this becomes once the neutral marker is joined by an exemption clause
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § B — the taxonomy's Rule 1 is derived from this entry

---

## 中文要点

- **一句话**：**"该有的没有"**被写成中性标记（`⚪`／note／warn／skip），**不进任何计数器** → `fail = 0` → 打印 **PASS**。
- **为什么会静默**：报告**没有一个字是假的**，全都属实。缺陷在别处：`PASS` 有**两个含义**——"我声明过的东西都一致"与"一切正常"——代码实现的是前者，所有读者理解的是后者。
- **为什么代码评审抓不到**：这个改动看起来是**报告优化**（多了一个类别 = 更细致），Bug 是"把输出做得更漂亮"这个动作本身创造的。
- **怎么自查**：列出检查器的全部输出状态，逐个问"它能不能导致非零退出"。剩下的（`neutral` / `skip`）每一条都是一个静默通过。
- **修法要点**：① **显式声明期望**（不声明 = 不检查 = 空着也 PASS）；② **缺失必须进退出码**。
- **反向对照**：删掉一个必需项 → 必须指名报错并非零退出；全部删掉 → 仍须非零退出，绝不能出现 `✅ 0 🔴 0`。
