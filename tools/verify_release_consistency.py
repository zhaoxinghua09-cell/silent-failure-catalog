#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""verify_release_consistency.py — 统一发布一致性校验（仓发布物级门禁）

为什么存在
-----------
文档有 external-rights-gate（内容层），但 **仓发布物（canonical pin / git tag / 许可证）**
从未被任何门禁覆盖。2026-09-30 就因此出现三向不一致：
  - README 写 canonical = v0.1.0 @ e977a04a
  - v0.1.0 git tag 实际指向 68f1f815583（≠ e977a04a）
  - e977a04a 快照自己的 README 又自指 82018d3c（已撤回版）
外加 set digest 在 README / INTEGRITY 两处写法不一（a5b9c7a7 vs c8abdecb）。

本脚本把"宣布 done"前的最后一道实体校验固化下来：README 与 INTEGRITY 的
canonical 引用必须一致、且指向一个真实存在且自洽的 tag；set digest 两处一致；
许可证 © 行与保留所有权利在位；已撤回的 82018d3c 不得再作为 canonical 引用。

2026-10-07 —— 本门禁自己被抓到两个盲区，同轮补上（见 CHANGELOG 0.1.1）：

  1) **不覆盖 content manifest**。canonical tag `v0.1.0` 的 `manifest.sha256` 与该 tag
     的树不一致（加第 6 门禁的那次提交没有重生成 manifest），而本脚本只做「文档 ↔ 文档」
     自洽，看不见「文档 ↔ 实体」的偏离 ⇒ 同一个 tag 上，`make-manifest.py --check` 报
     FAIL，本脚本报「✅ 一致」。两个"完整性"校验器对同一对象给出相反结论。
     补法：直接委派 `make-manifest.py --check`（复用单一实现，不重造第二套哈希逻辑）。

  2) **远程 tag 校验在 CI 里静默跳过**。它要调 `gh api`，而 workflow 没给 `GH_TOKEN`，
     runner 上 gh 未认证 ⇒ 每次走 err 分支打印「⚠ 跳过」后**仍判 ✅ 且 exit 0**。
     即本门禁的招牌能力（"tag 对象解析到自洽快照"）从未真正执行过 —— 正是本 catalog
     所命名的病（一个跑不起来却被记为通过的门禁），长在本门禁自己身上。
     补法：CI 注入 GH_TOKEN；且「声明了 canonical 锚却解析不到」= FAIL（不是跳过）。

  3) **gate 计数无人看管**（2026-10-07 同日补）。`AGENTS.md` 两处与 `index.md` 一处仍写
     「seven gates」，而 hook 当时已跑更多道 —— 计数散在多处、无单一真源、无门看管（rule 15
     形同虚设）。现新增检查：活文档里的 gate 数必须等于 `.githooks/pre-commit` 的 `run`
     调用数；史件（`CHANGELOG.md`、`docs/building-this-catalog.md`）排除，避免把"当时写了 N 道"
     误判为当前声明。

另：`--ref` 不再硬编码。2026-10-07 前三处调用都写死 `--ref v0.1.0`，改锚时必有一处漏改 ——
硬编码版本号本身就是第二个真源。现改为从 README 的 canonical 推导。

用法
----
  python verify_release_consistency.py --repo-path . [--ref v0.1.1] [--repo owner/name]
  python verify_release_consistency.py --repo zhaoxinghua09-cell/silent-failure-catalog

退出码：0 = 一致；1 = 不一致（逐条打印 FAIL，不静默）。
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def extract_canonical(text):
    """返回 (kind, value) 或 None。kind ∈ {'tag','sha'}。"""
    if text is None:
        return None
    # 优先匹配「release tag `vX`」/「canonical ... `vX`」
    m = re.search(r"release tag\s+`?(v[0-9][0-9.]*)`?", text, re.IGNORECASE)
    if m:
        return ("tag", m.group(1))
    m = re.search(r"canonical (?:citation|pin)[^\n`]*?`?(v[0-9][0-9.]*)`?", text, re.IGNORECASE)
    if m:
        return ("tag", m.group(1))
    # 否则匹配 commit <40-hex>
    m = re.search(r"commit\s+`?([0-9a-f]{40})`?", text, re.IGNORECASE)
    if m:
        return ("sha", m.group(1))
    return None


