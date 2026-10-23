# SF-015 · Stale reference: citations rot when the cited state moves

**Status**: `candidate v1.1`（外审侧审阅通过带三条修改，v1.1 已按意见修订；待外审终审后转 `accepted`） ｜ **Family**: E · Process & Environment ｜ **Confidence**: high（三实例实取） ｜ **as of** 2026-10-23

> **One line.** A document cites an external object's *state* (issue open/closed, version, link alive) but carries no re-check mechanism, so the citation silently inverts its meaning when the cited state changes.
>
> **v1.1 changelog**（2026-10-23，按外审三条意见）: ① split into two subtypes — *rot* (true at write time, decays after) vs *defect* (incomplete at write time); ② re-check cadence now tiered by cited-object volatility instead of one-size-fits-all; ③ explicit scope statement — the linter covers governance-plane assets only, long-tail assets must cite facts, never bare states.

## Symptom

A glossary README says:

> opened as an open question in [themes#33] (2026-10-01)

Twenty-three days later, the cited issue is `closed` (closed 2026-10-02, wontfix, one day after the citation was written). The README still presents a dead question as a live one. Nobody notices, because nothing in the citing document watches the cited object.

The inversion is the same shape as `SF-013`'s temporal inversion, but with a different mechanism: there, the environment served a stale copy to correct logic; here, the **citation itself is the stale copy**, and the environment never pushes an update.

Two distinct harms compound:

1. **Wrong status claimed to readers.** "Open question" invites contribution and debate; the thread is actually closed by a maintainer decision (wontfix). A reader who engages is acting on false information.
2. **Evidence chain contaminated downstream.** Anything that cited the citation (machine files, other READMEs, review reports) inherits the rot without knowing it. Stale references compose.

A third variant observed the same day, from the reviewer side: a reviewer cites "PR #2 and #4 exist in repo X" from partial memory; the repo actually holds #2, **#3 and #4**. Partial enumeration presented as complete enumeration is the same disease with a different organ — the citation omitted checking before citing.

## Why it is silent

The cited object changing state produces **no event in the citing document**. GitHub closes the issue; the README is a static file on another host; nothing bridges the two. The citation was true when written, which is exactly what makes it dangerous: every check that trusts "it was true then" passes, and the failure has no log, no alert, no diff.

Citations with state are *liabilities*, not facts. A fact ("SF-014 has a minimal reproduction") decays slowly; a state ("#33 is open") can decay in one day. Documents that treat the two identically accumulate rot at the speed of the fastest decaying thing they cite.

## Minimal reproduction

```bash
# Day 1: document cites a live issue
echo "see the open question in <repo>/issues/33" >> README.md
# Day 2 (elsewhere, by someone else): the issue is closed wontfix
# Day 24: reader follows the citation expecting an open discussion
# → finds a closed thread; the README has been wrong for 23 days
#   with zero warnings in the citing repo
```

Observed: three instances within one week (see Evidence). Expected with the fix: the citing doc either carries a re-check record or does not cite the state at all.

## Evidence（三个实立例，全部一手核实）

| # | 引用方 | 被引对象 | 写入时 | 实查时 | 亚型 |
|---|---|---|---|---|---|
| 1 | `lgd-glossary/README.md` "opened as an open question" | `FG-TIDA/themes#33` | 2026-10-01 | closed（2026-10-02，wontfix） | 腐烂型 |
| 2 | `FG-TIDA/use-cases` README 提交索引表 | 本仓 use-case #14（SynomosAI/MedXpert） | 2026-10 初 | #14 已 CLOSED（2026-10-05，**labels=[]——无任何标签的静默关单**，实查 API 返回空标签数组） | 腐烂型 |
| 3 | 外审侧回执 "PR #2、#4 已开" | `FG-TIDA/wg1-ra-aai` PR 列表 | 2026-10-23 | 实为 #2/#3/#4 三个 | 残缺型 |

**Instance #2 note**: the maintainer closed #14 leaving *zero labels* — not even a closing marker. The README index (line 21, verified 2026-10-23) still lists it. This makes instance #2 more typical than #1: the rot happened with no trace at either end.

## Subtypes（v1.1，按外审意见分型——药不同）

| 亚型 | 机理 | 实例 | 药 |
|---|---|---|---|
| **腐烂型 rot** | 写入时正确；其后被引对象状态变化，引用未跟进 | #1、#2 | 复查周期（Fix §2）+ linter 状态比对（Fix §3） |
| **残缺型 defect** | 写入时即不完整/不正确——枚举不全、行号错、版本记错 | #3 | 引用当时全量拉源（自查 §4；写入流程拉源，不靠记忆） |

混型的代价：残缺型套用复查周期等于拿错药——复查只会重复确认一个从写入那天起就错的数字。两型必须分诊。

## Self-check

**对全部引用（两型通用）**：

1. **Does the sentence assert a state, or a fact?** States use verbs like *is open / is live / is current / has been submitted*. Those need a check date or no assertion.
2. **Would the sentence still be true if the cited object changed yesterday?** If the document cannot answer that, it is asserting state without liability control.

**对腐烂型（写时正确、其后会变）**：

3. Does the citation carry (a) status-at-citation, (b) a re-check cadence **matched to the volatility tier** (see below), (c) a fallback wording if the state flipped? Missing any one = this bug.

**对残缺型（枚举/计数/行号）**：

4. **Was the enumeration pulled from the source at writing time, or from memory?** Memory-written enumerations are suspect by default. The pull must be *complete* (list the whole set, not spot-check members) — instance #3 failed precisely because a spot-check of #2/#4 was presented as the full list.

## Volatility tiers & re-check cadence（v1.1，按外审意见分级——防告警洪水）

One-size-fits-all re-check cadence produces alert floods; flood warnings get muted wholesale, and alert fatigue is a sibling of silent failure — the anti-rot tool must not rot first. Cadence follows the cited object's volatility:

| Tier | 被引对象 | 变化速度 | 复查周期 |
|---|---|---|---|
| **高** | issue/PR 状态、分支 HEAD、"当前最新版"措辞 | 以天计 | 以周计（如 14 天）；或事件触发（发布前、投稿前强制查） |
| **中** | 版本号、文件行号、目录结构、commit hash | 以月计 | 以月计（如 90 天） |
| **低** | 已发布标准（RFC/ITU-T Rec.）、存档 DOI、正式公报记录 | 以年计或不更新 | 免例行复查；仅在上下游迁移时顺手验 |

写入 `cites.recheck` 时必须带 tier 标注；linter 按 tier 取默认周期，条目可覆盖但不得低于 tier 下限。

## Scope of coverage（v1.1，按外审意见写明射程——防「全生态已防住」错觉）

This catalog's tooling has a bounded reach, and the entry must not overstate it:

- **linter（Fix §3）覆盖：治理面资产**——ecosystem.json 登记的 flagship 与 support 层、其派生视图与 llms.txt。
- **linter 不覆盖：长尾层**（longtail 登记、散篇文档、外部站点页面）。那里的状态引用只能靠 Fix §1 兜底。
- **硬规则：旗舰与支撑层走 linter；长尾层只许引事实、不许裸引状态。** 若做不到引事实，就把该引用降级为「截至 YYYY-MM-DD 的快照」并停止宣称其为现状。
- 任何引用本条目的材料不得写成「全生态已防住此类失效」——正确措辞：「治理面有 linter 拦截，长尾面靠写作纪律兜底」。清单外未扫描，不得宣称全覆盖。

## Fix

Three layers, strongest first.

**1. Cite facts, not states — or date-stamp the state.** Rewritable in one line:

```markdown
<!-- not this -->
opened as an open question in <repo>/issues/33

<!-- this: fact, survives any state change -->
raised in <repo>/issues/33 (2026-10-01); closed as wontfix 2026-10-02 — see the
thread for the maintainer's stated reasons
```

If the status matters, the closure *is* the finding. A citation that survives its subject's state change carries more information, not less.

**2. Attach a re-check trigger to any unavoidable state citation.** Machine-readable at minimum:

```yaml
cites:
  - ref: "FG-TIDA/themes#33"
    state_at_citation: open
    tier: high                    # volatility tier (see table) — required
    recheck: 14d                  # default per tier; may override upward only
    fallback: "closed without adoption (wontfix, 2026-10-02)"
```

The fallback pre-writes the post-rot wording, so updating is a one-line flip instead of a rewrite. The tier drives the default cadence — high volatility gets weeks, medium gets months, low gets none.

**3. Linter: pull cited states at build time and diff.** The catalog's self-testing linter gains one rule: extract issue/PR/DOI/release links, resolve their current state, compare against `state_at_citation`; emit a finding on mismatch. Where the network is unavailable, degrade to "citation older than N days and never re-verified" instead of silently passing. Scope: governance-plane assets only (see Scope of coverage).

| Negative control | Expected result |
|---|---|
| Cite a closed issue as "open question" (variant of instance #1) | linter **flags** the mismatch |
| Cite the same issue with closure date included (fix style) | linter passes; sentence stays true after closure |
| Enumeration written from memory (instance #3 style) | self-check question 4 triggers; enumeration re-pulled before citing |

## Related

- `SF-013` — sibling temporal inversion: there the environment serves the stale copy; here the citation *is* the stale copy
- `SF-008` — both let a once-true artifact stand in for a current check
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § E

---

## 中文要点

- **一句话**：文档引用外部对象的**状态**（议题开闭、版本、链接存活）却不带复查机制；被引方状态一变，引用静默失效、语义反转，且无任何告警。
- **为什么会静默**：被引对象变化时，引用方**不产生任何事件**——议题在别人那里关掉，README 是另一台主机上的静态文件，中间没有桥。引用写入那一刻是真的，这恰是危险所在：一切「当时为真」的检查都会通过。
- **三个实立例（一周内，全部一手核实，分两亚型）**：
  - **腐烂型**：① glossary 把已 wontfix 关闭的 themes#33 当「开放问题」引了 21 天；② 我方 use-cases README 索引表（第 21 行，10-23 实查）仍列已关闭的 #14——维护者关单时**一个标签都没留**（API 实查 labels=[]），连关的姿势都没留下，比 ① 更典型。
  - **残缺型**：③ 外审侧引用 wg1 PR「#2、#4」，漏了 #3——抽查当全量，写入那天起就是错的。外审侧自证一例并认账。
  - **分型的意义（外审意见）**：两型药不同。残缺型套用复查周期等于拿错药——复查只会重复确认一个从写入起就错的数字。
- **自查（v1.1 分组）**：通用两问——这句是陈述事实还是状态？被引对象昨天变了这话还成立吗？腐烂型加一问——是否带「写入时状态 + 匹配易变级的复查周期 + 失效替代口径」三件套？残缺型加一问——枚举是写入当时全量拉源还是凭记忆？（抽查 #2/#4 冒充全量正是实例 ③ 的错法。）
- **易变性分级与复查周期（v1.1，外审意见）**：议题/PR 状态是**高易变**（复查以周计或事件触发）；版本号/行号是**中**（以月计）；已发布标准/存档 DOI 是**低**（免例行复查）。一刀切周期只会产出告警洪水，洪水的下场是被整体静音——告警疲劳是静默失效的近亲，别让防腐工具自己腐掉。
- **适用范围（v1.1，外审意见）**：linter 只覆盖治理面资产（flagship + support 层及派生视图）；**长尾层只许引事实、不许裸引状态**。任何引用本条的材料不得写成「全生态已防住」——正确措辞：「治理面有 linter 拦截，长尾面靠写作纪律兜底」。
- **修法三层（由强到弱）**：① **引事实不引状态**——把关闭本身写进去（「10-01 提出、10-02 wontfix 关闭」），引用反而比原句信息更多；② 避不开的状态引用附 `cites` 元数据（state_at_citation / **tier** / recheck / fallback，失效口径预写好，更新时改一行）；③ linter 构建时拉取被引状态比对，断网时降级为「超 N 天未复验即报告」，不得静默通过。
- **与 SF-013 的关系**：同为时间倒置。SF-013 是环境把旧副本端给正确的逻辑；本条是引用本身成为旧副本，且环境永远不会推送更新。
