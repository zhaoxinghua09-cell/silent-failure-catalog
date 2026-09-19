# SF-007 · Empty value is silent

**Status**: `stable` ｜ **Family**: B · Uncounted Absence ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A required field is empty, and nothing anywhere breaks — the page loads, the API responds, the reference resolves.

## Symptom

A record is structurally valid and semantically hollow. Every consumer works:

- the profile page renders (the empty field is simply not displayed)
- the API returns `200` with `{"field": null}`
- the identifier resolves and the citation parses
- the schema validator passes, because the field is optional *in the schema*

Nothing is broken. Nothing is complete either. The record is **findable but not searchable** — a distinction no error channel expresses.

Concrete instance: a researcher profile with identity, works and affiliation all present, but biography, keywords and external links empty. The profile is live, the DOI resolves, the ORCID record is valid. And a retrieval system has nothing to match on beyond the name — so it is effectively invisible for every query except the person's own name, which nobody searches.

**The general shape:** the field is required for the record's *purpose* but optional in the record's *schema*. Absence is therefore legal, and legal absence is not reported anywhere.

## Why it is silent

*A way for "absent" to count* is missing — and here the schema actively agrees with the omission. The validity check and the usefulness check are different checks, and only the first one exists.

There is a second reason this survives every automated audit: **the failure mode is compatible with every success signal.** Page up, status 200, identifier resolves, no drift, no alert. An audit that asks "is anything broken?" answers no. Only an audit that asks **"is the expected thing present?"** can see it.

## Minimal reproduction

```python
record = {"id": "example", "name": "X", "biography": "", "keywords": []}

assert validate_schema(record) is True      # passes — all fields optional
assert http_get(record["id"]).status == 200 # passes — page renders

print("record OK")                          # → and it is, structurally
# ...but a search over the record's subject matter returns nothing.
```

Observed: page renders, no error, no warning — Expected after fix: a validation failure naming the empty required-for-purpose fields

## Self-check

Enumerate the fields that a **retrieval system** would need in order to match this record against a query — then check whether each is populated *and* whether anything asserts it.

```
field           populated?   asserted non-empty?
name            yes          yes (schema)
biography       no           no               ← the hole
keywords        no           no               ← the hole
```

Anything with `populated=no, asserted=no` is this bug.

## Fix

Split "required" into two explicit classes, and assert the second one.

```python
REQUIRED_FOR_VALIDITY  = ["id", "name"]          # schema-level
REQUIRED_FOR_PURPOSE   = ["biography", "keywords", "links"]   # discoverability-level

empty = [f for f in REQUIRED_FOR_PURPOSE if not record.get(f)]
if empty:
    raise SystemExit(f"record {record['id']}: required-for-purpose fields empty: {empty}")
```

Two design principles that prevent the class:

1. **Optional in the schema is not optional in practice.** Encode the purpose-level requirement somewhere assertable, even if the schema cannot express it.
2. **Make the check part of the pipeline that publishes**, not a separate audit. An audit that must be remembered will not be run; an assertion in the publish path cannot be skipped.

Where a field's emptiness is legitimate for some records, express it as an explicit declaration (`fields_not_applicable = [...]`) rather than as an absence — so that "not applicable" and "forgotten" remain distinguishable. This is the same move as `SF-006`'s registry: turn a default into a declaration.

| Negative control | Expected result |
|---|---|
| Blank a required-for-purpose field | the publish path exits **non-zero**, naming the field |
| Remove the assertion, re-run | the record publishes silently — proving the assertion was doing the work |

## Related

- `SF-005` — the aggregate version: many such fields, all reported as neutral
- `SF-006` — the registry-level version of the same frame problem
- `SF-010` — empty fields are usually only visible from the **published** side, not the local tree
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § B

---

## 中文要点

- **一句话**：必需字段空着，**系统一处都不坏** —— 页面照常开、接口照常 200、标识符照常解析、schema 校验照常通过。
- **为什么会静默**：该字段对记录的**用途**必需，但在**schema 里是可选的** → 空着合法，而合法的空不会被任何地方报告。失效形态与所有成功信号并存：页面在、状态 200、无漂移、无告警。只问"有没有坏"的审计永远答"没有"；只有问"**该有的在不在**"才看得见。
- **怎么自查**：列出"检索系统需要哪些字段才能把这条记录和查询匹配上"，逐个检查是否**已填**且**有断言**。`已填=否, 有断言=否` 的就是洞。
- **修法要点**：把"必需"拆成两类 —— `REQUIRED_FOR_VALIDITY`（schema 级）与 `REQUIRED_FOR_PURPOSE`（可发现性级），并断言后者非空；断言要挂在**发布路径**上，而不是另做一个"要记得跑"的审计。
- **反向对照**：把某个用途必需字段置空 → 发布路径必须指名报错并非零退出。
