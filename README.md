<div align="center">

# Silent Failure Catalog
## 许可说明 · License Notice

> **本仓库使用自定义的「分层」许可：代码 MIT、内容保留所有权利**——不是整仓 MIT 或
> Apache-2.0。平台显示为 `Other`（NOASSERTION），属识别算法的正常结果，
> **不代表本仓库处于无许可状态**。

- **权利状态**：全部内容保留所有权利（All Rights Reserved）。未经书面许可，
  不得复制、改编、再分发、公开传播或用于衍生作品。
- **可否引用**：可以。允许在**注明出处**的前提下引用与学术、公共讨论；
  引用时请同时标注仓库名、原文链接 `https://github.com/zhaoxinghua09-cell/silent-failure-catalog`
  与权利人「赵兴华 / Steven Zhao·China」。
- **完整条款**：代码见 [LICENSE](LICENSE)（MIT）；内容见 [LICENSE-CONTENT](LICENSE-CONTENT)（**保留所有权利**，注明出处可引用）。
- **联系**：zhaoxinghua09@gmail.com ｜ ORCID 0009-0001-0512-1237 <!-- leak-scan: allow — the maintainer's published contact address; deliberate, not a leak -->
- **品牌状态限定**：MedXpert、SynomosAI、LGD 等为相关项目标识，
  **均未申请实体注册、未申请商标注册**；出现仅作来源标识，
  不构成对法人实体或商标权的任何主张。
- **免责**：本仓库内容不构成法规意见或注册代理服务；关键数据以监管机构最新发布为准。

---


**A catalog of validation that passes while nothing is being checked.**

*Silent failure modes in CI gates, test suites, data pipelines and AI-agent harnesses — with detection recipes.*

