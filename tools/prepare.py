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

Known limits
------------
Written down here rather than discovered later. Each one was measured on
2026-10-08 before it was written down; `_diag_ci_20261008/nc_prepare_limits.py`
is the control file that keeps them honest.

* **`git add -A` still stages untracked files.** That is the point -- the gates
  read the index and cannot see a file that is not in it. What changed is that
  the paths this run *added* are now listed in their own block, in full, with no
  cap, while the paths you edited yourself keep the cap. The run does not ask
  permission; it makes the sweep impossible to miss. Measured before the fix:
  twenty untracked files, ten of them named, `... and 10 more`, exit 0.
* **`_looks_binary` reads a NUL window and then requires valid UTF-8.** The
  window is gate 13's number, and the selftest asserts the two are equal, because
  they were not: 8,192 here and 8,000 there until 2026-10-08, and a NUL at offset
  8,100 made prepare skip a file gate 13 then reported -- a run prepare could not
  bring to a passing state.
  The UTF-8 test is prepare's own, and it makes prepare **stricter** than the
  gate: a file that is NUL-free for the window *and* not valid UTF-8 is skipped
  by prepare but still reported as text by gate 13. That asymmetry is taken on
  purpose -- prepare leaving a file alone fails loudly at gate 13, whereas a
  rewrite of a binary fails silently -- but it is a real edge: a NUL-free,
  non-UTF-8, CRLF-carrying tracked file would be reported by the gate with no
  normalisation available for it.
  A binary that is NUL-free for the window *and* happens to decode as UTF-8 is
  still treated as text. Measured before the fix: an 8,070-byte file became
  8,069 bytes, one CRLF pair gone, no warning.
  When a file is skipped, step [1/4] names it and the test that fired, and it
  says out loud when the reason was the UTF-8 test alone.
* **Rollback restores the index, not the working tree.** The CRLF corrections
  and the regenerated manifest stay on disk after a failed run, deliberately:
  they are the repair, and throwing them away would only make the next run
  repeat it.
* **`--check` is a comparison at one instant, not a lock.** It compares the
  working tree with the index and then runs the gates. Nothing stops an edit
  landing between the two steps.

Usage
-----
    python tools/prepare.py              # normalise, regenerate, stage, verify
    python tools/prepare.py --check      # verify, and say what the verdict covers
    python tools/prepare.py --selftest   # prove the ordering is load-bearing

