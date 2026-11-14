#!/usr/bin/env python3
"""Assertions for the CI job `no coreutils`.

That job takes coreutils away from the hook's PATH. The interesting question is not
"did the job run", it is "did the hook lie" -- and the two lies it has told have exact
sentences:

  * `dirname: command not found` (or any `... is missing.`) -- the environment reported
    as a repository problem, at a moment when no gate had run;
  * `pre-commit: FAIL` lines with **empty bodies** -- every gate "failed" through an
    interpreter that exits and prints nothing.

This file is the judge for those two. It is deliberately not a gate: it does not
decide anything about the repository, only about a transcript a runner already
produced. Keeping it out of `.githooks/pre-commit` is why the hook's gate list stays
at its current size and parity is unaffected.

    python tools/no_coreutils_assert.py hook  <transcript> <exit-code>
    python tools/no_coreutils_assert.py stub  <transcript> <exit-code>
    python tools/no_coreutils_assert.py --selftest

`hook` expects: no lie sentences, and a verdict line that only prints after the last
gate (`all gates passed` or `commit blocked`). The exit code is reported, not required
to be 0: with a PATH that thin some gates legitimately cannot run, and demanding 0
would force this job to describe a run that proves nothing.

`stub` expects the opposite shape: the refusal, naming the interpreter it found and
rejected, and **no verdict line** -- because a verdict would mean the gates were run
through an interpreter that prints nothing.

`--selftest` runs six controls, three per mode: the defect-shaped transcript must be
rejected, the good transcript accepted, and a verdict through a dead interpreter
rejected. A judge that cannot fail is not a judge.

**Known blind spot, stated rather than papered over.** The second defect also produced
eighteen `pre-commit: FAIL` lines with *empty bodies*. From a transcript alone that is
indistinguishable from eighteen gates that failed for real: both print the same header
and no explanation. So this judge does **not** claim to catch it there; control 4 fixes
that transcript as *accepted*, and the shape is caught where it can be caught -- by the
`stub` mode, because a hook that refuses an interpreter which cannot run never reaches
a verdict at all.
"""

from __future__ import annotations

import sys

LIES = ("command not found", "is missing", "no usable Python interpreter found")
VERDICTS = ("pre-commit: all gates passed.", "pre-commit: commit blocked.")
REFUSAL = ("no usable Python interpreter found",
           "these were found but rejected:",
           "found, but it cannot run a trivial script")


def judge(mode, text, rc):
    """Return (ok, lines). lines carry ::error:: annotations for the runner."""
    if mode == "hook":
        bad = [s for s in LIES if s in text]
        if bad:
            return False, ["the hook reported its own environment as a repository problem: "
                           + ", ".join(repr(s) for s in bad)]
        if not any(s in text for s in VERDICTS):
            tail = text.strip().splitlines()[-8:]
            return False, ["the hook exited (rc=%d) without reaching a verdict; it did not "
                           "run its full list. Tail:" % rc] + ["    " + l for l in tail]
        return True, ["the hook started, ran its list, and reported a verdict (rc=%d)" % rc]

    if mode == "stub":
        missing = [s for s in REFUSAL if s not in text]
        if missing:
            return False, ["the hook used a stub interpreter instead of refusing it; missing: "
                           + ", ".join(repr(s) for s in missing)]
        if any(s in text for s in VERDICTS):
            return False, ["the hook reached a verdict through an interpreter that exits 49 "
                           "and prints nothing -- that is the second half of the defect"]
        if rc != 1:
            return False, ["refusal must exit 1, got %d" % rc]
        return True, ["refusal named the interpreter it found, and exited before running a gate"]

    return False, ["unknown mode %r" % mode]


def _run(mode, text, rc):
    ok, lines = judge(mode, text, rc)
    for line in lines:
        print(("::error::" if not ok else "") + line)
    return 0 if ok else 1


# ---------------------------------------------------------------- selftest fixtures

GOOD_HOOK = """\
pre-commit: all gates passed.
"""

FAILING_HOOK = """\
pre-commit: FAIL — release consistency
    gate 6 needs git, and this PATH has none
pre-commit: commit blocked. Fix the above, or if the manifest is stale:
"""

DIRNAME_LIE = """\
.githooks/pre-commit: line 118: dirname: command not found
pre-commit: FAIL — tools/gate-lint.py is missing. A gate that is not there is not a gate.
pre-commit: commit blocked. Fix the above, or if the manifest is stale:
"""

SILENT_GATES = """\
pre-commit: FAIL — gate-lint selftest
pre-commit: FAIL — catalog selftest
pre-commit: commit blocked. Fix the above, or if the manifest is stale:
"""

GOOD_STUB = """\
pre-commit: no usable Python interpreter found (looked for python3, python).
pre-commit: these were found but rejected:
    python3 -> /tmp/bare/python3 (found, but it cannot run a trivial script)
    python -> /tmp/bare/python (found, but it cannot run a trivial script)
pre-commit: refusing to commit. Install Python, or set PYTHON=/path/to/python.
"""

STUB_WITH_VERDICT = """\
pre-commit: these were found but rejected:
    python3 -> /tmp/bare/python3 (found, but it cannot run a trivial script)
pre-commit: no usable Python interpreter found (looked for python3, python).
pre-commit: all gates passed.
"""


def cmd_selftest():
    controls = [
        ("hook · a clean transcript is accepted", "hook", GOOD_HOOK, 0, 0),
        ("hook · a hook that ran and failed some gates is accepted", "hook", FAILING_HOOK, 1, 0),
        ("hook · the dirname lie is rejected", "hook", DIRNAME_LIE, 1, 1),
        # Stated as accepted on purpose: a transcript of empty-bodied FAIL lines cannot be
        # told apart from real failures, and this judge must not pretend otherwise. The
        # shape is caught by `stub`, where a refusing hook never prints a verdict.
        ("hook · empty-bodied failures are NOT distinguishable (known blind spot)",
         "hook", SILENT_GATES, 1, 0),
        ("stub · a refusal that names the interpreter is accepted", "stub", GOOD_STUB, 1, 0),
        ("stub · a verdict through a dead interpreter is rejected", "stub", STUB_WITH_VERDICT, 0, 1),
    ]
    red = 0
    for name, mode, text, rc, want in controls:
        ok, _ = judge(mode, text, rc)
        got = 0 if ok else 1
        flag = "ok" if got == want else "x"
        if got != want:
            red += 1
        print("  %s  %s  (want %d, got %d)" % (flag, name, want, got))
    print("selftest: %d controls, %d red" % (len(controls), red))
    if red:
        print("SELFTEST FAILED")
        return 1
    print("SELFTEST PASS")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        return cmd_selftest()
    if len(argv) != 3:
        print(__doc__)
        return 2
    mode, path, rc = argv[0], argv[1], int(argv[2])
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        print("::error::cannot read the transcript %s: %s" % (path, exc))
        return 1
    return _run(mode, text, rc)


if __name__ == "__main__":
    sys.exit(main())
