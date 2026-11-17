#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check-line-endings.py -- byte hygiene of the index: no CRLF, no UTF-8 BOM.

Why this gate exists
--------------------
`.gitattributes` in this repository is `* -text`, and it is that on purpose. The
content manifest (`manifest.sha256`, `INTEGRITY.md`) records the SHA-256 of the
bytes on disk. Git's one automatic end-of-line mechanism rewrites a file on
checkout, so a file committed with LF on a server is checked out as CRLF on a
Windows machine and the bytes -- hence every digest -- differ by platform. `-text`
disables that rewrite, which is exactly what a byte manifest requires.

The cost of `-text` is that git no longer normalizes anything. Every newline in
every commit is now whatever bytes the committing editor happened to produce, and
nothing in the toolchain objects: a CRLF file enters the index, gets committed,
and is byte-exact on checkout, so no manifest digest goes red. The failure is
silent in the only sense that matters here -- the run where a CRLF slips in looks
exactly like the run where it did not.

So CRLF has to be *checked*, not converted. That is the whole gate: it does not
normalize anything (that would change the bytes the manifest signs), it reports.

Why the index, and not the working tree
---------------------------------------
The defect this gate is built around was a working tree that had been normalized
to LF while the index still held the CRLF blobs. A checker that reads the working
tree looks green there; the CRLF is still what the next commit would record. That
is this repository's recurring shape -- a gate watching a copy of the artifact
instead of the artifact. The index is the thing a commit writes, so the index is
what is checked. Every blob here is read through `git cat-file blob <hash>` and
never from disk.

This is a check, not a fix
--------------------------
`tools/make-manifest.py` exists precisely because the bytes must not move under
the manifest. This gate reports a CRLF and exits non-zero; it never rewrites a
line ending, because rewriting is the transformation `-text` was chosen to forbid.

Why it has a negative control
-----------------------------
A checker that has never been observed failing is a decoration. `--selftest`
builds a throwaway git repository in `tempfile.mkdtemp()`, commits a CRLF file
into its index, and requires this program to report it and exit non-zero; then it
builds an LF repository and requires silence. Either direction failing is a
self-test failure. That is what separates a gate from a check nobody has watched.

Why the BOM is in scope (2026-10-28)
------------------------------------
A leading UTF-8 BOM (`EF BB BF`) is the same class of defect as CRLF under
`* -text`: it is three bytes that change every digest, and nothing in this
toolchain used to look at them. That was not hypothetical. An independent
review seat measured it on this repository: a file carrying a BOM passed all
seventeen gates, while a revision of the same file without it also passed, so
two byte-different artifacts were equally "verified". A `grep` for
`utf-8-sig|efbbbf|BOM` across `tools/` returned nothing -- the gate's own
subject had never been named anywhere, which is precisely the shape this
catalogue documents.

The BOM is reported, never stripped, for the same reason CRLF is: the manifest
signs the bytes on disk, and a gate that silently rewrites them is the
transformation `-text` was chosen to forbid. `tools/prepare.py` normalizes line
endings and does NOT touch a BOM -- stated plainly rather than left to be
discovered, because the asymmetry means a BOM is fixed by hand.

Only the UTF-8 BOM is checked. A UTF-16 BOM cannot reach this code path: those
files carry NUL bytes in their first window and are skipped as binary, and
claiming coverage that the binary skip makes unreachable would be worse than
leaving it out.

This `name` deliberately carries no gate number. It used to print "gate 13" and
the gate list moved it to 14 without this string moving with it -- a stale
number is a second source of truth about ordering, and the ordering already has
one (`tools/check-gate-parity.py`).

Usage
-----
  python tools/check-line-endings.py             # scan the index of the cwd repo
  python tools/check-line-endings.py --selftest   # positive + negative controls