Exit code is 0 only when the gates pass *and* the working tree holds nothing the
index does not.
"""

from __future__ import annotations

import argparse
import io
import os
import re
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

# The NUL window. This is git's own number (`buffer_is_binary` looks at the first
# 8000 bytes) and it is also gate 13's -- `check-line-endings.py` has
# `SNIFF_BYTES = 8000`. It has to be the same number on both sides: prepare's job
# is to make the tree pass gate 13, so the two must agree about what is binary.
# They did not. Until 2026-10-08 this file said 8192 while the gate said 8000, and
# a NUL at offset 8,100 made prepare skip a file that gate 13 then reported --
# a run prepare could not bring to a passing state, which is the one thing it
# exists to prevent. The selftest now asserts the two are equal, so an edit to
# either one turns red instead of drifting.
NUL_PROBE_BYTES = 8000

GATE13 = REPO / "tools" / "check-line-endings.py"

# The cap applies to the class that cannot surprise you: edits you made to files
# git already tracks. The class that *can* surprise you -- files git did not
# have -- is printed without a cap. That asymmetry is the whole point; a cap on
# both is how twenty stray files became ten named ones and a `... and 10 more`.
TRACKED_EDIT_REPORT_MAX = 20


def _binary_reason(data: bytes):
    """Why the bytes are not text, or None if they are.

    Returning the reason rather than a bool means the run can say *which* test
    fired, and that matters for one case: a file skipped on the UTF-8 test alone
    will still be reported by gate 13, which only has the NUL window. Saying so
    at the moment it is skipped is the difference between a decision and a
    mystery.
    """
    if b"\x00" in data[:NUL_PROBE_BYTES]:
        return "NUL in the first %d bytes" % NUL_PROBE_BYTES
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return "not UTF-8 (%s)" % exc
    return None


def _looks_binary(data: bytes) -> bool:
    """Two questions, both cheap, both answered about the bytes.

    1. A NUL byte in the first `NUL_PROBE_BYTES`. This is git's own test, and it
       catches every binary format that carries a header with zero bytes in it.
    2. Does it decode as UTF-8? Everything this repository tracks does. A file
       that does not is either a different encoding or not text, and in both
       cases rewriting its line endings is the wrong move.

    The second test exists because the first has a hole with a measured size: a
    file with 8,000 bytes of ASCII in front of its binary body has no NUL in the
    window and was rewritten (8,070 -> 8,069 bytes, 2026-10-08).

    The first test is deliberately *not* this file's to choose -- see
    `NUL_PROBE_BYTES`. The second one is, and it makes prepare stricter than gate
    13: prepare skips a file the gate would call text. That asymmetry is taken on
    purpose and stated in "Known limits".
    """
    return _binary_reason(data) is not None


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


def normalize_eol(repo, log=None):
    """Convert CRLF to LF in tracked text files. Bytes are otherwise untouched.

    This does not *mask* a CRLF problem, it removes it before the index can
    carry it. Gate 13 still runs, and still fails on anything that arrives
    CRLF some other way.
    """
    log = log if log is not None else sys.stdout
    changed = []
    skipped_binary = []
    for rel in tracked_files(repo):
        path = repo / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        reason = _binary_reason(data)
        if path.suffix.lower() in BINARY_SUFFIXES:
            reason = reason or "known binary suffix"
        if reason:
            if b"\r\n" in data:
                skipped_binary.append((rel, reason))
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
        log.write("        left alone (binary carrying CRLF), %d file(s): %s\n"
                  % (len(skipped_binary),
                     ", ".join("%s [%s]" % (rel, why) for rel, why in skipped_binary[:4])))
        not_utf8 = [rel for rel, why in skipped_binary if why.startswith("not UTF-8")]
        if not_utf8:
            log.write("        ^ %d of these were skipped on the UTF-8 test alone. Gate 13\n"
                      "          decides 'binary' from the NUL window only, so it WILL\n"
                      "          report their CRLF and this run cannot clear it. That is\n"
                      "          the loud direction on purpose: the alternative rewrites\n"
                      "          a binary and commits it without a word.\n"
                      % len(not_utf8))
    return changed


def regen_manifest(repo, log=None):
    log = log if log is not None else sys.stdout
    rc, out = _run([sys.executable, "tools/make-manifest.py"], cwd=repo, timeout=300)
    log.write("  [2/4] regenerate manifest : %s\n"
              % ("ok" if rc == 0 else "FAILED rc=%d %s" % (rc, out[-200:])))
    return rc == 0


def stage(repo, log=None):
    """Stage everything, and say exactly what "everything" turned out to be.

    `git add -A` is deliberate -- the gates read the index, so a file that is not
    in the index is a file no gate has looked at. The side effect is that files
    a human did not choose get staged too, and a side effect nobody reviews is a
    side effect that will eventually be committed.

    So the report splits the index into two classes and treats them differently.
    Edits to already-tracked files are capped, because you made them. Paths that
    were **untracked** before this run -- the ones that can surprise you -- are
    listed in full. Twenty of them used to print as ten and `... and 10 more`.
    """
    log = log if log is not None else sys.stdout

    rc, out = _run(["git", "ls-files", "--others", "--exclude-standard"],
                   cwd=repo, timeout=60)
    if rc != 0:
        log.write("  [3/4] stage all changes  : FAILED listing untracked files: %s\n"
                  % out[:200])
        return False
    untracked_before = set(l.strip() for l in out.splitlines() if l.strip())

    rc, out = _run(["git", "add", "-A"], cwd=repo, timeout=120)
    if rc != 0:
        log.write("  [3/4] stage all changes  : FAILED %s\n" % out[:200])
        return False

    rc2, names = _run(["git", "diff", "--cached", "--name-status"], cwd=repo, timeout=60)
    rows = [r for r in names.splitlines() if r.strip()]

    edits, added = [], []
    for row in rows:
        code, _, path = row.partition("\t")
        if code.strip().startswith("A") and path.strip() in untracked_before:
            added.append(row)
        else:
            edits.append(row)

    log.write("  [3/4] stage all changes  : ok, %d path(s) in the index\n" % len(rows))
    log.write("        edited by you (tracked)  : %d\n" % len(edits))
    for row in edits[:TRACKED_EDIT_REPORT_MAX]:
        log.write("          %s\n" % row)
    if len(edits) > TRACKED_EDIT_REPORT_MAX:
        log.write("          ... and %d more\n" % (len(edits) - TRACKED_EDIT_REPORT_MAX))
    log.write("        NEW - untracked until this run : %d\n" % len(added))
    for row in added:                      # deliberately not capped
        log.write("          %s\n" % row)
    if added:
        log.write("        ^ these are in the index now because the gates must see\n"
                  "          the whole tree. If any of them is not part of this\n"
                  "          commit, `git reset` and re-run.\n")
    return True


def worktree_delta(repo):
    """Paths the working tree holds and the index does not.

    Why this is worth its own function: the gates do not read one artifact.
    Gate 13 reads the **index** -- and says so, on purpose, because the index is
    what a commit writes. `make-manifest --check` reads the **working tree**,
    because the manifest is a statement about the bytes on disk. A verdict built
    from those two says nothing about the gap between them, and it was measured
    on 2026-10-08 that a `--check` run could not name a file it never read.

    Returns (delta, note). delta is None when the comparison could not be made,
    which is not the same as "no difference".
    """
    rc1, out1 = _run(["git", "diff", "--name-only"], cwd=repo, timeout=60)
    rc2, out2 = _run(["git", "ls-files", "--others", "--exclude-standard"],
                     cwd=repo, timeout=60)
    if rc1 != 0 or rc2 != 0:
        return None, ("could not compare the index with the working tree "
                      "(git diff rc=%d, git ls-files rc=%d)" % (rc1, rc2))
    delta = [l for l in out1.splitlines() if l.strip()]
    delta += [l for l in out2.splitlines() if l.strip()]
    return delta, "ok"


def _sh():
    for name in ("sh", "bash"):
        found = shutil.which(name)
        if found:
            return found
    return None


def verify(repo, log=None):
    log = log if log is not None else sys.stdout
    interpreter = _sh()
    if interpreter is None:
        log.write("  [4/4] run the hook       : FAILED -- no sh on PATH\n")
        return False
    env = dict(os.environ)
    env[SENTINEL_ENV] = "1"
    rc, out = _run([interpreter, ".githooks/pre-commit"], cwd=repo, timeout=900, env=env)
    tail = "\n".join(out.splitlines()[-6:])
    log.write("  [4/4] run the hook       : %s\n"
              % ("all gates passed" if rc == 0 else "FAILED rc=%d" % rc))
    if rc != 0:
        log.write("        hook tail:\n")
        for line in tail.splitlines():
            log.write("          %s\n" % line)
    return rc == 0


def _snapshot_index(repo, log):
    """A token that puts the index back. None when no token can be taken."""
    rc, out = _run(["git", "write-tree"], cwd=repo, timeout=120)
    if rc != 0:
        log.write("        (no index snapshot: git write-tree rc=%d %s)\n"
                  % (rc, out[:120]))
        return None
    token = out.strip().splitlines()[-1].strip() if out.strip() else ""
    return token or None


def _restore_index(repo, token, log):
    """Put the index back after a failed run.

    A failed run used to leave the index fully staged -- measured on 2026-10-08:
    `prepare.py` exited 1 and `git diff --cached` still listed three paths. The
    next `git commit`, from muscle memory, would have committed a state this tool
    had just called NOT READY. So the index is restored from a snapshot taken
    before staging.
    """
    log.write("\n  [rollback] the run failed after staging; putting the index back\n")
    if not token:
        log.write("             no snapshot was available (see [3/4] above). The index\n"
                  "             is still staged. Undo with:  git reset\n")
        return
    rc, out = _run(["git", "read-tree", token], cwd=repo, timeout=120)
    if rc != 0:
        log.write("             restore FAILED (git read-tree rc=%d %s)\n"
                  "             Undo with:  git reset\n" % (rc, out[:160]))
        return
    log.write("             index restored to %s\n" % token[:12])
    log.write("             working-tree corrections from [1/4] and [2/4] were kept --\n"
              "             they are the repair, not the damage. Deal with the failure\n"
              "             above, then re-run prepare.py.\n")


def pipeline(repo, log=None):
    log = log if log is not None else sys.stdout
    log.write("prepare: %s\n" % repo)
    normalize_eol(repo, log)
    if not regen_manifest(repo, log):
        return False
    snapshot = _snapshot_index(repo, log)
    if not stage(repo, log):
        return False
    if verify(repo, log):
        return True
    _restore_index(repo, snapshot, log)
    return False


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
    """A repository small enough to reason about, complete enough to run the
    whole of `pipeline()` -- including a hook, so `verify()` is exercised and
    not stubbed."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "tools").mkdir(exist_ok=True)
    (root / ".githooks").mkdir(exist_ok=True)
    (root / "data" / "a.txt").write_bytes(b"alpha\nbeta\n")
    (root / "data" / "b.txt").write_bytes(b"gamma\n")
    (root / "tools" / "make-manifest.py").write_bytes(_GEN.encode("utf-8"))
    (root / "verify.py").write_bytes(_VERIFY.encode("utf-8"))
    (root / ".githooks" / "pre-commit").write_bytes(
        ('#!/bin/sh\nexec "%s" verify.py\n' % sys.executable.replace("\\", "/")
         ).encode("utf-8"))
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@e"],
                ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "base"]):
        _run(cmd, cwd=root, timeout=60)
    return root


