# SF-013 · Stale copy contaminates the check

**Status**: `stable` ｜ **Family**: E · Process & Environment ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A pre-change backup is written inside the directory being checked, so the check reads an old copy as fresh input.

## Symptom

A gate scans a directory tree for violations. It reports an enormous number of findings — hundreds — in files you already fixed.

```
426 violations found
```

You open the first one. The file is fine. You open the second. Fine. Then you notice the path:

```
project/src/module.py.bak_20260918        ← yesterday's pre-fix copy
project/src/module.py.bak_20260919
project/.backup/module.py
```

The gate scanned **the backups**. Every fix you made is present in the live file and absent from the backup, so the backup looks like a violation — and there are more backups than there are files.

Two distinct harms compound:

1. **False positives** bury the real findings. A 426-item report contains no information.
2. **Temporal inversion.** The backup is a *correct record of the past*. Reporting it as a current defect inverts its meaning.

A related variant: `sed -i` on a CRLF file converts all line endings to LF, which a "≥50% of lines changed" heuristic reads as a mass deletion — the whole file is reported as removed content. Here the check is correct about what it sees and wrong about what it means.

## Why it is silent

The check is behaving correctly *for the input it was given*. Nothing in the pipeline distinguishes "the working tree" from "the directory". `find`, `glob` and `os.walk` do not know the difference, and the backup was written inside the tree because that is where the file was.

The environment is lying to correct logic — the signature of Family E. Reproduction is the way to confirm: run the gate on a clean checkout and it passes; run it where backups exist and it floods.

## Minimal reproduction

```bash
# backup placed next to the file it backs up
cp src/module.py src/module.py.bak_$(date +%Y%m%d)
# ... apply a fix to src/module.py ...

# gate scans the tree
python check.py --root src
# → reports the violations that only the .bak copy still contains
```

Observed: hundreds of violations, all in `*.bak*` paths — Expected after fix: zero, with backup paths excluded by construction

## Self-check

1. **Are any findings in paths that are not source?** Group the report by path pattern. A cluster in `.bak`, `_backup`, `~`, `.orig`, `.tmp` or a timestamped directory is this bug.
2. **Does the count change between a clean checkout and the working tree?** If yes, the difference is environmental.
3. **Is the check's file selection explicit?** If it globs a tree rather than an allow-list, it selects whatever happens to be there.

## Fix

Three layers, strongest first.

**1. Keep backups outside the checked tree.** This is the real fix. A backup inside the tree being audited is contaminated evidence by construction.

```bash
# not this:
cp src/module.py src/module.py.bak

# this:
cp src/module.py "$BACKUP_ROOT/$(date +%Y%m%d)/module.py"
```

**2. Make the gate's selection an allow-list, not a tree glob.** Prefer "these paths" over "everything under here".

```python
TRACKED = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
targets = [p for p in TRACKED if p.startswith("src/")]
```

Using version control's file list is better than a hand-maintained allow-list, and much better than `os.walk`.

**3. Add an ignore list as a backstop**, with the caveat that it is a heuristic, not a guarantee.

```python
IGNORE = re.compile(r"(\.bak|\.orig|~\d*$|/\.backup/|/\d{8}-/)")
targets = [p for p in targets if not IGNORE.search(p)]
```

And when a mass-change heuristic fires (the CRLF variant): prefer **byte-level replacement that preserves line endings** over line-oriented tools, or normalise line endings explicitly before comparing.

| Negative control | Expected result |
|---|---|
| Place a `.bak` file with a known violation inside the tree | gate **does not** report it |
| Place the same violation in a tracked source file | gate **does** report it |
| Run on a clean checkout then on the working tree | identical counts |

## Related

- `SF-011` — both produce a flood of false findings; here the cause is environmental
- `SF-014` — the other Family E entry: environment state, not files
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § E

---

## 中文要点

- **一句话**：改前备份写在**被检查的目录里**，于是门禁把旧副本当成了新输入，一次报出几百条"违规"。
- **为什么会静默**：门禁对**给它的输入**而言是完全正确的 —— `find`／`glob`／`os.walk` 分不清"工作树"与"这个目录"。环境对正确的逻辑说了谎（E 族的标志）。两重叠加伤害：① 数百条假阳性把真问题埋掉；② **时间倒置** —— 备份是**过去的正确记录**，把它报成当前缺陷，语义被反转了。
- **怎么自查**：按路径分组看报告 —— 若一堆命中集中在 `.bak`／`_backup`／`~`／`.orig`／时间戳目录，就是这条；对比"干净检出"与"当前工作树"的计数，不一致的差值就是环境造成的。
- **修法要点**：三层，由强到弱 —— ① **备份一律落仓外**（真正的修法）；② 门禁的取文件方式改成**白名单**（`git ls-files` 优于 `os.walk`）；③ 忽略列表只作兜底。CRLF 变体：用**保持行尾的字节级替换**，别用面向行的工具。
- **反向对照**：往树里放一个含违规的 `.bak` → 不得报出；把同一违规放进被跟踪的源文件 → 必须报出。
