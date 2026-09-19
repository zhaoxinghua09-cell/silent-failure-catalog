# SF-009 · Exposure counted as usage

**Status**: `stable` ｜ **Family**: C · Wrong Evidence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** Content is present in every request, so a search for it returns a large number — which is read as usage.

## Symptom

You measure adoption by counting occurrences of an identifier in a corpus (logs, transcripts, prompts, rendered pages). The count is large. The conclusion is "heavily used".

Then you look at one instance and find that the corpus **contains the entire inventory on every entry**, because a roster, a catalogue, a capability list or a system prompt is emitted with each request.

```
occurrences of item X in logs: 268
actual invocations of item X:    1
```

The factor is not noise — it is the fan-out of whatever ambient container repeats the inventory. 268 ≈ (number of requests) + (number of genuine uses).

## Why it is silent

*A signal that can prove the claim* is missing, and the inflation is **structural rather than statistical**: it comes from the shape of the data, so no amount of averaging removes it. The metric is precise, reproducible and wrong.

This is the same family as `SF-008`, with a different mechanism. SF-008 uses an artifact from the *wrong lifecycle stage*; SF-009 uses text from the *wrong role* — an inventory listing looks identical to a use in a substring search, because both are just the identifier appearing.

A further trap: the measurement is usually taken with a tool that cannot distinguish roles, and the correction requires knowing **which site** emitted the text. Counting is easy; attribution is not — and the count without attribution is the false metric.

## Minimal reproduction

```python
# every request emits the full roster (a system prompt, a catalogue, a menu)
def build_prompt(user_msg, roster):
    return f"Available items: {', '.join(roster)}\n\nUser: {user_msg}"

# audit, later: how often was item X used?
log = read_logs()
hits = sum(1 for entry in log if "item-X" in entry.text)   # ← counts listings
print(f"item-X occurrences: {hits}")
```

Observed: `occurrences: 268` — Expected after correction: `invocations: 1 (268 occurrences were roster listings)`

## Self-check

1. Inspect **one** instance of a hit, not the aggregate. Read the surrounding text and identify which site produced it.
2. Classify the sites into **listing** (the item is named because it is available) and **firing** (the item is named because it was chosen).
3. Count only the firing sites. A pattern that marks the firing site (a tool-call marker, an event id, a distinct log template) is the only usable counter.

**Rule of thumb:** if a metric's value is close to your request count, it is measuring exposure, not usage.

## Fix

Count events at the firing site only, and make the exclusion explicit in the query.

```python
FIRING   = re.compile(r"\[Tool\] tool '(?P<name>[^']+)'")   # fires
LISTING  = re.compile(r"Available items:")                  # ambient inventory

invocations = [m["name"] for line in log
               if not LISTING.search(line)
               for m in [FIRING.search(line)] if m]

usage = collections.Counter(invocations)
print(f"invocations: {sum(usage.values())} ({len(usage)} distinct)")
```

Operational notes that make this stick:

- **Filter at collection time**, not at reporting time. A count that *can* be produced the wrong way eventually will be.
- **Keep both numbers** and their difference visible: `exposure − usage` is itself a useful signal (it measures how much ambient listing the system emits).
- **Never quote the exposure number as adoption** — not in a report, not in a slide, not to a stakeholder. It is not a conservative estimate; it is a structurally inflated one.

| Negative control | Expected result |
|---|---|
| Add a request that does not invoke the item | usage count **unchanged** (exposure rises, usage does not) |
| Invoke the item once | usage count +1 |
| Remove the ambient roster | both counts converge — proving the gap was the inflation |

## Related

- `SF-008` — wrong lifecycle stage; SF-009 is wrong role, same conclusion
- `SF-012` — when a genuine failure is likewise attributed to the wrong site
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § C

---

## 中文要点

- **一句话**：内容**每一次请求都被完整列出**，于是检索命中数很大，被读成了"使用量很大"。
- **为什么会静默**：偏差是**结构性的**而不是统计性的 —— 来自数据形态（每个请求都带花名册／目录／系统提示），所以取平均、扩大样本都去不掉。数字精确、可复现、且是错的。
- **怎么自查**：**只看一条命中**（别看聚合），读它的上下文，判断是哪个站点产生的；把站点分成**列出**（因为可用而被写出）与**触发**（因为被选中而被写出），只数后者。经验法则：**指标值接近请求总数，那就不是使用量，是曝光量。**
- **修法要点**：只在**触发站点**计数；**在采集时过滤**而不是在报表时过滤；两个数字都留着，`曝光 − 使用` 本身就是有用信号。
- **反向对照**：加一次"只列不用"的请求 → 使用量必须不变；真调用一次 → 恰好 +1。
