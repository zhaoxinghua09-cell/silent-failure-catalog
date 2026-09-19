# SF-008 · Loading artifact as evidence of use

**Status**: `stable` ｜ **Family**: C · Wrong Evidence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A file written at startup proves *loaded*. It is being read as proof of *used*.

## Symptom

A system writes a marker when it loads something — an install artifact, a lock file, a `.in_use/<id>` sentinel, a cache entry, a "registered" record. An audit later finds the markers present and concludes the thing is in use.

The audit's finding is true about the artifact and false about the world:

```
63/63 packages have an install marker   →  "all 63 are in use"
```

The markers were all written during a single startup, by the same process, at the same time. They prove the loader read a manifest. They cannot prove any item was ever *invoked*.

The real usage number is often an order of magnitude smaller — and finding it requires a different evidence source entirely.

## Why it is silent

*A signal that can prove the claim* is missing: a **lifecycle artifact** is standing in for a **behavioural fact**.

The two are correlated at the top of the funnel (nothing can be used without being loaded) and diverge after it. Any metric built on the loading stage will systematically over-report, and it will over-report **most for exactly the items that were loaded and never used** — the population you most wanted to identify.

The audit is not sloppy. The artifact is real, on disk, countable, and pleasant to query. That is precisely the trap: **the convenient evidence is the wrong evidence.**

## Minimal reproduction

```python
# loader, runs once at startup
for pkg in installed:
    (state_dir / ".in_use" / str(os.getpid())).touch()
    (state_dir / pkg.name / "loaded").touch()

# audit, months later
loaded = [p for p in installed if (state_dir / p.name / "loaded").exists()]
print(f"{len(loaded)}/{len(installed)} in use")
```

Observed: `63/63 in use` — Expected after correction: a usage count derived from invocation events, e.g. `7/63 invoked at least once`

## Self-check

For every metric you report, write down the **claim** and then ask: *could this evidence be true while the claim is false?*

| Evidence | Claim it supports | Claim it does NOT support |
|---|---|---|
| install marker | the package is installed | it is used |
| process started | the service is up | it is serving |
| file written | a write happened | the content is correct |
| request received | traffic arrived | the response was useful |
| item in prompt | the item was available | the item was selected |

If the rightmost column is non-empty, you are reading a proxy. Then find the **event-level** source: a log line with a stable, greppable shape that is emitted at the moment of the behaviour.

For the package case: match invocation events (`tool '<name>'` / `id=<key>`), not existence. Distinguish the sites that merely *list* the items (a roster printed in every request) from the sites that *fire* them — see `SF-009`.

## Fix

Replace lifecycle evidence with event evidence, and state the evidence class in the report.

```python
# only count invocations, and say so
invocations = count_events(pattern=r"\[Tool\] tool '(?P<name>[^']+)'")
usage_rate = len(invocations) / len(installed)

print(f"usage (event-level): {len(invocations)}/{len(installed)} = {usage_rate:.0%}")
print("evidence class: invocation events; load markers intentionally excluded")
```

Two habits that prevent recurrence:

1. **Label the evidence class** in every metric — *load-time*, *request-time*, *invocation-time*. A number without its evidence class will be misread by the next person.
2. **Keep the strongest available source as the authority.** If a behavioural source exists, it wins; the convenience source becomes a secondary signal at best.

| Negative control | Expected result |
|---|---|
| Install an item and never invoke it | usage metric stays **flat** (correctly not counted) |
| Invoke an item once | usage metric increments by exactly 1 |

## Related

- `SF-009` — the sibling failure: presence in a **recurring** artifact inflating a count
- `SF-010` — evidence from the local side standing in for the published side
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § C

---

## 中文要点

- **一句话**：启动时写下的文件只能证明**"被加载过"**，却被读成了**"被使用过"**。
- **为什么会静默**：**生命周期痕迹**冒充了**行为事实**。两者只在漏斗顶端相关（不用就不可能加载），往下就分叉；而且偏差最大的恰好是"加载了但一次没用"的那批 —— 正是你最想识别的人群。陷阱在于：**最方便拿到的证据，恰好是错的证据。**
- **怎么自查**：对每个指标写下它**声称**的结论，然后问："这证据为真时，结论可能为假吗？"会，就是代理指标。
- **修法要点**：换成**事件级**证据（调用发生时打出的日志行），并在报告里**标注证据层级**（加载时 / 请求时 / 调用时）。
- **反向对照**：装一个但一次不调 → 指标不动；调一次 → 恰好 +1。
