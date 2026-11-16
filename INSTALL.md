# Install

There is nothing to install. The tools are standard library only by design, and a guard (`tools/no_coreutils_assert.py`) keeps it that way.

## Requirements

| Item | Requirement | Verified |
|---|---|---|
Python | ≥ 3.9 (f-strings and `pathlib` only in use) | 3.13.12 on Windows 11, 2026-11-17 |
Git | Any version that can clone | yes |
Network | None, after the clone | yes |
Packages | **None** — no `requirements.txt`, no `pyproject.toml`, no virtualenv needed | yes |

## Get the code and check it

```bash
git clone https://github.com/zhaoxinghua09-cell/silent-failure-catalog.git
cd silent-failure-catalog
python3 tools/check-catalog.py
```

Expected on a clean checkout: a run over 16 entries, then `PASS — every required section present, every id indexed, every link resolves.` and exit code 0.

On Windows PowerShell the same command works as:

```powershell
python tools\check-catalog.py
```

## Prove the checker itself works

```bash
python3 tools/check-catalog.py --selftest
```

This is not a smoke test. It asserts that the link rule fires on its bad sample, stays quiet on its good samples, and produces nothing at all once the rule set is emptied — the negative control. Expect `PASS — the rule fires on its bad sample and is silent on its good samples.`

If `check-catalog.py` passes but `--selftest` fails, **stop**: the checker's rules are in doubt, and a green run from a checker in doubt is exactly the silent pass this catalog documents.

## Optional: hooks and the rest of the gates

```bash
python3 tools/prepare.py
```

Then run, in any order:

```bash
python3 tools/check-line-endings.py
python3 tools/check-gate-parity.py
python3 tools/gate-lint.py
python3 tools/verify_release_consistency.py
```

Each exits 0 or 1 with the offending location printed. `docs/pull-request-workflow.md` states which of these a pull request must pass.

## There is no package to install

`this repository is not distributed via PyPI, npm, or any package registry.` Nothing is imported from it; entries are read as files. If you find an install instruction pointing at a registry, it is not ours.

---

# 安装

不需要安装。工具刻意只用标准库，且由 `tools/no_coreutils_assert.py` 守住这一条。

## 要求

| 项 | 要求 | 实测 |
|---|---|---|
Python | ≥ 3.9（只用到 f-string 与 `pathlib`） | Windows 11 上 3.13.12，2026-11-17 |
Git | 能 clone 即可 | 是 |
网络 | clone 之后不需要 | 是 |
第三方包 | **零**——无 `requirements.txt`、无 `pyproject.toml`、不需要虚拟环境 | 是 |

## 取代码并自检

```powershell
git clone https://github.com/zhaoxinghua09-cell/silent-failure-catalog.git
cd silent-failure-catalog
python tools\check-catalog.py
```

干净检出下的预期：扫过 16 条，末尾打印 `PASS — every required section present, every id indexed, every link resolves.`，退出码 0。

## 证明检查器本身有效

```powershell
python tools\check-catalog.py --selftest
```

这**不是**冒烟测试。它断言：链接规则对坏样本触发、对好样本沉默，且把规则集清空后什么都不报（负向对照）。预期 `PASS — the rule fires on its bad sample and is silent on its good samples.`

**若 `check-catalog.py` 通过而 `--selftest` 失败，请停下**：检查器的规则本身可疑，而一个可疑的检查器给出的绿灯，正是本仓记录的那种静默通过。

## 可选：钩子与其余门禁

```powershell
python tools\prepare.py
```

再逐个跑 `check-line-endings.py`、`check-gate-parity.py`、`gate-lint.py`、`verify_release_consistency.py`，各自退出码 0/1 并打印位置。PR 必须过哪几项见 `docs/pull-request-workflow.md`。

## 没有可安装的包

本仓不通过 PyPI、npm 或任何包管理器分发；它不被 import，条目按文件读取。若你看到指向包管理器的安装说明，那不是我们的。