def extract_set_digest(text):
    r"""只认两种明确写法，避免把历史 commit SHA 误当 set digest。

    - INTEGRITY.md 权威格式： `**Set digest (SHA-256)** | \`<64-hex>\``
    - README 显式 code-span： `set digest \`<hex>\``（要求 digest 紧跟在 'set digest' 后的反引号里）
    其余（如 "the set digest recorded in INTEGRITY.md" 后跟历史 SHA）一律不匹配 → 返回 None。

    该 docstring 为 raw 串：`\`` 在普通串里是无效转义，Python 3.12 会告
    SyntaxWarning（2026-10-07 于 CI 日志实证），`-W error` 下直接失败。
    """
    if text is None:
        return None
    m = re.search(r"Set digest \(SHA-256\)\*\*\s*\|\s*`([0-9a-f]{64})`", text)
    if m:
        return m.group(1).lower()
    m = re.search(r"set digest\s+`([0-9a-f]{8,64})`", text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def remote_canonical(repo, ref):
    """用 gh api 取 tag 目标 commit，并读其 README 的 canonical。返回 (kind,value) 或 None/('err',msg)。"""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/git/refs/tags/{ref}"],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return ("err", out.stderr.strip()[:160])
        obj = json.loads(out.stdout)
        target = obj.get("object", {})
        sha = target.get("sha") or obj.get("sha")
        if not sha:
            return ("err", "no sha in ref")
        # 附注 tag（annotated）指向的是 tag 对象而非 commit；先解引用，否则下面按 sha 取
        # README 会取错东西、变成假 FAIL。本仓切的是轻量 tag（v0.1.0 即其一），所以今天
        # 无影响 —— 但"因为没人会那么做"不是理由，正是本 catalog 记的那类假设。
        if target.get("type") == "tag":
            tout = subprocess.run(
                ["gh", "api", f"repos/{repo}/git/tags/{sha}"],
                capture_output=True, text=True, timeout=30)
            if tout.returncode != 0:
                return ("err", tout.stderr.strip()[:160])
            sha = json.loads(tout.stdout).get("object", {}).get("sha") or sha
        # 读该 commit 的 README
        rout = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/README.md?ref={sha}"],
            capture_output=True, text=True, timeout=30)
        if rout.returncode != 0:
            return ("err", rout.stderr.strip()[:160])
        robj = json.loads(rout.stdout)
        rtext = base64.b64decode(robj["content"]).decode("utf-8", "replace")
        return extract_canonical(rtext)
    except Exception as e:  # noqa
        return ("err", str(e)[:160])


def manifest_check(repo_path):
    """委派 tools/make-manifest.py --check。返回 (exit_code, output)。

    为什么是委派而不是重写：manifest 的哈希规则（域分隔串、路径排序、排除集）只能有一份
    实现。第二份实现会自己漂移，而两份"权威"对不上时读者无法判断信哪一个 —— 这正是
    v0.1.0 上发生的事（两个校验器对同一 tag 给出相反结论）。
    """
    script = os.path.join(repo_path, "tools", "make-manifest.py")
    if not os.path.isfile(script):
        return (1, "tools/make-manifest.py is missing — a gate that is not there is not a gate")
    p = subprocess.run([sys.executable, script, "--check", "--root", os.path.abspath(repo_path)],
                       capture_output=True, text=True, timeout=180)
    return (p.returncode, (p.stdout + p.stderr).strip())


# 会「以散文形式声明当前 gate 数」的活文档。CHANGELOG.md 故意排除：它是历史记录，
# 「某次提交当时写了八道门」是对过去为真的陈述，不是当前计数声明 —— 把它算进来会让
# 门自己误报。这也正是「计数只许出现在一处」（rule 15）要区分的：活件 vs 史件。
GATE_COUNT_DOCS = ["AGENTS.md", "index.md", "README.md", "docs/start-here.md",
                   "CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md",
                   ".github/workflows/gates.yml"]
