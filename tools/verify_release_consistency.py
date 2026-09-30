#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_release_consistency.py — 统一发布一致性校验（仓发布物级门禁）

为什么存在
-----------
文档有 external-rights-gate（内容层），但 **仓发布物（canonical pin / git tag / 许可证）**
从未被任何门禁覆盖。本次（2026-09-30）就因此出现三向不一致：
  - README 写 canonical = v0.1.0 @ e977a04a
  - v0.1.0 git tag 实际指向 68f1f815583（≠ e977a04a）
  - e977a04a 快照自己的 README 又自指 82018d3c（已撤回版）
外加 set digest 在 README / INTEGRITY 两处写法不一（a5b9c7a7 vs c8abdecb）。

本脚本把"宣布 done"前的最后一道实体校验固化下来：README 与 INTEGRITY 的
canonical 引用必须一致、且指向一个真实存在且自洽的 tag；set digest 两处一致；
许可证 © 行与保留所有权利在位；已撤回的 82018d3c 不得再作为 canonical 引用。

用法
----
  python verify_release_consistency.py --repo-path . [--ref v0.1.0] [--repo owner/name]
  python verify_release_consistency.py --repo zhaoxinghua09-cell/silent-failure-catalog

退出码：0 = 一致；1 = 不一致（逐条打印 FAIL，不静默）。
"""
import argparse
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
    """只认两种明确写法，避免把历史 commit SHA 误当 set digest。

    - INTEGRITY.md 权威格式： `**Set digest (SHA-256)** | \`<64-hex>\``
    - README 显式 code-span： `set digest \`<hex>\``（要求 digest 紧跟在 'set digest' 后的反引号里）
    其余（如 "the set digest recorded in INTEGRITY.md" 后跟历史 SHA）一律不匹配 → 返回 None。
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
            return ("err", out.stderr.strip()[:120])
        import json
        obj = json.loads(out.stdout)
        sha = obj.get("object", {}).get("sha") or obj.get("sha")
        if not sha:
            return ("err", "no sha in ref")
        # 读该 commit 的 README
        rout = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/README.md?ref={sha}"],
            capture_output=True, text=True, timeout=30)
        if rout.returncode != 0:
            return ("err", rout.stderr.strip()[:120])
        robj = json.loads(rout.stdout)
        import base64
        rtext = base64.b64decode(robj["content"]).decode("utf-8", "replace")
        return extract_canonical(rtext)
    except Exception as e:  # noqa
        return ("err", str(e)[:120])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", default=".")
    ap.add_argument("--ref", default="v0.1.0")
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

    # 5) 远程 tag 自洽（可选）
    remote_note = ""
    if args.repo and not args.no_remote:
        rc = remote_canonical(args.repo, args.ref)
        if rc and rc[0] == "err":
            remote_note = f"  ⚠ 远程 tag 校验跳过（{rc[1]}）"
        elif rc and c_r and rc != c_r:
            fails.append(f"远程 tag {args.ref} 指向的快照 canonical={rc} ≠ 本地 canonical={c_r}")

    # 输出
    print("═ verify_release_consistency · --ref %s" % args.ref)
    checks = [
        ("README canonical", c_r),
        ("INTEGRITY canonical", c_i),
        ("README set digest", d_r),
        ("INTEGRITY set digest", d_i),
    ]
    for label, val in checks:
        print("  • %-22s %s" % (label, val if val else "（无）"))
    print("═ 远程 tag 校验：%s" % (remote_note or ("已比对" if (args.repo and not args.no_remote) else "未启用（--no-remote）")))

    if fails:
        print("═ 判定：❌ 不一致 ——")
        for f in fails:
            print("   ❌ " + f)
        sys.exit(1)
    print("═ 判定：✅ 一致（canonical 自洽、set digest 对齐、许可证在位）")
    sys.exit(0)


if __name__ == "__main__":
    main()
