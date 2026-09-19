# SF-001 · Zero items collected, exit 0

**Status**: `stable` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** The runner executed successfully and collected nothing, which is reported as success.

## Symptom

A test or validation command runs, prints a normal-looking summary, exits 0 — and no test was executed.

The tell is a single line in otherwise healthy output:

```
collected 0 items
no tests ran in 0.03s
```

followed by exit code `0`. Everything downstream reads that as *passed*. Dashboards are green, the agent reports "tests passed", CI allows the merge.

This variant is especially durable: a **path-to-target mapping** (a table, a config file, a glob) pointed at targets that were later renamed, split, or deleted. The command is still syntactically valid, still runs, still succeeds. The mapping is never validated, because nothing asserts that the targets exist.

## Why it is silent

A process that ran nothing is **observationally identical** to a process that ran everything successfully, as long as success is a boolean derived from the exit code.

- *Something to check* — present (a mapping, a config)
- *A way for "absent" to count* — **missing**: an empty collection is treated as "nothing failed"
- *A signal that can prove the claim* — missing: the exit code cannot distinguish "0 failures" from "0 items"

The more automation sits between the operator and the run, the longer this survives. An agent reading stdout (rather than the exit code, or a result count) will report honestly and wrongly: *"tests passed"* is a true statement about the output and a false statement about the system.

## Minimal reproduction

```python
# gate.py — a plausible-looking validator with the empty-set hole
import json, pathlib

TARGETS = json.loads(pathlib.Path("targets.json").read_text())  # may be stale

failures = 0
for t in TARGETS:
    if not pathlib.Path(t).exists():
        print(f"warn: {t} not found, skipping")
        continue
    if not verify(t):
        failures += 1

print(f"checked {len(TARGETS)}, failures={failures}")
raise SystemExit(1 if failures else 0)
```

With `targets.json` = `[]`, or with every target missing, the output is `checked 0, failures=0` and exit **0**.

Observed: `checked 0, failures=0` → exit 0 — Expected after fix: `collected 0 targets` → exit 1

## Self-check

1. Run your suite with an explicitly empty selection (`-k "zzz_no_match"`, `--filter` that matches nothing, an empty target list).
2. If it exits 0, you have this bug.
3. Separately, verify the **mapping itself**: assert every declared target exists before running anything.

## Fix

Make an empty collection a failure, and validate the mapping before use.

```python
# 1) refuse to run over an empty set
if not TARGETS:
    raise SystemExit("FATAL: 0 targets collected — refusing to report success")

# 2) validate declared targets exist, and count their absence as failure
missing = [t for t in TARGETS if not pathlib.Path(t).exists()]
if missing:
    raise SystemExit(f"FATAL: {len(missing)} declared targets missing: {missing}")
```

For test runners, the equivalent is a collected-count assertion:

```bash
# pytest: fail if nothing was collected
pytest --strict-markers -q | tee out.txt
grep -qE "collected [1-9]" out.txt || { echo "FATAL: 0 tests collected"; exit 1; }
```

| Negative control | Expected result |
|---|---|
| Empty the target list / rename one target | exits **non-zero** with `0 targets collected` or `N declared targets missing` |
| Point the runner at a non-existent directory | exits **non-zero**, not `collected 0 items` + exit 0 |

## Related

- `SF-006` — a sibling: the validator only checks decl**ared** items, so a missing declaration is invisible. SF-001 is the empty-set case; SF-006 is the undeclared case.
- `SF-011` — the oracle that decays to unconditional pass
- Established practice: minimum test count guards; the `pytest` collected-count convention
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § A

---

## 中文要点

- **一句话**：命令跑了、也"成功"了，但**一个检查都没执行** —— 空集合被当成了"没有失败"。
- **为什么会静默**：空集合的退出码与"全部通过"完全相同，观测上不可区分。映射表（路径表/配置/glob）指向的目标早已被改名或删除，但没有任何东西断言目标存在。
- **怎么自查**：故意传一个必然匹配不到的选择条件（空目标表、`-k zzz`）。若仍然 exit 0，就中了。
- **修法要点**：**空集合直接判失败**（`0 targets collected` → 非零退出），并在运行前先校验映射表所指目标真实存在；缺失计入失败。
- **反向对照**：清空目标表 / 改名一个目标 → 必须非零退出。