def _syn_gen(root):
    return _run([sys.executable, "tools/make-manifest.py"], cwd=root, timeout=60)[0] == 0


def _syn_verify(root):
    return _run([sys.executable, "verify.py"], cwd=root, timeout=60)[0] == 0


def _syn_stage(root):
    return _run(["git", "add", "-A"], cwd=root, timeout=60)[0] == 0


def _syn_prepare(root):
    """The same order prepare.py uses: normalise -> generate -> stage -> verify."""
    for rel in ("data/a.txt", "data/b.txt"):
        p = root / rel
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
    if not _syn_gen(root):
        return False
    if not _syn_stage(root):
        return False
    return _syn_verify(root)


def _staged(root):
    rc, out = _run(["git", "diff", "--cached", "--name-status"], cwd=root, timeout=60)
    return [l for l in out.splitlines() if l.strip()]


def selftest(tmpdir=None, out=None):
    import tempfile

    out = out if out is not None else sys.stdout
    controls = []
    tmp = Path(tempfile.mkdtemp(prefix="prepare-selftest-",
                                dir=str(tmpdir) if tmpdir else None))

    # --- positive control: a consistent tree verifies clean ----------------- #
    r0 = _make_synthetic(tmp / "clean")
    _syn_gen(r0)
    _syn_stage(r0)
    controls.append(("a consistent tree verifies clean", _syn_verify(r0), "verify rc=0"))

    # --- negative control 1: CRLF in the index is caught -------------------- #
    r1 = _make_synthetic(tmp / "crlf")
    _syn_gen(r1)
    (r1 / "data" / "a.txt").write_bytes(b"alpha\r\nbeta\r\n")
    _syn_stage(r1)
    controls.append(("CRLF staged into the index is caught", not _syn_verify(r1), "verify rc=1"))

    # --- negative control 2: a stale stamp is caught ------------------------ #
    r2 = _make_synthetic(tmp / "stale")
    _syn_gen(r2)
    _syn_stage(r2)
    (r2 / "data" / "b.txt").write_bytes(b"gamma\ndelta\n")   # edit AFTER generating
    controls.append(("a stamp stale after a later edit is caught", not _syn_verify(r2), "verify rc=1"))

    # --- closure 1: the full order repairs the stale-stamp tree ------------- #
    controls.append(("the full order repairs a stale stamp", _syn_prepare(r2), "prepare rc=0"))

    # --- closure 2: the full order repairs the CRLF tree -------------------- #
    controls.append(("the full order repairs staged CRLF", _syn_prepare(r1), "prepare rc=0"))

    # --- binary control 1: a NUL in the probe window is enough -------------- #
    r3 = _make_synthetic(tmp / "binary")
    blob = r3 / "data" / "blob.bin"
    original = b"\x00\x01\x02\r\n\x03"
    blob.write_bytes(original)
    _syn_stage(r3)
    normalize_eol(r3, log=io.StringIO())
    controls.append(("a binary with a NUL keeps its bytes",
                     blob.read_bytes() == original,
                     "unchanged=%s" % (blob.read_bytes() == original)))

    # --- binary control 2: no NUL for 8 KiB, but still not text ------------- #
    # This is the fix. Before it, this file lost one byte and its CRLF: a binary
    # whose head is long ASCII passed the NUL test and was rewritten as text.
    r3b = _make_synthetic(tmp / "binary_nohead_nul")
    blob2 = r3b / "data" / "blob2.bin"
    payload = b"A" * 8000 + b"\xff\xd8\xff\xe0" + b"\r\n" + b"\xff" * 64
    blob2.write_bytes(payload)
    _syn_stage(r3b)
    log3 = io.StringIO()
    normalize_eol(r3b, log=log3)
    controls.append(("a NUL-free-head binary keeps its bytes",
                     blob2.read_bytes() == payload,
                     "%d -> %d bytes" % (len(payload), len(blob2.read_bytes()))))
    said = log3.getvalue()
    controls.append(("a skip names the file and the test that fired",
                     "blob2.bin" in said and "not UTF-8" in said,
                     "named=%s, reason=%s" % ("blob2.bin" in said,
                                              "not UTF-8" in said)))

    # --- parity control: one window, not two -------------------------------- #
    # Found by an independent reviewer's probe, not by the author: gate 13 answers
    # "is this binary" with SNIFF_BYTES = 8000 while this file answered it with
    # 8192. A NUL at offset 8,100 sat in the gap -- skipped by prepare, reported
    # by the gate. Asserting the two numbers equal here means an edit to either
    # one turns this red instead of drifting again.
    gate_width = None
    try:
        m = re.search(r"^SNIFF_BYTES\s*=\s*(\d+)",
                      GATE13.read_text(encoding="utf-8"), re.M)
        gate_width = int(m.group(1)) if m else None
    except OSError:
        gate_width = None
    controls.append(("the binary window matches gate 13's",
                     gate_width == NUL_PROBE_BYTES,
                     "gate13=%s prepare=%d" % (gate_width, NUL_PROBE_BYTES)))

    # --- report control: every newly-staged path is named, and not capped --- #
    r5 = _make_synthetic(tmp / "report")
    _syn_gen(r5)
    _syn_stage(r5)
    names = ["zz-%02d.txt" % i for i in range(15)]
    for n in names:
        (r5 / n).write_bytes(b"scratch\n")
    buf = io.StringIO()
    stage(r5, log=buf)
    text = buf.getvalue()
    missing = [n for n in names if n not in text]
    controls.append(("every newly-staged path is named, uncapped", not missing,
                     "%d/%d named%s" % (len(names) - len(missing), len(names),
                                        "" if not missing else " missing=%s" % missing[:3])))

    # --- rollback control: a failed run must not leave the index staged ----- #
    r6 = _make_synthetic(tmp / "rollback")
    _syn_gen(r6)
    _syn_stage(r6)
    _run(["git", "commit", "-q", "-m", "current"], cwd=r6, timeout=60)
    (r6 / "data" / "blob.bin").write_bytes(b"\x00\x01\r\n\x02")   # cannot be normalised
    before = _staged(r6)
    ok6 = pipeline(r6, log=io.StringIO())
    after = _staged(r6)
    controls.append(("a failed run puts the index back", (not ok6) and after == before,
                     "pipeline ok=%s staged %d -> %d" % (ok6, len(before), len(after))))

    # --- check control: `--check` must refuse what it did not read ---------- #
    r7 = _make_synthetic(tmp / "checkdelta")
    _syn_gen(r7)
    _syn_stage(r7)
    saved = sys.stdout
    buf7 = io.StringIO()
    sys.stdout = buf7
    try:
        rc_clean = main(["--repo", str(r7), "--check"])
        (r7 / "notes.txt").write_bytes(b"a file the index does not hold\n")
        rc_dirty = main(["--repo", str(r7), "--check"])
    finally:
        sys.stdout = saved
    named = "notes.txt" in buf7.getvalue()
    controls.append(("--check names a path the index does not hold",
                     rc_clean == 0 and rc_dirty != 0 and named,
                     "clean=%d dirty=%d named=%s" % (rc_clean, rc_dirty, named)))

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
    sentinel_ok = rc_refuse == 3
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


