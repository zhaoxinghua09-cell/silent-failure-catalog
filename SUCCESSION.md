# SUCCESSION — how someone else takes this over

## Current state (2026-11-17)

| Role | Named? |
|---|---|
| Maintainer | Yes — `.github/CODEOWNERS` (or the repository owner, where no CODEOWNERS file exists) |
| Successor | **No.** Stated rather than implied. |
| Release / DOI authority | Maintainer only |
| Content licensing authority | Maintainer only — content is all rights reserved, so no one else may grant reuse |

**Bus factor: 1.** The entries survive without a maintainer — they are plain files. What does not survive is the authority to publish a snapshot, mint a DOI, or grant content reuse.

## First hour

1. `python3 tools/check-catalog.py` → expect `PASS` over 16 entries and exit 0.
2. `python3 tools/check-catalog.py --selftest` → expect the rule to fire on its bad sample and stay quiet on its good ones.
3. If either fails, do not touch content: fix the checker first. A checker in doubt invalidates every statement in the repository.

## Second hour

4. Read `docs/taxonomy.md` — the families (A · Vacuous Verification, B · Uncounted Absence, C…E) are the intellectual structure; adding an entry into the wrong family is the most common quality failure.
5. Read three entries end to end, including one `draft` — `drafts` show where the reproduction is not yet convincing, which is where the catalog's honest edge is.
6. Read `docs/pull-request-workflow.md` and run `tools/check-gate-parity.py` — the local instructions and the CI gate must agree.

## Publishing a snapshot

- [ ] `check-catalog.py` PASS and `--selftest` PASS
- [ ] `tools/check-line-endings.py`, `tools/gate-lint.py`, `tools/verify_release_consistency.py` all exit 0
- [ ] `manifest.sha256` regenerated with `tools/make-manifest.py` and verified
- [ ] Entry count in `failures/README.md` matches the number of `SF-*.md` files
- [ ] No badge added before the run it points at exists (`docs/adr/ADR-001`)
- [ ] CHANGELOG states what changed, including any status promotion (`draft` → `stable`)

## Recovery

- **An entry was deleted by accident.** `git log -- failures/` then `git checkout <sha> -- failures/SF-NNN-*.md`; also restore its index row, or the checker will report `index id has no page`.
- **The index and the files disagree.** Trust the files, fix the index, then re-run. Never delete a file to satisfy an index row.
- **A rule stopped firing.** Check `git log -p tools/check-catalog.py`; a pattern edited without a sample change is the usual cause. The sample pair is the contract.
- **DOI / Zenodo metadata drifted.** `tools/verify_release_consistency.py` is the check; the DOI is immutable once minted, so a new version gets a new DOI rather than a rewritten one.

## What a successor may not do without an explicit, recorded decision

- Publish a status badge whose target does not resolve
- Delete an entry, section or index row to make a check pass
- Change a `stable` entry's reproduction without re-running it
- Relax `LICENSE-CONTENT`: content is all rights reserved; attribution-only reuse is the ceiling
- Add a dependency. The zero-dependency promise is enforced by `tools/no_coreutils_assert.py`, and it is the reason the checker runs anywhere without a network

---

# 接替说明 — 别人怎么接手

## 现状（2026-11-17）

| 角色 | 是否已指定 |
|---|---|
维护人 | 是——`.github/CODEOWNERS`（无该文件时即仓库所有者） |
接替人 | **否。写出来，不是暗示。** |
发布 / DOI 权限 | 仅维护人 |
内容许可授权 | 仅维护人——内容是保留所有权利，别人无权授予再利用 |

**Bus factor = 1**。条目本身不依赖维护人（它们就是纯文件）；不随人消失的是三项权限：发布快照、铸 DOI、授予内容再利用。

## 第一小时

1. `python3 tools/check-catalog.py` → 预期扫过 16 条、`PASS`、退出 0；
2. `python3 tools/check-catalog.py --selftest` → 预期规则对坏样本触发、对好样本沉默；
3. **任一失败就不要动内容，先修检查器**——可疑的检查器会让仓里每一句陈述失效。

## 第二小时

4. 读 `docs/taxonomy.md`：family（A 空转验证 / B 未计入的缺失 / C…E）是这套东西的智力结构，把条目放进错的 family 是最常见的质量事故；
5. 通读三条条目，其中至少一条 `draft`——草稿暴露的是"复现还不硬"的地方，那正是本仓诚实的边缘；
6. 读 `docs/pull-request-workflow.md` 并跑 `check-gate-parity.py`：本地说明与 CI 门禁必须一致。

## 发布快照清单

- [ ] `check-catalog.py` PASS 且 `--selftest` PASS
- [ ] `check-line-endings.py`、`gate-lint.py`、`verify_release_consistency.py` 全 0
- [ ] `manifest.sha256` 用 `make-manifest.py` 重生成并校验
- [ ] `failures/README.md` 的条目数与 `SF-*.md` 文件数一致
- [ ] **没有在其所指运行存在之前加徽章**（见 `docs/adr/ADR-001`）
- [ ] CHANGELOG 写明变化，含状态提升（`draft` → `stable`）

## 恢复

- **误删条目**：`git log -- failures/` 找到提交，`git checkout <sha> -- <文件>`，并同时恢复索引行，否则检查器会报 `index id has no page`；
- **索引与文件不一致**：信文件、改索引、再重跑；**永远不要为了满足索引而删文件**；
- **规则不再触发**：查 `git log -p tools/check-catalog.py`；改了模式却没改样本，是最常见原因——样本对就是契约；
- **DOI / Zenodo 元数据漂移**：用 `verify_release_consistency.py` 检查；DOI 一旦铸出不可改，新版本铸新 DOI，不要改写旧的。

## 未经明确且记录在案的决定，接替人不得

- 发布指向不可解析目标的徽章
- 为让检查通过而删除条目、小节或索引行
- 不改复现就改 `stable` 条目的内容
- 放宽 `LICENSE-CONTENT`：内容保留所有权利，注明出处的引用是上限
- 新增依赖：零依赖承诺由 `tools/no_coreutils_assert.py` 强制，它也是这个检查器能在任何无网环境跑起来的原因
