#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""prepare.py -- put the tree into the one state the hook can pass, in one command.

Why this exists
---------------
The gates in `.githooks/pre-commit` are correct and every one of them can fail.
What they cannot do is run themselves in the right order relative to *editing*.
On 2026-10-08 three write-then-verify loops cost this repository two extra
rounds each, because the ordering was mine and the ordering was wrong:

  * `manifest.sha256` was regenerated, and then a file it covers was edited.
    The manifest went stale; `make-manifest --check` failed inside the hook.
  * A text-mode write turned `docs/defect-ledger.json` into CRLF. Gate 13 reads
    the **index**, so the slip stayed invisible until the file was staged.
  * Both were caught -- by the hook, on the *next* run. Being caught is fine.
    Needing a second run in order to be caught is the defect.

`prepare.py` removes the second run by fixing the order: normalise, regenerate,
stage, then verify once. It is idempotent, so running it twice is harmless, and
it never commits -- the commit stays a deliberate act with a written message.

The rule this file obeys
------------------------
It is **not** a gate and must never be added to `.githooks/pre-commit`: it calls
the hook, so listing it there would recurse. It lives beside the gates because
it answers "which one do I run first", and that answer belongs next to the
question it answers.

Usage
-----
    python tools/prepare.py              # normalise, regenerate, stage, verify
    python tools/prepare.py --check      # verify only; change nothing
    python tools/prepare.py --selftest   # prove the ordering is load-bearing

Exit code is 0 only when the full gate list passes.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# A recursion sentinel. The docstring says this tool must never be listed in
# `.githooks/pre-commit`, because it calls that hook. A sentence in a docstring
# is not a guard -- the run where someone lists it anyway looks exactly like the
# run where nobody did, except it hangs. So the rule is executable: when this
# tool calls the hook it exports the variable, and when it starts it refuses if
# the variable is already set.
SENTINEL_ENV = "PREPARE_ACTIVE"

# Extensions known to be binary. A suffix list alone is a guard with a hole --
# it misses every container format nobody thought to list (.docx, .xlsx, .jar,
# .whl, .epub are all zip). So the list is only a fast path; the real test is
# `_looks_binary`, which asks the bytes.
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2",
    ".ttf", ".otf", ".zip", ".gz", ".tgz", ".7z", ".exe", ".dll", ".so",
    ".pyc", ".bin", ".sqlite", ".db",
}

NUL_PROBE_BYTES = 8192


def _looks_binary(data: bytes) -> bool:
    """A NUL byte in the first 8 KiB means not text. This is what git uses."""
    return b"\x00" in data[:NUL_PROBE_BYTES]