Exit code: 0 = no CRLF and no BOM in the index; 1 = at least one, or the scan
could not run.
"""
import os
import subprocess
import sys
import tempfile

# A blob whose first bytes contain NUL is treated as binary and skipped. This also
# skips UTF-16 text, whose ASCII is interleaved with NULs: reporting "CRLF" inside
# such a file would be noise about an encoding, not about a line ending.
SNIFF_BYTES = 8000

# The UTF-8 byte-order mark. Three bytes that shift every digest in the manifest
# without changing a single character a reader would see.
BOM_UTF8 = b"\xef\xbb\xbf"


def _git(args, cwd=None):
    """Run git and return (returncode, stdout_bytes, stderr_text).

    Never raises for a non-zero exit: callers decide whether that is a failure. A
    git that cannot be executed at all (missing binary, OSError) is reported as a
    failure here, because "I could not run the check" is not "the check passed".
    """
    try:
        proc = subprocess.Popen(
            ["git"] + list(args),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate()
    except OSError as exc:
        return 127, b"", "git could not be executed: %s" % exc
    return proc.returncode, out, err.decode("utf-8", "replace")


def _index_entries(cwd):
    """Return a list of (path, blob_hash) for every entry in the index.

    `-s` gives the staged blob hash and `-z` NUL-terminates, so no path is ever
    quoted or reinterpreted. Reading by hash means the working tree is not
    consulted at all: the content tested is the content a commit would write.
    """
    code, out, err = _git(["ls-files", "-s", "-z"], cwd=cwd)
    if code != 0:
        raise RuntimeError("git ls-files failed (exit %d): %s" % (code, err.strip()))

    entries = []
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) < 2:
            continue
        blob_hash = parts[1].decode("ascii", "replace")
        entries.append((path.decode("utf-8", "replace"), blob_hash))
    return entries


def _blob_bytes(blob_hash, cwd):
    """Return the raw bytes of one blob, straight from the object store."""
    code, out, err = _git(["cat-file", "blob", blob_hash], cwd=cwd)
    if code != 0:
        raise RuntimeError("git cat-file blob %s failed (exit %d): %s"
                           % (blob_hash, code, err.strip()))
    return out


def _is_binary(data):
    return b"\0" in data[:SNIFF_BYTES]


def _has_utf8_bom(data):
    """True if the blob starts with a UTF-8 BOM.

    Checked after the binary test, on purpose: a UTF-16 file also starts with a
    BOM but is skipped as binary, and this gate does not claim to see it.
    """
    return data.startswith(BOM_UTF8)


def _crlf_lines(data):
    """Return the 1-based line numbers whose terminator is CRLF.

    Split on LF and look at the segment before it: a segment ending in CR means
    the pair it was split from was CRLF. A lone CR (not followed by LF) is not a
    line terminator this gate is about and is deliberately not reported.
    """
    hits = []
    for number, segment in enumerate(data.split(b"\n"), start=1):
        if segment.endswith(b"\r"):
            hits.append(number)
    return hits


def scan(cwd):
    """Scan the index of the repository at `cwd`.

    Returns (crlf_hits, bom_hits, scanned): crlf_hits is a list of
    (path, line_number), bom_hits a list of path, scanned the number of index
    entries examined.
    """
    crlf_hits = []
    bom_hits = []
    entries = _index_entries(cwd)
    for path, blob_hash in entries:
        data = _blob_bytes(blob_hash, cwd)
        if _is_binary(data):
            continue
        if _has_utf8_bom(data):
            bom_hits.append(path)
        for number in _crlf_lines(data):
            crlf_hits.append((path, number))
    return crlf_hits, bom_hits, len(entries)


def _run(cwd):
    """Scan and print. Returns the process exit code."""
    try:
        crlf_hits, bom_hits, scanned = scan(cwd)
    except RuntimeError as exc:
        print("line-endings gate FAILED: %s" % exc)
        return 1

    if crlf_hits or bom_hits:
        for path, number in crlf_hits:
            print("%s:%d: CRLF" % (path, number))
        for path in bom_hits:
            print("%s:1: UTF-8 BOM" % path)
        parts = []
        if crlf_hits:
            files = sorted(set(path for path, _ in crlf_hits))
            parts.append("%d CRLF line(s) across %d file(s)" % (len(crlf_hits), len(files)))
        if bom_hits:
            parts.append("%d UTF-8 BOM(s)" % len(bom_hits))
        print("line-endings gate FAILED: %s in the index" % " and ".join(parts))
        return 1

    print("OK: %d file(s) in the index, no CRLF, no BOM" % scanned)
    return 0


def _build_repo(root, filename, payload):
    """Create a repo at `root` and commit one file with the given raw bytes.

    autocrlf is forced off so the bytes written are the bytes staged -- otherwise
    a Windows host with autocrlf on would silently normalize the negative control's
    CRLF away and the control would pass for the wrong reason. core.hooksPath is
    emptied so a global hook cannot interfere with a throwaway repository.
    """
    os.makedirs(root)
    flags = ["-c", "core.autocrlf=false", "-c", "core.hooksPath="]
    code, _, err = _git(flags + ["init", "-q"], cwd=root)
    if code != 0:
        raise RuntimeError("git init failed: %s" % err)
    with open(os.path.join(root, filename), "wb") as fh:
        fh.write(payload)
    for args in (
        ["add", filename],
        ["-c", "user.email=selftest@localhost",
         "-c", "user.name=selftest", "commit", "-q", "-m", "selftest"],
    ):
        code, _, err = _git(flags + args, cwd=root)
        if code != 0:
            raise RuntimeError("selftest repo setup failed on %r: %s" % (args, err))


def _run_this_tool(cwd):
    """Invoke this script as a child process in `cwd`; return (code, output).

    The controls exercise the real program -- its argument handling and its exit
    code -- rather than an internal function, because the exit code is part of the
    contract a gate has to keep.
    """
    script = os.path.abspath(__file__)
    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out, _ = proc.communicate()
    return proc.returncode, out.decode("utf-8", "replace")


def selftest():
    failures = []
    tmp = tempfile.mkdtemp(prefix="gate13-selftest-")
    try:
        # -- negative control: a CRLF file in the index must be reported, and the
        #    exit code must go non-zero. This is the control that proves the gate
        #    fails on the shape it exists to catch.
        crlf_root = os.path.join(tmp, "crlf")
        _build_repo(crlf_root, "sample.txt", b"first line\r\nsecond line\r\n")
        code, out = _run_this_tool(crlf_root)
        if code != 0 and "sample.txt:1: CRLF" in out and "sample.txt:2: CRLF" in out:
            print("  + negative control        CRLF in the index reported, exit %d" % code)
        else:
            failures.append(
                "negative control: a committed CRLF file was NOT caught "
                "(exit %d, output %r)" % (code, out.strip()))

        # -- positive control: a pure-LF repository must pass silently. Without
        #    this, a checker that flags everything would satisfy the control above
        #    and be useless; the two directions are what make it discriminating.
        lf_root = os.path.join(tmp, "lf")
        _build_repo(lf_root, "sample.txt", b"first line\nsecond line\n")
        code, out = _run_this_tool(lf_root)
        if code == 0 and "no CRLF" in out:
            print("  + positive control        pure-LF index passed, exit %d" % code)
        else:
            failures.append(
                "positive control: a pure-LF repository was NOT passed "
                "(exit %d, output %r)" % (code, out.strip()))

        # -- divergence control: the exact shape this gate was built for. A CRLF
        #    file is committed, then the working tree is normalized to LF without
        #    re-staging -- index CRLF, worktree LF. A checker that reads the working
        #    tree looks green here; the next commit would still record CRLF. The gate
        #    must stay red, which is only possible because it reads the index.
        div_root = os.path.join(tmp, "divergence")
        _build_repo(div_root, "sample.txt", b"first line\r\nsecond line\r\n")
        with open(os.path.join(div_root, "sample.txt"), "wb") as fh:
            fh.write(b"first line\nsecond line\n")
        code, out = _run_this_tool(div_root)
        if code != 0 and "sample.txt:1: CRLF" in out:
            print("  + divergence control      index CRLF behind an LF worktree still "
                  "reported, exit %d" % code)
        else:
            failures.append(
                "divergence control: a normalized working tree hid CRLF that is still "
                "in the index (exit %d, output %r)" % (code, out.strip()))

        # -- binary control: a NUL-bearing blob must be skipped, so an encoded
        #    or genuinely binary file is not reported as a line-ending defect.
        bin_root = os.path.join(tmp, "binary")
        _build_repo(bin_root, "blob.bin", b"\x00\x01\x02\r\n\x00\x03")
        code, out = _run_this_tool(bin_root)
        if code == 0 and "no CRLF" in out:
            print("  + binary control          NUL-bearing blob skipped, exit %d" % code)
        else:
            failures.append(
                "binary control: a NUL-bearing blob was NOT skipped "
                "(exit %d, output %r)" % (code, out.strip()))
        # -- BOM control: a UTF-8 BOM is three bytes of digest drift with nothing
        #    visible on screen, so it is reported and the exit code goes non-zero.
        bom_root = os.path.join(tmp, "bom")
        _build_repo(bom_root, "sample.txt", BOM_UTF8 + b"first line\nsecond line\n")
        code, out = _run_this_tool(bom_root)
        if code != 0 and "sample.txt:1: UTF-8 BOM" in out:
            print("  + BOM control            UTF-8 BOM in the index reported, exit %d" % code)
        else:
            failures.append(
                "BOM control: a committed UTF-8 BOM was NOT caught "
                "(exit %d, output %r)" % (code, out.strip()))
    finally:
        _rmtree(tmp)

    print("")
    if failures:
        print("SELF-TEST FAILED: %d problem(s)" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("SELF-TEST PASSED: CRLF caught with a non-zero exit, LF passed, "
          "index/worktree divergence caught, binary skipped, UTF-8 BOM caught")
    return 0


def _rmtree(path):
    """Remove a temp tree; best effort, never raises during teardown."""
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for name in filenames:
            try:
                os.remove(os.path.join(dirpath, name))
            except OSError:
                pass
        for name in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def main(argv):
    if "--selftest" in argv[1:]:
        return selftest()
    return _run(os.getcwd())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
