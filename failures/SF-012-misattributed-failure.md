# SF-012 · Misattributed failure

**Status**: `stable` ｜ **Family**: D · Drifting Oracle ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** The check fails — and blames the wrong cause, so the real defect is never fixed.

## Symptom

A gate reports `FAIL`, a human reads the message, investigates the named cause, finds nothing wrong, and eventually dismisses the gate as flaky.

```
FAIL: content drift detected in record 42
```

The investigator checks record 42's content against the source: identical. Closes the ticket. The real problem — two entries sharing an id, the earlier one silently shadowed — is still there and is never mentioned, because the check found *a* discrepancy and stopped at the first plausible label.

Two mechanisms produce this, both common:

**1. First-match reporting.** The check has multiple failure conditions; it reports the first one it detects and returns, so later (or more fundamental) findings never surface.

**2. Substring and prefix matching.** The detector's comparison is weaker than the concept it claims to test:

| Detector | Intended | Actually matches |
|---|---|---|
| `"org" in text` | the field `org` | `organizer`, `organisation` |
| `"role" in text` | the field `role` | `getByRole`, `roleTitle` |
| `REQ-2.2.` prefix | requirement `REQ-2.2` | `REQ-2.21`, `REQ-2.22` — and misses nothing but reports wrongly |
| `value in line` (substring) | exact value `x` | `xyz`, `prefix_x` |

In the substring cases the check is *wrong in both directions*: it flags things that are fine and misses things that are not, while reporting a single confident cause.

## Why it is silent

The failure is **loud**, which is exactly what makes it dangerous: it consumes the attention that would otherwise find the real defect. A loud wrong answer is worse than a quiet one, because it generates a plausible investigation that concludes "no problem".

This is the inverse of every other family in this catalog, and it is why the family exists: *the check went off, and that was the problem.*

## Minimal reproduction

```python
# intended: find the field named exactly "role"
MECH_FIELD = "role"
hits = [ln for ln in lines if MECH_FIELD in ln]

# line: "await page.getByRole('button').click()"
# → matched. Attributed as "uses the role field".
# The real finding (a missing `role:` field) is nowhere in the output.
```

Observed: `1 field usage attributed: role` — Expected after fix: `0 exact matches; 1 substring collision reported separately`

## Self-check

1. **Take the reported cause and verify it independently.** If the named cause is not actually broken, the attribution is wrong — and the real cause is still unknown.
2. **Audit every string comparison** for substring/prefix semantics where exact semantics are intended. Prefer token equality, parsed values, or anchored patterns (`\b` boundaries, `^...$`).
3. **Check for early return.** Grep the detector for `break` / `return` inside the finding loop — each one truncates the report.
4. **Look for a second, quieter signal.** Misattribution usually means two conditions are present and only one is reported.

## Fix

Make the comparison as strong as the claim, and report all findings rather than the first.

```python
import re

# anchored, word-bounded exact match — not substring
EXACT = re.compile(r"(?<![\w-])role(?![\w-])")
hits = [ln for ln in lines if EXACT.search(ln)]

# and never stop at the first finding
findings = []
for record in records:
    findings.extend(detect_all(record))     # plural, exhaustive
for f in sorted(findings, key=severity_key):
    print(f)
```

Also worth stating explicitly: **do not use `in` for identity.** `in` answers "does this substring occur", which is almost never the question a validator means to ask.

| Negative control | Expected result |
|---|---|
| Introduce an exact-match violation | reported as an **exact** match |
| Introduce only a substring collision (`getByRole`) | reported separately as a collision, **not** as a field usage |
| Introduce two violations | **both** reported, not just the first |

## Related

- `SF-011` — the mirror image: an oracle that stopped failing; here it fails and misinforms
- `SF-006` — a mis-scoped frame hides findings; a mis-attributed label misdirects them
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § D

---

## 中文要点

- **一句话**：检查**报警了**，但**归错了因** —— 于是真正的问题永远没人修。
- **为什么会静默**：它的失败是**响的**，而这正是危险所在：它消耗掉了本该用来发现真问题的注意力。**响亮但错误的答案，比安静的更糟**，因为它会生成一次看起来合理的排查，最后得出"没问题"。
- **怎么自查**：① 拿到它报的原因，**独立验证一遍** —— 报的原因若不成立，归因就是错的，而真因还未知；② 审计每一处字符串比较（该精确的地方是否用了子串/前缀）；③ 找 `break` / `return` —— 每个都在截断报告；④ 找"更安静的第二信号"。
- **修法要点**：**别用 `in` 做身份判断**（`in` 回答的是"这个子串出现过吗"，而校验器想问的几乎从来不是这个）；改用带词边界的锚定匹配；**报告全部发现而不是第一个**。
- **反向对照**：造一个精确匹配违规 → 按"精确"报出；只造子串碰撞（`getByRole`）→ 单独报为碰撞、**不得**报成字段使用；造两处违规 → **两处都报**。
