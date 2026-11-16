# Troubleshooting

Every entry below is a condition you can hit while checking this repository, with the cause and the fix. If a symptom is missing, that is a gap — open an issue rather than guessing.

## `check-catalog.py` exits 1

It always prints the file and line that produced each finding. Read the first finding, not the last: later findings are often consequences of the first.

| Message pattern | Cause | Fix |
|---|---|---|
`missing section: ## Fix` | An entry was edited and a heading lost | Restore the heading; the six sections are fixed, not suggested |
`missing header field: Confidence` | Header line rewritten by hand | Put all four fields on the status line: Status · Family · Confidence · as of |
`id not in index` | New entry added without touching `failures/README.md` | Add the row to the right family table |
`index id has no page` | Row added ahead of the page, or a rename | Create the page or remove the row |
`unresolved link` | A relative link points at a file that moved | Fix the path; do not delete the link to silence it |

**Do not "fix" a finding by deleting the thing it asks about.** Deleting an entry to make the index pass is the same defect class this repository documents.

## `--selftest` fails

Two cases, and they mean different things.

- **"must fire but stayed quiet"** — a rule was weakened or a pattern was edited. The rule no longer catches the sample it is supposed to catch.
- **"still a finding with no rule loaded"** — the negative control failed: something other than the rules is producing findings, which means any finding this checker reports may be unrelated to the rule.

Both are release blockers. Do not adjust the sample to match the rule; adjust the rule to match the sample, or explain in an ADR why the sample changed.

## `--scan-leaks` flags something

The scan is heuristic and intentionally blunt. Its exceptions are narrow: `example.com`, `example.org`, `example.invalid` are allowed, and `.internal` / `.corp` / `.local` hostnames are not.

- **A real email in an entry** — remove it. Entries should not carry anyone's address.
- **A path that looks absolute** — rewrite as a relative path inside the repository.
- **A false positive on prose** — widen the allow-list in `LEAK_PATTERNS` with a comment saying what shape you are excluding and why. A silent allow-list edit is itself a silent failure.

## Windows: line endings

Entries are checked for consistent line endings (`tools/check-line-endings.py`). Editing in an IDE that rewrites CRLF/LF produces a diff over the whole file and a gate failure.

Fix: set `core.autocrlf` deliberately for this checkout, or edit with an editor configured per `.gitattributes`. Do not convert a file wholesale to make the check pass — that buries the real change.

## The gate passes locally but fails in CI

Compare what you ran with `docs/pull-request-workflow.md`, and check `tools/check-gate-parity.py`: it exists precisely because the local instructions and the CI gate can drift apart. Whichever side is wrong, fix it in the same pull request — a gate that disagrees with its own documentation is a silent failure about silent failures.

## An entry reads as vague

The six sections are a floor, not a template. If `## Minimal reproduction` cannot be pasted into a terminal and produce the symptom, the entry is not ready for `stable`. Leave it `draft` and say so in the entry — a draft that admits it is honest; a `stable` that cannot be reproduced is a claim without evidence.

---

# 故障排查

以下每条都是检查本仓时会真实撞到的情形，附原因与处置。若你遇到的症状不在这里，那是缺口——请开 issue，不要猜。

## `check-catalog.py` 退出 1

它总会打印每个问题的文件与行号。**读第一条，不要读最后一条**：后面的发现常常是第一条的后果。

| 报错形态 | 原因 | 处置 |
|---|---|---|
`missing section: ## Fix` | 编辑时弄丢了标题 | 补回标题；六个小节是固定的，不是建议 |
`missing header field: Confidence` | 手工重写了头部行 | 四个字段放同一行：Status · Family · Confidence · as of |
`id not in index` | 加了条目但没改 `failures/README.md` | 在对应 family 表补一行 |
`index id has no page` | 先加行后建页，或改了名 | 建页或删行 |
`unresolved link` | 相对链接指向已移动的文件 | 改路径；**不要为了消掉报错而删链接** |

**不要靠删掉被指出的东西来"修复"**。为了让索引通过而删掉一条条目，与本仓记录的是同一类缺陷。

## `--selftest` 失败

两种情形，含义不同：

- **"must fire but stayed quiet"**——规则被削弱或被改写，不再抓它本该抓的样本；
- **"still a finding with no rule loaded"**——负向对照失败：产生发现的不是规则本身，那么它报的任何发现都可能与规则无关。

两种都是发版阻断项。**不要改样本去迁就规则**；改规则去匹配样本，或用 ADR 说明为什么样本该变。

## `--scan-leaks` 报了东西

扫描是启发式、刻意钝。放行面很窄：`example.com`/`.org`/`.invalid` 允许，`.internal`/`.corp`/`.local` 不允许。

- **条目里有真实邮箱**：删掉，条目不承载任何人的地址；
- **看起来是绝对路径**：改成仓内相对路径；
- **散文误报**：在 `LEAK_PATTERNS` 里加允许项并注明排除的是什么形状、为什么。**静默改动允许清单，本身就是静默失败。**

## Windows 行尾

`check-line-endings.py` 会检查行尾一致。用会重写 CRLF/LF 的编辑器，会得到整文件 diff + 门禁失败。

处置：对本检出明确设置 `core.autocrlf`，或按 `.gitattributes` 配置编辑器。**不要为了过检查而整文件转换**——那会把真实改动埋掉。

## 本地过、CI 不过

把你跑的和 `docs/pull-request-workflow.md` 写的对上，并跑 `check-gate-parity.py`——它存在的理由就是"本地说明与 CI 门禁会漂移"。哪边错都在同一个 PR 里修掉：**门禁与自己的文档打架，是关于静默失败的静默失败**。

## 条目读起来空泛

六个小节是下限不是模板。若 `## Minimal reproduction` 不能粘进终端并复现症状，这条就不该是 `stable`。留在 `draft` 并写明白——承认自己是草稿是诚实的；复现不了的 `stable` 是没有证据的主张。
