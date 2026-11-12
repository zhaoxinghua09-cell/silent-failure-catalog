#!/usr/bin/env python3
"""quoted-output -- a block that claims to be verbatim must equal what the command prints.

Why this exists: on 2026-11-12 the README's selftest block said "That output is
verbatim, not a mock-up" and was one line short, because `SFL-007` had just been
added. The example block below it was further off: it still showed 8 findings
(4 high) where the tool printed 11 (7 high). Both blocks were inside a section
whose entire argument is *the output you see is the output you get*, and no gate
could see either of them. `check-catalog.py` proves entries are indexed and links
resolve; it has no opinion about a quoted block.

So the block opts in, and a command produces it:

    <!-- quoted-output: python tools/gate-lint.py --selftest -->
    ```
    <the output, verbatim>
    ```

A command that must run somewhere else names its directory in square brackets,
relative to the repository root:

    <!-- quoted-output: [tools/samples/bad] python ../../gate-lint.py . --tree . -->

Rules this enforces
  1. The block must be on the line after the marker (blank lines between them
     are allowed, nothing else is).
  2. The captured stdout must equal the block, line for line, after trailing
     whitespace on each line is dropped. Nothing else is normalized: an editor
     that trims trailing spaces cannot fake a green, and reordering is drift.
  3. The exit code is NOT part of the comparison. A documented run may exit 1
     on purpose -- the sample run below does, because it is linting files that
     are meant to be caught -- and demanding exit 0 would force the documentation
     to describe a run that finds nothing.
  4. A marker with no block after it is a failure, not a skip: the marker is the
     promise that something is being compared.
  5. Finding no marker anywhere is a failure. A checker that passes because it
     compared nothing is the defect this repository catalogs most often.

What it does not check
  * Prose around the block. Only the fenced text is compared.
  * Blocks with no marker. Those are prose examples, and pretending to verify
    them would mean guessing which command produced them.
  * stderr. A tool may print warnings there; the block is stdout.

Exit status: 0 when every marked block matches, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile

MARKER = re.compile(r"^\s*<!--\s*quoted-output:\s*(?P<spec>.*?)\s*-->$")
FENCE = re.compile(r"^\s*```")
DEFAULT_FILES = ("README.md", "index.md", "docs/*.md")


class Block:
    def __init__(self, path, line_no, spec, text):
        self.path = path
        self.line_no = line_no
        self.spec = spec
        self.text = text


def normalize(text):
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def collect(path, root):
    """Return (blocks, problems). problems are markers that promised a block and had none."""
    blocks, problems = [], []
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    i = 0
    while i < len(lines):
        m = MARKER.match(lines[i])
        if not m:
            i += 1
            continue
        marker_line = i + 1
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j >= len(lines) or not FENCE.match(lines[j]):
            problems.append("%s:%d  marker with no fenced block after it (the marker IS the promise)"
                            % (path, marker_line))
            i = j
            continue
        k = j + 1
        body = []
        while k < len(lines) and not FENCE.match(lines[k]):
            body.append(lines[k])
            k += 1
        if k >= len(lines):
            problems.append("%s:%d  fenced block is never closed" % (path, marker_line))
            i = k
            continue
        blocks.append(Block(path, marker_line, m.group("spec"), "\n".join(body)))
        i = k + 1
    return blocks, problems


def run_spec(spec, root):
    cwd = root
    if spec.startswith("["):
        close = spec.find("]")
        if close < 0:
            raise ValueError("malformed [cwd] prefix: %r" % spec)
        cwd = os.path.normpath(os.path.join(root, spec[1:close].strip()))
        spec = spec[close + 1:].strip()
    argv = shlex.split(spec)
    if not argv:
        raise ValueError("empty command")
    if argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    proc = subprocess.run(argv, cwd=cwd, capture_output=True)
    out = proc.stdout.decode("utf-8", "replace")
    return normalize(out), proc.returncode


def first_diff(expected, actual):
    a, b = expected.split("\n"), actual.split("\n")
    for n in range(max(len(a), len(b))):
        ea = a[n] if n < len(a) else "<no line>"
        ab = b[n] if n < len(b) else "<no line>"
        if ea != ab:
            return n + 1, ea, ab
    return None


def check(blocks, root, quiet=False):
    bad = 0
    for blk in blocks:
        expected = normalize(blk.text)
        try:
            actual, code = run_spec(blk.spec, root)
        except FileNotFoundError as exc:
            print("DRIFT  %s:%d  command not runnable: %s" % (blk.path, blk.line_no, exc))
            bad += 1
            continue
        except ValueError as exc:
            print("DRIFT  %s:%d  %s" % (blk.path, blk.line_no, exc))
            bad += 1
            continue
        diff = first_diff(expected, actual)
        if diff is None:
            if not quiet:
                print("ok     %s:%d  %s (exit %d, %d line(s))"
                      % (blk.path, blk.line_no, blk.spec, code, len(expected.split("\n"))))
        else:
            n, ea, ab = diff
            print("DRIFT  %s:%d  %s" % (blk.path, blk.line_no, blk.spec))
            print("         line %d of the block: %s" % (n, ea))
            print("         line %d of the run  : %s" % (n, ab))
            bad += 1
    return bad


def cmd_default(files):
    root = os.getcwd()
    blocks, problems = [], []
    for pattern in files:
        candidates = sorted(__import__("glob").glob(pattern))
        for path in candidates:
            if not os.path.isfile(path):
                continue
            b, p = collect(path, root)
            blocks.extend(b)
            problems.extend(p)
    for p in problems:
        print("DRIFT  " + p)
    if not blocks and not problems:
        print("FAIL — no quoted-output marker found in %s. Nothing was compared, so nothing "
              "was verified." % ", ".join(files))
        return 1
    bad = check(blocks, root) + len(problems)
    if bad:
        print("\nFAIL — %d quoted block(s) disagree with the command that produces them." % bad)
        return 1
    print("\nOK: %d quoted block(s) match the command output." % len(blocks))
    return 0


def cmd_selftest():
    """Four controls, each of which must produce the verdict it names."""
    root = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="quoted-output-selftest-")
    ok_text = "first line\nsecond line"
    spec = "python -c \"print('first line');print('second line')\""
    doc = "\n".join([
        "<!-- quoted-output: %s -->" % spec,
        "```",
        ok_text,
        "```",
        "",
        "<!-- quoted-output: %s -->" % spec,
        "```",
        "first line",
        "second LINE",
        "```",
        "",
        "<!-- quoted-output: %s -->" % spec,
        "no block follows this marker",
        "",
    ])
    path = os.path.join(tmp, "fixture.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)

    b, problems = collect(path, root)
    controls = []

    # N1: the faithful block, alone, must pass.
    one = [x for x in b if x.text.strip() == ok_text]
    controls.append(("N1 faithful block passes", len(one) == 1 and check(one, root, quiet=True) == 0))

    # N2: the mutated block must be reported as drift.
    two = [x for x in b if "second LINE" in x.text]
    controls.append(("N2 one-word mutation is drift", len(two) == 1 and check(two, root, quiet=True) == 1))

    # N3: a marker without a block must be a problem, not a skip.
    controls.append(("N3 marker without a block fails", len(problems) == 1))

    # N4: finding nothing must fail rather than pass quietly.
    empty = os.path.join(tmp, "empty.md")
    with open(empty, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("no marker here\n")
    saved = sys.argv
    sys.argv = ["check-quoted-output.py", "--files", os.path.join(tmp, "empty.md")]
    try:
        rc = cmd_default([os.path.join(tmp, "empty.md")])
    finally:
        sys.argv = saved
    controls.append(("N4 zero markers fails loudly", rc == 1))

    width = max(len(n) for n, _ in controls)
    failed = 0
    for name, ok in controls:
        print("  %s %s" % ("PASS" if ok else "FAIL", name.ljust(width)))
        failed += 0 if ok else 1
    print()
    if failed:
        print("SELFTEST FAILED: %d control(s) did not behave as named." % failed)
        return 1
    print("SELFTEST PASSED: all 4 controls behave as named - drift fails, agreement passes, a marker promises a block, and an empty scan is not a green.")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="prove the four controls behave as named")
    ap.add_argument("--files", nargs="*", default=list(DEFAULT_FILES),
                    help="globs to scan, relative to the repository root")
    args = ap.parse_args(argv)
    if args.selftest:
        return cmd_selftest()
    return cmd_default(args.files)


if __name__ == "__main__":
    sys.exit(main())