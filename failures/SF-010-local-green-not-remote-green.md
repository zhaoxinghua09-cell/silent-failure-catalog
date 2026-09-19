# SF-010 · Local green is not remote green

**Status**: `stable` ｜ **Family**: C · Wrong Evidence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** Every local gate passes; the published artifact is still inconsistent, because the published artifact is a different object.

## Symptom

A repository has good hygiene. Linters, schema checks, link checks and consistency gates all pass locally and in CI. Then someone reads the published state — via API, on the live site, in the registry — and finds disagreements that have existed for weeks.

```
local gates:  PASS  PASS  PASS
published:    6 inconsistencies, 4 missing attachments, 1 wrong type
```

The local checks were never wrong. They were answering a different question: *"is this working tree internally consistent?"* The question that mattered was *"does the published state match intent?"*

## Why it is silent

The two propositions are conflated, and the local one is cheap to verify while the remote one requires a network read, credentials and a comparison against expectations.

- Local consistency: files vs. a registry, both on disk, fully under your control
- Published consistency: an API's view of an object whose lifecycle you do not fully control

A third factor makes it durable: **the published object has its own state that the local tree cannot see.** Version fields rewritten on deposit, affiliation fields populated from an account profile, types re-mapped by the platform's own rules, visibility defaulted to non-public. None of these appear in a diff, because they were never in a file.

## Minimal reproduction

There is no code reproduction — the reproduction is a comparison.

```bash
# local: passes
python check_local.py && echo GREEN

# published: a different claim (illustrative)
curl -s "https://api.example.org/records/<id>" | jq '{type, visibility, fields: (.metadata | keys)}'
# → type: journal-article   (declared as: working-paper)
# → visibility: limited     (assumed: public)
```

Observed: local `GREEN`, published disagrees on type and visibility — Expected after fix: a gate that reads the live state and fails on the difference

## Self-check

For every external channel — registry, package index, website, profile, store listing — ask:

1. **Is there a check that reads the live state?** (Not "is there a check for the local source of it".)
2. **Does it compare against a declared expectation**, or only print what it finds?
3. **Does it check the fields the platform rewrites** — type, visibility, ordering, derived fields?

Any channel with `no` to the first question is unverified. Any with `no` to the second is `SF-005` waiting to happen.

## Fix

One read-back check per published channel, comparing live state against a declared expectation.

```python
live = fetch_published(record_id)                 # authoritative for the published claim
exp  = registry[record_id]                        # declared expectation

problems = []
if live["visibility"] != exp["required_visibility"]:
    problems.append(f"visibility {live['visibility']} != {exp['required_visibility']}")
if live["type"] != exp["expected_type"]:
    problems.append(f"type {live['type']} != {exp['expected_type']}")
for field in exp["required_fields"]:
    if not live.get(field):
        problems.append(f"required field empty: {field}")

raise SystemExit(1 if problems else 0)
```

Design notes:

- **The expectation must be declared**, not inferred from the live state. Comparing live-against-live is a tautology and always passes.
- **Expectations belong in a registry**, so adding a new published artifact means adding a declaration — and an undeclared artifact is itself detectable (`SF-006`).
- **Assume the platform rewrites something.** Type and visibility are the usual suspects; both are behavioural, not cosmetic — a wrong type misrepresents the work, a non-public visibility removes it from discovery entirely.
- **Run it on a schedule.** A publish-time check catches the first moment; only a recurring check catches later platform-side changes.

| Negative control | Expected result |
|---|---|
| Change an expectation in the registry so it no longer matches live | the check exits **non-zero**, naming the field |
| Point it at a deliberately wrong record id | exits **non-zero** (not a silent no-op — see `SF-001`) |

## Related

- `SF-006` — the published channel's registry coverage has the same frame problem
- `SF-005` — what the read-back check looks like when absence is not counted
- `SF-007` — the empty-field cases are usually visible only from the published side
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § C

---

## 中文要点

- **一句话**：本地门禁全绿，**线上仍是错的** —— 因为线上那份是与本地不同的对象。
- **为什么会静默**：两个命题被混淆了。"本地工作树内部一致"便宜、可控；"线上状态符合预期"要联网、要凭据、要与期望比对。而且**线上对象有自己的状态**（版本号被平台改写、机构字段从账号档案带出、类型被平台规则重新映射、可见性默认非公开）—— 这些**从未出现在文件里**，所以 diff 里永远看不到。
- **怎么自查**：对每一个外部渠道问三句：① 有没有**读线上实况**的检查？（不是检查本地源）② 它是对着**声明的期望**比对，还是只打印"我看到了什么"？③ 它检查**平台会改写的字段**（类型／可见性）了吗？
- **修法要点**：**每个已发布渠道配一次线上实读核对**。期望值必须**声明**（拿线上比线上是同义反复，恒绿）；期望进登记表；并假设平台一定会改写点什么（类型、可见性最常见）；最后**定期跑**，只在发布时跑只能抓第一次。
- **反向对照**：故意把登记表里的期望改到与线上不符 → 必须指名报错并非零退出。
