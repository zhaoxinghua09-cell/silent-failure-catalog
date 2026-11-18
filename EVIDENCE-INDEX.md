# EVIDENCE-INDEX — silent-failure-catalog

口径：等级由**谁能复现**决定。没有的写 `0`，并写清缺什么才能升。本表可逐行点开核对。

## 现状

| 级 | 结果 | 证据位置 | 说明 |
|---|---|---|---|
| L1 自我复现 | **有** | `tools/check-catalog.py --selftest`、`tests/test_catalog.py`、`tests/test_negative_controls.py`、`tools/checker-mutation.py`、`tools/impl-mutation.py`、`tools/impl-mutation-negctl.py`、`tools/samples/{good,bad}/`、`.github/workflows/gates.yml`、`INTEGRITY.md`、`manifest.sha256` | 每个条目有可跑复现与负控；检查器本身受变异测试（把检查器改坏，测试必须变红）；CI `gates.yml` 每 push 跑 |
| L2 异体审查 | **有限** | `REVIEW.md`、`docs/adr/ADR-001-badge-withheld-until-gate-exists.md`、`docs/building-this-catalog.md` | 有评审记录与一条"门禁不存在就不发徽章"的 ADR，但**评审者是否为作者之外的异体，需回执内可核**；本表不据此升为"有" |
| L3 第二实现 | **0** | — | 无独立于本仓的第二份目录/检查器实现；外部实现若出现，须在同一批条目上给出相同判定 |
| L3.5 外部语料 | **0** | — | `examples/S5-Qregister`、`examples/T08-S5Q2`、`examples/clinical-handoff` 是本仓自建演示，属 L1 范围，不计外部语料 |
| L4 外部节点 | **0** | DOI `10.5281/zenodo.23301091`（`.zenodo.json`、`zenodo-deposit.yml`） | Zenodo 存档是**外部归档**，不等于外部采用；无第三方系统/组织指认 |

## 已知不硬的地方

1. **条目数量口径不一致。** README 徽章写 `entries-15`，`failures/` 下实际有 `SF-001` 至 `SF-016` 共 16 个条目文件。本表不裁决哪个对，先把这个不一致登记为待修缺陷——一个关于"静默出错"的仓库，自己的计数不该静默。
2. **无第二实现。** 检查器与条目同源，无法排除"同一批盲点"。
3. **无外部采用者。** Zenodo DOI 可被引用，但不构成 L4。
4. **分类学是作者视角的分类。** `docs/taxonomy.md` 不宣称覆盖全部失效模式，README 也只说"a catalog of"，不宣称完备。

## 维护约定

- 新增条目必须同时带：复现脚本、修复配方、负控；缺一项即不合并（这是本仓既有规则）。
- 每次合并改变结论的 PR 同步本表。
- 等级只降不升，除非新证据落盘。引用本仓时请一并标注仓库名、链接与权利人（分层许可：代码 MIT，内容保留所有权利）。
