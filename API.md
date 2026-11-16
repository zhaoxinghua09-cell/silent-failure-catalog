# API — two contracts

This repository has no server and no network API. It has two contracts that anything consuming or contributing to it must be able to rely on: **the entry format**, and **the checker's behaviour**.

## Contract 1 — an entry file

Path: `failures/SF-NNN-<slug>.md`. One file, one failure mode, self-contained and safe to quote.

Structure enforced by `tools/check-catalog.py`:

| Element | Rule |
|---|---|
Title | First line matches `^# (SF-\d{3}) ·` — the id in the title, a middle dot, then the name |
Header fields | All four present on one line: `Status`, `Family`, `Confidence`, `as of` |
Sections | All six present, in this order: `## Symptom`, `## Why it is silent`, `## Minimal reproduction`, `## Self-check`, `## Fix`, `## Related` |
Status | `stable` · `draft` · `deprecated` |
Family | A · Vacuous Verification, B · Uncounted Absence, C · … (see `docs/taxonomy.md`) |
Confidence | `high` · `medium` · `low` — how sure the reproduction is |
Index | The id appears in `failures/README.md` under its family table, linked to this file |

An entry that omits a section is **not** "just less detailed" — it is a broken contract, and the checker fails on it, because absence must count as failure (see `ARCHITECTURE.md`, invariant 1).

## Contract 2 — the checker

```
python3 tools/check-catalog.py [--scan-leaks] [--selftest] [--json]
```

| Exit | Meaning |
|---|---|
`0` | Every required thing is present and every relative link resolves |
`1` | At least one problem; each is printed with the file and line that produced it |

Flags:

- `--selftest` — proves the link-discipline rule fires on its bad sample and stays quiet on its good ones, then proves the negative control (with the rule set emptied, nothing fires). Exit 0 only if both hold.
- `--scan-leaks` — heuristic de-identification scan (absolute paths, home directories, emails, token-like strings, internal hostnames).
- `--json` — machine-readable output, for a dashboard or another agent.

**What exit 0 does not mean.** It means the catalog is structurally intact — ids, sections, index, links. It does **not** mean the entries are correct, that the taxonomy is complete, or that any product has been evaluated. A green run here is a statement about this repository's consistency, nothing more.

## Consuming the catalog as data

There is no official JSON export. The stable machine-readable surface is:

1. `manifest.sha256` — the file list with hashes, for pinned citations.
2. `failures/README.md` — the index table (id, name, one-line symptom, status).
3. The entry files themselves — plain Markdown, six fixed sections, quotable with attribution.

If you need structured records, parse the index table; it is deliberately regular. Treat any derived dataset as yours, not as ours: we do not certify your parse.

---

# API — 两份契约

本仓没有服务端、没有网络 API。它有两份必须能被依赖的契约：**条目格式**，与**检查器行为**。

## 契约一：条目文件

路径 `failures/SF-NNN-<slug>.md`，一个文件一个失效模式，自足、可直接引用。

强制结构：标题首行匹配 `^# SF-NNN ·`；头部四字段 `Status` / `Family` / `Confidence` / `as of` 齐全；六个小节齐全且顺序为 `## Symptom`、`## Why it is silent`、`## Minimal reproduction`、`## Self-check`、`## Fix`、`## Related`；索引 `failures/README.md` 中有该 ID 且链到本文件。

**缺一个小节不等于"写得简略"，而是一份坏掉的契约**，检查器会失败——因为缺失必须算作失败（见 `ARCHITECTURE.md` 不变量 1）。

## 契约二：检查器

```
python3 tools/check-catalog.py [--scan-leaks] [--selftest] [--json]
```

退出码 `0` = 必需项齐全、相对链接可解析；`1` = 至少一个问题，逐条打印文件与行号。

`--selftest` 证明链接规则既能触发又能保持沉默（含"规则集清空后必须全部沉默"的负向对照）；`--scan-leaks` 做去标识化启发式扫描；`--json` 给程序读。

**退出码 0 不等于什么**：只表示本仓结构完整（ID、小节、索引、链接），**不**表示条目内容正确、分类完整，或任何产品被评估过。这里的绿灯只说明这个仓库自身一致，仅此而已。

## 作为数据消费

没有官方 JSON 导出。稳定的机器可读面是 `manifest.sha256`（固定引用）、`failures/README.md` 索引表（ID / 名称 / 一行症状 / 状态）、以及条目文件本身。要结构化数据就解析索引表，它刻意保持规则。派生数据集是你的，不是我们的——我们不认证你的解析结果。