[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Content: All Rights Reserved](https://img.shields.io/badge/content-All%20Rights%20Reserved-lightgrey.svg)](LICENSE-CONTENT)
[![Entries](https://img.shields.io/badge/entries-14-14B8A6)](failures/)
[![Zero dependency](https://img.shields.io/badge/deps-stdlib%20only-0B1F3A)](#quick-start)
<!-- The gate runs in CI now, so the badge below can point at a run that exists.
     It was withheld until it did: a badge claiming a validation run that does not
     exist would be exactly the silent pass this repo documents. The second badge
     still points at the check you can run yourself, right now, locally. -->
[![gates](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/actions/workflows/gates.yml/badge.svg)](https://github.com/zhaoxinghua09-cell/silent-failure-catalog/actions/workflows/gates.yml)
[![Catalog validation](https://img.shields.io/badge/validation-check--catalog%20--selftest-0B1F3A)](tools/check-catalog.py)

[Start here](docs/start-here.md) · [Taxonomy](docs/taxonomy.md) · [Question Map](docs/question-map.md) · [Catalog index](failures/) · [Take the challenge](docs/take-the-challenge.md) · [Contributing](CONTRIBUTING.md)

`silent-failure` `false-green` `verification-gap` `ci-cd` `testing` `ai-agents` `observability` `data-quality`

</div>

---

> **If this saved you a debugging session, open an issue naming the pattern you hit.** That is what decides which failure mode gets written next — a star does not, and we do not trade, buy or reward them. If you would rather attack the tooling itself, [start here](docs/take-the-challenge.md).
>
> If you found this through one of our other projects, [`docs/start-here.md`](docs/start-here.md) maps a symptom to the entry that answers it, and [`docs/where-to-find-us.md`](docs/where-to-find-us.md) is the one page that carries all of our channels.
>
> The tooling here found **ten defects in itself** while being built. The record is in [`docs/building-this-catalog.md`](docs/building-this-catalog.md) — a catalog about silent passes that was itself silently passing would be worth nothing.

---

## The problem in one paragraph

> *"A test that always passes is worse than no test. It looks like coverage and provides none."*

A crash announces itself. A silent failure does not. The page still loads, the DOI still resolves, the pipeline still prints `PASS`, the agent still reports progress. **Nothing is red, and nothing is working.**

These failures share a shape: the system has no *signal* for "the thing that should have happened did not happen." Missing, empty, skipped, uncounted and mis-attributed states all render as **success**.

This catalog names those shapes so they can be discussed, searched, and mechanically detected.

## What makes this different

There is no shortage of blog posts about this. There is a shortage of a **catalog**.
Every entry here is:

| | |
|---|---|
| **Named** | An unnamed phenomenon cannot be searched for, cited, or fixed. Naming comes first. |
| **Minimal** | A runnable reproduction — usually under 10 lines. |
| **Fixed** | The concrete change that converts the silent pass into a loud failure. |
| **Control-bearing** | Each fix requires a *negative control*: proof the check can detect a real break. |

Plus a runnable linter that scans your own gates for these patterns:

```bash
python tools/gate-lint.py path/to/your_gate.py
python tools/gate-lint.py --selftest      # proves the linter itself works
```

## Taxonomy — five families

| Family | What it is | Entries |
|---|---|---|
| **A · Vacuous Verification** | The check runs, but has no discriminating power | [SF-001](failures/SF-001-zero-items-pass.md) · [SF-002](failures/SF-002-early-return-as-skip.md) · [SF-003](failures/SF-003-swallowed-exception.md) · [SF-004](failures/SF-004-sentinel-value.md) |
| **B · Uncounted Absence** | Something required is missing, and missing does not count as failure | [SF-005](failures/SF-005-neutral-marker-not-counted.md) · [SF-006](failures/SF-006-undeclared-not-checked.md) · [SF-007](failures/SF-007-empty-value-is-silent.md) |
| **C · Wrong Evidence** | The signal used cannot prove the conclusion drawn from it | [SF-008](failures/SF-008-loading-artifact-as-evidence.md) · [SF-009](failures/SF-009-exposure-counted-as-usage.md) · [SF-010](failures/SF-010-local-green-not-remote-green.md) |
| **D · Drifting Oracle** | The check itself degrades — exemption, substring match, mis-attribution | [SF-011](failures/SF-011-always-green-oracle.md) · [SF-012](failures/SF-012-misattributed-failure.md) |
| **E · Process & Environment** | The failure lives outside the logic: stale artifacts, zombie processes | [SF-013](failures/SF-013-stale-copy-contaminates-check.md) · [SF-014](failures/SF-014-zombie-process-looks-alive.md) |

→ Full taxonomy with the shared root cause: [`docs/taxonomy.md`](docs/taxonomy.md)

## The shared root cause

Every family above is the same bug at a different layer:

> **The absence of evidence is being recorded as evidence of absence of a problem.**

A gate that checks only what it can find will always pass. A gate that must *also* assert that the expected thing exists is the only kind that can fail.

Two mechanical consequences follow, and they are the two most useful rules in this repo:

1. **Missing must enter the exit code.** If "required but absent" is recorded as a neutral note — a log line, a `⚪`, a skip, a warning — then a required-but-absent state produces `exit 0`. The gate is blind exactly where it matters most.
2. **No negative control means no evidence.** A check that has never been observed failing has not been shown to be capable of failing. *Every negative result needs a positive control.*

## Quick start

```bash
git clone https://github.com/zhaoxinghua09-cell/silent-failure-catalog.git
cd silent-failure-catalog

# lint a gate / validator / audit script you already trust
python tools/gate-lint.py path/to/your_gate.py

# verify the catalog itself is internally consistent
python tools/check-catalog.py
```

Both scripts are **stdlib-only** — no install, no network, Python 3.9+.

Example output — a **verbatim** run against the fixtures shipped in `tools/samples/bad/`, not a mock-up. Reproduce it yourself with the two commands below:

```bash
cd tools/samples/bad
python ../../gate-lint.py . --tree .
```

```
counter_unused.py
  🔴 SFL-001  no-nonzero-exit              cannot fail: no exit()/raise/assert anywhere in this file
  🟠 SFL-004  counter-does-not-gate-exit   counter(s) never influence the exit code: problems

no_exit.py
  🔴 SFL-001  no-nonzero-exit              cannot fail: no exit()/raise/assert anywhere in this file

swallow.py
  🔴 SFL-001  no-nonzero-exit              cannot fail: no exit()/raise/assert anywhere in this file
  🔴 SFL-002  swallow-exception            except block only does: pass

unchecked_empty.py
  🟡 SFL-003  unchecked-empty              not <expr> branch in check() has no failure path — empty/false is treated as OK

zero_items.py
  🟠 SFL-005  zero-item-pass               invokes a test runner but never guards against '0 items collected'

  🟡 SFL-006  no-negative-control          no negative-control sample found under . — nothing here demonstrates that any check in this tree is capable of failing

8 finding(s): 4 high, 2 medium, 2 low.
2 low-severity finding(s) did NOT affect the exit code. Pass --strict to make them fail.
Run with --explain for the fix and the known false positives.
```

Note the second-to-last line: low-severity findings are **reported as downgraded**, in the output, every time. Silently dropping a finding because of its severity is exactly the failure this catalog documents, so the tool announces the downgrade instead of hiding it. `--strict` promotes low findings to a non-zero exit.

## Using an entry

Each entry follows the same six-part shape, so it can be read as a self-contained chunk:

```
Symptom → Why it is silent → Minimal reproduction → Self-check → Fix → Related
```

Start at [`failures/`](failures/) for the index, or jump straight to the one that matches what you're seeing.

## Content integrity

`INTEGRITY.md` and `manifest.sha256` record a SHA-256 for every file plus one digest over the set, so a reader can confirm they hold the same bytes this page describes:

```bash
python tools/make-manifest.py --check     # exit 1 on any drift
python tools/make-manifest.py             # regenerate after an intended change
```

This detects a truncated download, a partial checkout, or an unnoticed edit. It does **not** attest authorship — a manifest ships beside the content it describes, so whoever changes the content can regenerate it. It anchors a *citation*, not a *claim*.

Because the digests are over raw bytes, `.gitattributes` sets `* -text`: with Git's default end-of-line translation a file committed with LF is checked out with CRLF on Windows, every digest changes, and the manifest would be wrong on exactly one platform.

**If you change any content file, regenerate the manifest in the same commit.** CI enforces this, and it also holds the check to the catalog's own standard — one byte is corrupted on purpose in CI and the verification is *required* to fail.

## Contributing

A new entry is welcome when you can supply a **reproduction** and a **negative control** — an incident write-up alone is not enough, because it cannot be mechanically checked.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the template at [`failures/TEMPLATE.md`](failures/TEMPLATE.md).

## Citing

See [`CITATION.cff`](CITATION.cff). Each entry carries an `as of` date — cite the entry **and** the date, because a fixed pattern can regress.

## Where to go next

| | |
|---|---|
| A symptom you are currently staring at | [`docs/start-here.md`](docs/start-here.md) |
| Every channel, citation rule, and the things we decline to do | [`docs/where-to-find-us.md`](docs/where-to-find-us.md) |
| An open question, or something that looks wrong but is not a pattern yet | [`SUPPORT.md`](SUPPORT.md) |
| A way to defeat the tooling | [`SECURITY.md`](SECURITY.md) |
| The route from reader to contributor | [`docs/take-the-challenge.md`](docs/take-the-challenge.md) |

These are the only outbound and entry links in this README, by policy — the rule is enforced by `check_promo_links` in [`tools/check-catalog.py`](tools/check-catalog.py), not by good intentions.

## Scope and non-goals

**In scope** — validation that silently passes; false greens in CI, gates, audits, data pipelines and agent harnesses.

**Out of scope** — general software bugs; performance problems; anything whose failure mode is *loud* (crash, non-zero exit, exception trace). Those are ordinary bugs. This catalog is specifically about failures that wear the costume of success.

**Not affiliated with any vendor or standards body.** No entry claims conformance with any standard. Where a technique maps onto an established practice (mutation testing, negative controls, test oracles), the established source is linked rather than restated.

---

## 中文说明

**静默失败 = 系统看着一切正常，其实该发生的没发生。**

崩溃会喊，静默失败不会。页面照常打开、DOI 照常解析、脚本照常打印 `PASS`、Agent 照常报告进度 —— **没有一处是红的，也没有一处是对的**。

本目录把这类失败**命名、分类、给出最小复现与修法**，并配一个可直接跑的体检器 `tools/gate-lint.py`（纯标准库，零依赖）。

**共用根因一句话**：

> **把「没有证据」当成了「没有问题」的证据。**

两条可机械执行的推论：

1. **缺失必须进退出码** —— 若"该有的没有"只记成一句日志／一个中性标记／一次 skip，那它永远产出 `exit 0`，门禁恰好在最要紧处失明。
2. **没有反向对照就没有证据** —— 一个从未被观察到失败的检查，没有被证明过它**能**失败。**每一个否定结论都要配一个阳性对照。**

**三个入口**：

- [`docs/start-here.md`](docs/start-here.md) —— **从症状找条目**：左边写"你看到什么"，右边直给对应条目。
- [`docs/take-the-challenge.md`](docs/take-the-challenge.md) —— **来拆我们的台**：三档难度，攻破我们自己的检测器，攻破即署名。
- [`docs/where-to-find-us.md`](docs/where-to-find-us.md) —— **全部渠道与引用口径**（本仓唯一集中放外链的地方）。

**怎么贡献最有用**：不要点赞，**开一个 issue 说出你撞见的那类静默失败**——它决定下一条写什么。

许可：代码 MIT ｜ 内容保留所有权利（注明出处可引用）

---

<div align="center">

**© 2026 赵兴华 / Steven Zhao·China** · Code [MIT](LICENSE) · Content [All Rights Reserved](LICENSE-CONTENT)

*Compiled from real incidents in AI-agent and CI toolchains. Entries are generalized; no proprietary or client material is reproduced.*

</div>

<!-- drift probe -->