def _run(cmd, timeout=600, cwd=None, env=None):
    """Run a command; never raise. Returns (rc, combined output)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        return p.returncode, (p.stdout + p.stderr).rstrip()
    except FileNotFoundError as exc:
        return 127, "not found: %s" % exc
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout


def tracked_files(repo):
    rc, out = _run(["git", "ls-files", "-z"], cwd=repo, timeout=60)
    if rc != 0:
        raise RuntimeError("git ls-files failed rc=%d: %s" % (rc, out[:200]))
    return [f for f in out.split("\0") if f]


def normalize_eol(repo, log=sys.stdout):
    """Convert CRLF to LF in tracked text files. Bytes are otherwise untouched.

    This does not *mask* a CRLF problem, it removes it before the index can
    carry it. Gate 13 still runs, and still fails on anything that arrives
    CRLF some other way.
    """
    changed = []
    skipped_binary = []
    for rel in tracked_files(repo):
        path = repo / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.suffix.lower() in BINARY_SUFFIXES or _looks_binary(data):
            if b"\r\n" in data:
                skipped_binary.append(rel)
            continue
        if b"\r\n" not in data:
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n"))
        changed.append(rel)
    log.write("  [1/4] normalise CRLF->LF : %d file(s)%s\n"
              % (len(changed), (" " + ", ".join(changed[:5])) if changed else ""))
    if skipped_binary:
        # Reported, never silently skipped: a binary with CRLF is left alone on
        # purpose, and saying so is the difference between a decision and a bug.
        log.write("        left alone (binary, CRLF present): %s\n"
                  % ", ".join(skipped_binary[:5]))
    return changed


def regen_manifest(repo, log=sys.stdout):
    rc, out = _run([sys.executable, "tools/make-manifest.py"], cwd=repo, timeout=300)
    log.write("  [2/4] regenerate manifest : %s\n"
              % ("ok" if rc == 0 else "FAILED rc=%d %s" % (rc, out[-200:])))
    return rc == 0


def stage(repo, log=sys.stdout):
    # `git add -A` stages everything, including files a human would not have
    # chosen (a stray log, an editor backup). That is deliberate here -- the
    # gates should see the whole tree -- but a side effect that happens quietly
    # is a side effect nobody reviews. So it is printed, every time.
    rc, out = _run(["git", "add", "-A"], cwd=repo, timeout=120)
    if rc != 0:
        log.write("  [3/4] stage all changes  : FAILED %s\n" % out[:200])
        return False
    rc2, names = _run(["git", "diff", "--cached", "--name-status"], cwd=repo, timeout=60)
    rows = [r for r in names.splitlines() if r.strip()]
    log.write("  [3/4] stage all changes  : ok, %d path(s) in the index\n" % len(rows))
    for row in rows[:12]:
        log.write("        %s\n" % row)
    if len(rows) > 12:
        log.write("        ... and %d more\n" % (len(rows) - 12))
    return True


def _sh():
    for name in ("sh", "bash"):
        found = shutil.which(name)
        if found:
            return found
    return None


def verify(repo, log=sys.stdout):
    interpreter = _sh()
    if interpreter is None:
        log.write("  [4/4] run the hook       : FAILED -- no sh on PATH\n")
        return False
    env = dict(os.environ)
    env[SENTINEL_ENV] = "1"
    rc, out = _run([interpreter, ".githooks/pre-commit"], cwd=repo, timeout=900, env=env)
    tail = "\n".join(out.splitlines()[-6:])
    log.write("  [4/4] run the hook       : %s\n" % ("all gates passed" if rc == 0 else "FAILED rc=%d" % rc))
    if rc != 0:
        log.write("        hook tail:\n")
        for line in tail.splitlines():
            log.write("          %s\n" % line)
    return rc == 0


def pipeline(repo, log=sys.stdout):
    log.write("prepare: %s\n" % repo)
    normalize_eol(repo, log)
    if not regen_manifest(repo, log):
        return False
    if not stage(repo, log):
        return False
    return verify(repo, log)


# --------------------------------------------------------------------------- #
# Self test: prove the ordering is what makes the run pass.
# --------------------------------------------------------------------------- #

_GEN = '''\
import hashlib, pathlib
h = hashlib.sha256()
for f in sorted(pathlib.Path("data").glob("*")):
    h.update(f.name.encode()); h.update(f.read_bytes())
pathlib.Path("stamp.txt").write_text(h.hexdigest(), encoding="utf-8")
'''

_VERIFY = '''\
import hashlib, pathlib, subprocess, sys
idx = subprocess.run(["git", "diff", "--cached", "--name-only"],
                     capture_output=True, text=True).stdout.split()
bad = [f for f in idx if f.startswith("data/")
       and pathlib.Path(f).is_file() and b"\\r\\n" in pathlib.Path(f).read_bytes()]
if bad:
    print("CRLF reached the index:", bad); sys.exit(1)
h = hashlib.sha256()
for f in sorted(pathlib.Path("data").glob("*")):
    h.update(f.name.encode()); h.update(f.read_bytes())
if pathlib.Path("stamp.txt").read_text(encoding="utf-8").strip() != h.hexdigest():
    print("stamp is stale"); sys.exit(1)
print("ok")
'''


def _make_synthetic(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "a.txt").write_bytes(b"alpha\nbeta\n")
    (root / "data" / "b.txt").write_bytes(b"gamma\n")
    (root / "gen.py").write_text(_GEN, encoding="utf-8")
    (root / "verify.py").write_text(_VERIFY, encoding="utf-8", newline="\n")
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@e"],
                ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "base"]):
        _run(cmd, cwd=root, timeout=60)
    return root


def _syn_gen(root):
    return _run([sys.executable, "gen.py"], cwd=root, timeout=60)[0] == 0


def _syn_verify(root):
    return _run([sys.executable, "verify.py"], cwd=root, timeout=60)[0] == 0


def _syn_prepare(root):
    """The same order prepare.py uses: normalise -> generate -> stage -> verify."""
    for rel in ("data/a.txt", "data/b.txt"):
        p = root / rel
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
    if not _syn_gen(root):
        return False
    if _run(["git", "add", "-A"], cwd=root, timeout=60)[0] != 0:
        return False
    return _syn_verify(root)


def selftest(tmpdir=None, out=sys.stdout):
    import tempfile

    controls = []
    tmp = Path(tempfile.mkdtemp(prefix="prepare-selftest-", dir=str(tmpdir) if tmpdir else None))

    # --- positive control: a consistent tree verifies clean ----------------- #
    r0 = _make_synthetic(tmp / "clean")
    _syn_gen(r0)
    _run(["git", "add", "-A"], cwd=r0, timeout=60)
    controls.append(("a consistent tree verifies clean", _syn_verify(r0), "verify rc=0"))

    # --- negative control 1: CRLF in the index is caught -------------------- #
    r1 = _make_synthetic(tmp / "crlf")
    _syn_gen(r1)
    (r1 / "data" / "a.txt").write_bytes(b"alpha\r\nbeta\r\n")
    _run(["git", "add", "-A"], cwd=r1, timeout=60)
    controls.append(("CRLF staged into the index is caught", not _syn_verify(r1), "verify rc=1"))

    # --- negative control 2: a stale stamp is caught ------------------------ #
    r2 = _make_synthetic(tmp / "stale")
    _syn_gen(r2)
    _run(["git", "add", "-A"], cwd=r2, timeout=60)
    (r2 / "data" / "b.txt").write_bytes(b"gamma\ndelta\n")   # edit AFTER generating
    controls.append(("a stamp stale after a later edit is caught", not _syn_verify(r2), "verify rc=1"))

    # --- closure 1: the full order repairs the stale-stamp tree ------------- #
    controls.append(("the full order repairs a stale stamp", _syn_prepare(r2), "prepare rc=0"))

    # --- closure 2: the full order repairs the CRLF tree -------------------- #
    controls.append(("the full order repairs staged CRLF", _syn_prepare(r1), "prepare rc=0"))

    # --- negative control 3: a binary carrying CRLF must not be rewritten --- #
    # `_looks_binary` is the guard; a guard is only real if it can be observed
    # holding. A .bin with a NUL and a CRLF must come back byte-identical.
    r3 = _make_synthetic(tmp / "binary")
    blob = r3 / "data" / "blob.bin"
    original = b"\x00\x01\x02\r\n\x03"
    blob.write_bytes(original)
    _run(["git", "add", "-A"], cwd=r3, timeout=60)
    normalize_eol(r3, log=io.StringIO())
    controls.append(("a binary carrying CRLF is left byte-identical",
                     blob.read_bytes() == original,
                     "unchanged=%s" % (blob.read_bytes() == original)))

    out.write("\nSELFTEST -- proving the ordering is load-bearing\n")
    out.write("-" * 78 + "\n")
    n_bad = 0
    for title, ok, detail in controls:
        out.write("  %-4s %-52s %s\n" % ("OK" if ok else "BAD", title, detail))
        if not ok:
            n_bad += 1

    # --- recursion sentinel: must refuse when it is already inside a hook --- #
    saved = os.environ.get(SENTINEL_ENV)
    os.environ[SENTINEL_ENV] = "1"
    try:
        rc_refuse = main(["--repo", str(tmp)])
    finally:
        if saved is None:
            os.environ.pop(SENTINEL_ENV, None)
        else:
            os.environ[SENTINEL_ENV] = saved
    sentinel_ok = rc_refuse != 0
    out.write("  %-4s %-52s %s\n"
              % ("OK" if sentinel_ok else "BAD",
                 "refuses to run when already inside a hook", "exit=%d" % rc_refuse))
    if not sentinel_ok:
        n_bad += 1

    out.write("-" * 78 + "\n")
    total = len(controls) + 1
    out.write("  %d controls: %d green, %d red -> %s\n"
              % (total, total - n_bad, n_bad,
                 "SELFTEST PASS" if n_bad == 0 else "SELFTEST FAIL"))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if n_bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Normalise, regenerate, stage, verify -- in that order.")
    ap.add_argument("--repo", default=str(REPO), help="repository root")
    ap.add_argument("--check", action="store_true", help="verify only; change nothing")
    ap.add_argument("--selftest", action="store_true", help="prove the ordering matters")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if os.environ.get(SENTINEL_ENV):
        # Someone listed this tool in `.githooks/pre-commit`. It would call the
        # hook, which would call this tool. Refuse before that starts.
        sys.stderr.write(
            "REFUSED: %s is set, so this run is already inside a hook.\n"
            "prepare.py must not be listed in .githooks/pre-commit -- it calls\n"
            "that hook, and the two would recurse.\n" % SENTINEL_ENV
        )
        return 3

    repo = Path(args.repo).resolve()
    if args.check:
        ok = verify(repo)
    else:
        ok = pipeline(repo)
    if ok:
        sys.stdout.write("\nREADY: the tree is consistent and all gates pass. "
                         "Commit is still yours to make.\n")
        return 0
    sys.stdout.write("\nNOT READY: fix the failure above, then re-run prepare.py.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
