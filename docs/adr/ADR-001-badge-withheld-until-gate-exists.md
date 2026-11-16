# ADR-001: Withhold the CI badge until a run exists

- Status: Accepted (decision made before the gate existed; recorded 2026-11-17)
- Decided by: maintainer
- Affects: `README.md` badges, `docs/start-here.md`

## Context

The repository publishes a catalog of validations that pass while nothing is checked. Its own README carries status badges. A CI badge is a claim: it asserts that a validation run exists and that it currently passes.

For a period, the gate existed as a local script (`tools/check-catalog.py`) but no workflow ran it. A badge pointing at a workflow that does not exist renders as grey or broken — and worse, a badge minted from a hand-edited URL renders as **passing** while nothing has run.

That is, precisely: a validation claiming to pass while nothing is being checked. The failure mode this catalog exists to document, applied to the catalog itself.

## Decision

The CI badge stays withheld until a workflow that actually runs the check exists and has produced a run. The README carries a comment recording why, so the delay is a stated decision rather than an oversight. A second badge pointing at the command a reader can run locally is used in the meantime — because that claim is verifiable at any moment by anyone.

## Consequences

**Good.** Every badge on the README now points at something that resolves. The repository does not demonstrate its own defect class in its own header.

**Costs.** While the gate is local-only there is no passive signal that the check passes; a reader must run it. That is a real cost and it was accepted.

**Rule derived from this.** A status indicator may be published only after the thing it indicates has executed at least once, and must point at a run that resolves. Corollary: when a check is added, the badge is added after its first green run, not with it.

## Alternatives rejected

1. **Publish the badge with a placeholder URL.** Rejected: it renders as a claim, and a claim that resolves to nothing is worse than no claim.
2. **Publish a static "passing" badge.** Rejected: a hand-drawn badge cannot fail, so it carries no information.
3. **Publish nothing and stay quiet about it.** Rejected: a silent absence is the failure mode itself. The comment makes the absence legible.

## Related

- `README.md` — the comment above the badge block
- `ARCHITECTURE.md` — invariant 1, absence must be reported as failure
- `tools/check-catalog.py --selftest` — the same principle applied to rules

---

# ADR-001：在真实运行存在之前，不发布 CI 徽章

- 状态：已采纳（决定作出于门禁存在之前，2026-11-17 记录）
- 决定人：维护者
- 影响：`README.md` 徽章、`docs/start-here.md`

## 背景

本仓发布的是"检查通过了但什么都没在检查"的失效目录，而 README 上挂着状态徽章。CI 徽章是一个**主张**：它断言存在一次验证运行，且当前通过。

有一段时间，门禁只是一个本地脚本（`tools/check-catalog.py`），没有任何 workflow 在跑它。指向不存在 workflow 的徽章会渲染成灰色或坏图——更糟的是，手工拼 URL 造出来的徽章会渲染成**通过**，而实际什么都没跑。

这恰好就是：一次声称通过、却什么都没在检查的验证。本仓要记录的失效模式，落在了本仓自己头上。

## 决定

CI 徽章在"真的会跑这个检查的 workflow 存在、并已产出一 runs"之前不发布。README 里保留一段注释记录原因，让这段延迟是**已声明的决定**，而不是疏漏。期间改用一枚指向读者**当下就能自己跑**的命令的徽章——因为那个主张任何人随时可核。

## 后果

**收益**：README 上每枚徽章都指向能解析的东西；仓库不再在自己的头部演示自己的缺陷类。

**代价**：门禁只在本地时，没有"检查正在通过"的被动信号，读者必须自己跑。这是真实成本，已接受。

**由此得出的规则**：状态指示符只能在其所指之物至少执行过一次之后发布，且必须指向可解析的一次运行。推论：新增一项检查时，徽章在它第一次绿灯之后才加，而不是与它同时加。

## 已否决的方案

1. **用占位 URL 发布徽章**——否决：它渲染成主张，而解析不到东西的主张比没有主张更糟。
2. **发布静态"passing"徽章**——否决：手画的徽章不会失败，因此不携带任何信息。
3. **什么都不发、也不说话**——否决：静默的缺失正是那个失效模式本身；注释让缺失可被看见。
