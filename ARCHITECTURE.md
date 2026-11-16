# Architecture

Four layers, one direction of trust. Nothing here is aspirational — it describes what the repository does today (16 entries, verified 2026-11-17).

## The four layers

| Layer | What lives there | Who reads it |
|---|---|---|
**Entries** (`failures/SF-*.md`) | One failure mode per file, self-contained | Humans, quoting directly |
**Tools** (`tools/*.py`) | Verification of the entries themselves; stdlib only | Contributors, CI |
**Gates** (`.github/workflows/`) | The same checks, run on every push and on a schedule | Anyone before merging |
**Attestation** (`manifest.sha256`, Zenodo DOI) | A fixed snapshot with a resolvable identifier | Anyone citing the catalog later |

## Data flow

```
failures/SF-*.md  ─┐
failures/README.md ─┼─▶ check-catalog.py ──▶ exit 0 / exit 1 (each problem printed with its location)
docs/*.md          ─┘        │
                             ├─ every id in the index resolves to a page and back
                             ├─ every page carries six required sections + four header fields
                             ├─ every relative link resolves (outbound links skipped by policy)
                             └─ --selftest: the link rule must fire on its bad sample and stay quiet on its good ones

         ──▶ make-manifest.py ──▶ manifest.sha256 ──▶ release-attestation.yml ──▶ Zenodo deposit
```

## Three invariants

1. **Absence must be reported as failure.** A missing entry, a missing section, a missing index row — each is a finding, never a silent skip. This is the whole reason the repository exists; a checker that passes on absence would reproduce the defect it documents.
2. **A rule must be shown to fire, and shown to stay quiet.** `--selftest` holds a sample pair. A detector never observed failing is, by this catalog's own rule 2, not a guideline at all.
3. **Style rules do not reach for the network.** The link rule reads files; it does not resolve URLs. A validator that fails when the network is down turns a red build into a mystery.

## Module map (tools)

| Tool | Role |
|---|---|
`check-catalog.py` | The core gate: ids, sections, header fields, index consistency, relative links, `--selftest`, `--json` |
`check-line-endings.py` | Keeps text files consistent across platforms |
`check-gate-parity.py` | The gate must match what contributors are told to run locally |
`check-hook-deps.py` | Hook dependencies resolve before a hook runs |
`check-quoted-output.py` | Quoted command output still matches reality |
`defect-closure.py` | A defect is closed only with a check that fails without the fix |
`gate-lint.py` | The gate config itself is linted |
`impl-mutation.py`, `impl-mutation-negctl.py`, `checker-mutation.py` | Mutation tests: the checker must catch a deliberately broken input, and must not catch everything |
`no_coreutils_assert.py` | Guards the zero-dependency promise |
`make-manifest.py`, `verify_release_consistency.py` | Snapshot and release integrity |
`prepare.py` | Contributor setup |

## Boundaries

- **Not a certification.** Nothing here assesses a product or grants permission to operate anything.
- **Not exhaustive.** 16 entries with status `stable` / `draft` / `deprecated`; coverage is claimed per entry, not globally.
- **Content is not open-licensed.** Code is MIT; content is all rights reserved, quotable with attribution (`LICENSE-CONTENT`).

## Read next

`INSTALL.md` → `API.md` (entry format and tool contract) → `TROUBLESHOOTING.md` → `SUCCESSION.md`.

---

# 架构说明

四层，一条信任方向。以下描述本仓今天实际在做的事（16 条条目，2026-11-17 实测）。

## 四层

| 层 | 放什么 | 谁读 |
|---|---|---|
**条目**（`failures/SF-*.md`） | 一个文件一个失效模式，自足可引用 | 人，直接引用 |
**工具**（`tools/*.py`） | 校验条目本身；只用标准库 | 贡献者、CI |
**门禁**（`.github/workflows/`） | 每次推送与定时跑同一套检查 | 合并前的任何人 |
**固化**（`manifest.sha256`、Zenodo DOI） | 可解析标识符指向的固定快照 | 日后引用者 |

## 数据流

条目与索引 → `check-catalog.py` → 退出码 0/1（每个问题都打印位置）→ 清单哈希 → 发布存证 → Zenodo。

三项检查：索引中每个 ID 能解析到页面且反向成立；每页六个必需小节 + 四个头部字段；每条相对链接可解析（外链按策略跳过）；`--selftest` 证明链接规则既能触发也能保持沉默。

## 三条不变量

1. **缺失必须报成失败**：缺条目、缺小节、缺索引行都是"发现"，绝不是静默跳过。一个对缺失判通过的检查器，会重演本仓记录的那个缺陷。
2. **规则必须被证明能触发、也能保持沉默**：`--selftest` 带一正一负样本对。从未被观察到失败的检测器，按本仓自己的规则 2，根本不构成规则。
3. **风格规则不联网**：链接规则只读文件、不解析 URL。联网校验会把"红构建"变成"玄学问题"。

## 模块表与边界

见英文段的 Module map。边界：**不是认证**（不评估产品、不授予运营权限）；**不是穷尽**（16 条，覆盖范围按条声明，不按全局声明）；**内容不是开放许可**（代码 MIT，内容保留所有权利，注明出处可引用）。

## 往下读

`INSTALL.md` → `API.md`（条目格式与工具契约）→ `TROUBLESHOOTING.md` → `SUCCESSION.md`。