READY_SENTENCE = ("every gate passed, and the working tree holds nothing the index "
                  "does not. Commit is still yours to make.")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Normalise, regenerate, stage, verify -- in that order.")
    ap.add_argument("--repo", default=str(REPO), help="repository root")
    ap.add_argument("--check", action="store_true",
                    help="verify the index, and say what the verdict leaves unread")
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

    if not args.check:
        ok = pipeline(repo)
    else:
        # Say what was read before saying what is true. The gates do not read a
        # single artifact -- gate 13 reads the index, the manifest reads the
        # working tree -- so a verdict that stays silent about the gap between
        # them is a verdict about something nobody looked at.
        delta, note = worktree_delta(repo)
        if delta is None:
            sys.stdout.write("\nNOT READY: %s. Nothing was verified about the "
                             "working tree.\n" % note)
            return 1
        if delta:
            sys.stdout.write(
                "  [check] the index does not hold the whole tree. These paths are\n"
                "          on disk and NOT in the index, so the gates below cannot\n"
                "          speak for them:\n")
            for path in delta[:TRACKED_EDIT_REPORT_MAX]:
                sys.stdout.write("            %s\n" % path)
            if len(delta) > TRACKED_EDIT_REPORT_MAX:
                sys.stdout.write("            ... and %d more\n"
                                 % (len(delta) - TRACKED_EDIT_REPORT_MAX))
        gates_ok = verify(repo)
        ok = gates_ok and not delta
        if gates_ok and delta:
            sys.stdout.write(
                "\nNOT READY: the gates passed against the index, but the working\n"
                "tree holds %d path(s) the index does not. Run prepare.py to stage\n"
                "them, then check again.\n" % len(delta))

    if ok:
        sys.stdout.write("\nREADY: %s\n" % READY_SENTENCE)
        return 0
    sys.stdout.write("\nNOT READY: fix the failure above, then re-run prepare.py.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