# The word list is the single source for the pattern below. A key the regex cannot match is a
# dead branch: "three|four|five|six" were once registered here but missing from the pattern, so
# the contributor-facing PR template said "four gates" and no gate saw it.
_COUNT_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_COUNT_RE = re.compile(
    r"\b(%s|[0-9]+)\s+gates?(?![\w-])"
    % "|".join(sorted(_COUNT_WORDS, key=len, reverse=True)),
    re.IGNORECASE)


def gate_count(repo_path):
    """gate 数，读自唯一真源 `.githooks/pre-commit`（数 `run "<label>" ...` 调用）。

    为什么数调用而不认字面量：hook 是规格，其它一切提及都必须与它一致。2026-10-07 审计
    发现两处活文档仍写「seven gates」，而 hook 实际跑了九道 —— 没有任何门在看这个，
    于是 rule 15（计数只许出现一处）形同虚设。本检查就是给 rule 15 装上牙齿。
    """
    text = read(os.path.join(repo_path, ".githooks", "pre-commit"))
    if text is None:
        return None
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith('run "'))



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", default=".")
    ap.add_argument("--ref", default=None,
                    help="canonical 引用（tag 名）；省略则从 README 推导（不硬编码版本号）")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                    help="owner/name；提供则额外校验 tag 指向的快照自洽")
    ap.add_argument("--no-remote", action="store_true")
    args = ap.parse_args()

    rp = args.repo_path
    fails = []

    readme = read(os.path.join(rp, "README.md"))
    integ = read(os.path.join(rp, "INTEGRITY.md"))
    lic = read(os.path.join(rp, "LICENSE"))
    lic_c = read(os.path.join(rp, "LICENSE-CONTENT"))

    # 1) README / INTEGRITY canonical 一致性
    c_r = extract_canonical(readme)
    c_i = extract_canonical(integ)
    if c_r is None:
        fails.append("README.md 未声明 canonical pin")
    if c_i is None:
        fails.append("INTEGRITY.md 未声明 canonical pin")
    if c_r and c_i and c_r != c_i:
        fails.append(f"canonical 不一致：README={c_r} ≠ INTEGRITY={c_i}")

    # ref：省略 --ref 时从 README canonical 推导（消除硬编码版本号这一漂移源）
    ref = args.ref or (c_r[1] if (c_r and c_r[0] == "tag") else "")

    # 2) set digest 两处一致
    d_r = extract_set_digest(readme)
    d_i = extract_set_digest(integ)
    if d_r and d_i and d_r != d_i:
        fails.append(f"set digest 不一致：README={d_r} ≠ INTEGRITY={d_i}")

    # 3) 许可证
    if lic and "©" not in lic and "Copyright" not in lic:
        fails.append("LICENSE 缺少 © / Copyright 行")
    if lic_c:
        if not re.search(r"All rights reserved|保留所有权利", lic_c, re.IGNORECASE):
            fails.append("LICENSE-CONTENT 缺少「保留所有权利」声明")
        # 已撤回的 CC BY 4.0 若作为「现行」许可出现则错；允许在 superseded/withdrawn 语境
        if re.search(r"CC BY 4\.0", lic_c):
            ctx = re.findall(r".{40}CC BY 4\.0.{40}", lic_c, re.IGNORECASE)
            bad = [c for c in ctx if not re.search(r"supersed|withdraw|earlier|撤回|作废|已撤", c, re.IGNORECASE)]
            if bad:
                fails.append("LICENSE-CONTENT 在非撤回语境出现 CC BY 4.0（应为保留所有权利）")

    # 4) 已撤回 commit 不得再作 canonical 引用
    for name, text in (("README.md", readme), ("INTEGRITY.md", integ)):
        if text and "82018d3c" in text:
            # 仅在 canonical/cite 语境出现才算错；纯历史说明允许
            seg = [s for s in re.split(r"\n\s*\n", text) if "82018d3c" in s]
            for s in seg:
                if re.search(r"canonical|cite|citation|引用", s, re.IGNORECASE) and \
                   not re.search(r"supersed|withdraw|earlier|撤回|作废|已撤|must not be cited", s, re.IGNORECASE):
                    fails.append(f"{name} 在 canonical/cite 语境引用了已撤回的 82018d3c")
                    break

    # 5) content manifest（文档 ↔ 实体）—— 2026-10-07 新增覆盖
    mm_code, mm_out = manifest_check(rp)
    if mm_code != 0:
        fails.append("content manifest 与该树不一致（本门禁此前完全不看 manifest，"
                     "v0.1.0 就是这样带着过期 manifest 发布的）")

    # 6) gate 计数一致性（rule 15 —— 计数只许出现在一处）
    # 本节的失败单独收集：摘要行必须看本节的结论，不能只看「真源读到了没有」。
    # 2026-10-08 实证（D-023）：`.github/workflows/gates.yml` 当时写着 "five gates"，
    # 本节判 ❌，摘要行却仍打印「✅ 活文档与真源一致（15 道）」—— 摘要说绿、判定说红，
    # 只看摘要的读者（或解析日志的下游）会得到相反的结论。这与 v0.1.0 那次
    # 「门打印 ✅ 并 exit 0」是同一个病，只是换到了摘要行上。
    count_fails = []
    n_gates = gate_count(rp)
    if n_gates is None:
        count_fails.append(".githooks/pre-commit 不存在 —— 无法确定 gate 数（真源缺失）")
    else:
        for name in GATE_COUNT_DOCS:
            text = read(os.path.join(rp, name))
            if text is None:
                # a listed document that cannot be read is a failure, not a skip (rule 12)
                count_fails.append("%s：被列为计数受检文件却读不到（rule 12：跑不起来的检查=失败）"
                                   % name)
                continue
            for m in _COUNT_RE.finditer(text):
                tok = m.group(1).lower()
                val = int(tok) if tok.isdigit() else _COUNT_WORDS.get(tok)
                if val is not None and val != n_gates:
                    count_fails.append("%s：声明 %s gates，但真源 .githooks/pre-commit 有 %d 道"
                                       "（rule 15：计数只许出现在一处）" % (name, tok, n_gates))
    fails.extend(count_fails)

    # 7) 远程 tag 自洽
    remote_note = "未启用（无仓上下文或 --no-remote）"
    if args.repo and not args.no_remote:
        if not ref:
            fails.append("无法确定 canonical tag：README/INTEGRITY 未声明，且未提供 --ref")
            remote_note = "未执行（ref 未知）"
        else:
            rc = remote_canonical(args.repo, ref)
            if rc and rc[0] == "err":
                # 「跑不起来」不是「通过」。2026-10-07 实证：CI 缺 GH_TOKEN，这里一直
                # 静默跳过，门禁仍打印 ✅ 并 exit 0 —— 本 catalog 所命名的病。
                fails.append(f"远程 tag {ref} 无法解析：{rc[1]}")
                remote_note = "❌ 无法解析（声明了锚就必须能解析到它）"
            elif rc and c_r and rc != c_r:
                fails.append(f"远程 tag {ref} 指向的快照 canonical={rc} ≠ 本地 canonical={c_r}")
                remote_note = "❌ 不一致"
            else:
                remote_note = f"已比对（{args.repo} @ {ref}）"

    # 输出
    print("═ verify_release_consistency · --ref %s" % (ref or "（未声明）"))
    checks = [
        ("README canonical", c_r),
        ("INTEGRITY canonical", c_i),
        ("README set digest", d_r),
        ("INTEGRITY set digest", d_i),
    ]
    for label, val in checks:
        print("  • %-22s %s" % (label, val if val else "（无）"))
    print("─ content manifest：%s" % ("✅ 与该树一致" if mm_code == 0 else "❌ 与该树不一致"))
    if mm_code != 0:
        for line in mm_out.splitlines():
            print("      " + line)
    if n_gates is None:
        count_note = "❌ 真源 .githooks/pre-commit 缺失"
    elif count_fails:
        count_note = "❌ 活文档与真源不一致（真源 %d 道）" % n_gates
    else:
        count_note = "✅ 活文档与真源一致（%d 道）" % n_gates
    print("─ gate 计数：%s" % count_note)
    print("═ 远程 tag 校验：%s" % remote_note)

    if fails:
        print("═ 判定：❌ 不一致 ——")
        for f in fails:
            print("   ❌ " + f)
        sys.exit(1)
    print("═ 判定：✅ 一致（canonical 自洽、manifest 与该树一致、set digest 对齐、许可证在位）")
    sys.exit(0)


if __name__ == "__main__":
    main()
