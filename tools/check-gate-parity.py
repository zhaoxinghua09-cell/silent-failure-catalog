#!/usr/bin/env python3
"""gate-parity -- the hook and CI must run the same gates, in the same order.

`.githooks/pre-commit` is the specification; `.github/workflows/gates.yml` says
so in its own header ("this file is its echo"). Two hand-written lists drift,
and this repository has already been bitten: on 2026-09-30 the hook ran five
gates while CI ran six, and nothing noticed until a human counted. The `N/M`
step labels exist for exactly that reason -- and a label is still only a label
until something reads it.

This gate reads them.

What it checks
  1. The hook's `run` list and the `gates` job's steps are the same ordered
     list of (script, arguments).
  2. Every step that runs a gate carries an `N/M` label, the labels are 1..M in
     order, and M equals the number of gate steps. A stale `/13` after a
     fourteenth gate is the same drift, one commit later.
  3. Declared exceptions are exact and still true. An exception is a triple
     (script, hook args, CI args). Edit either side and the triple stops
     matching, so the divergence cannot silently widen; and an exception that
     no longer describes a real difference is reported as stale, so the list
     cannot accumulate lies.

What it does not check
  * The `negative-control` job. It is a separate job with deliberately
    different arguments; it is not part of the shared list.
  * Whether a gate can fail. That is each gate's own `--selftest`, and
    `gate-lint.py` for the ones that do not carry one.

Known limit
  A gate deleted from *both* lists cannot be caught here: if both sides drop the
  same entry, they still agree. Catching that would need a second registry of
  "expected" gates, which is a second source of truth of exactly the kind this
  repository removes elsewhere (AGENTS.md rule 15). What remains over that hole
  is the `N/M` label discipline, the reviewer, and branch protection on the CI
  job -- all of them weaker than a gate, and stated here rather than implied.

Reading `gates.yml`
  This repository is stdlib-only and Python ships no YAML parser, so the
  workflow is read with a line scanner. It is deliberately narrow: it walks
  only the `gates:` job, and check 2 fails if the highest label disagrees with
  the number of steps found -- so a scan that silently drops a step fails
  loudly instead of passing quietly.

Exit status: 0 when the two lists agree, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

HOOK_REL = ".githooks/pre-commit"
WORKFLOW_REL = ".github/workflows/gates.yml"

# --------------------------------------------------------------------------- #
# Declared exceptions: real, intentional differences between the two lists.
# Each entry is (script, hook_args, ci_args, reason) with the argument tuples
# written out in full. Anything not listed here that differs is a failure.
# --------------------------------------------------------------------------- #
EXCEPTIONS: "list[tuple[str, tuple, tuple, str]]" = [
    (
        "tools/verify_release_consistency.py",
        ("--repo-path", ".", "--no-remote"),
        ("--repo-path", ".", "--repo", "${{ github.repository }}"),
        "the hook runs offline by design (--no-remote); CI resolves the tag "
        "through the API, which needs --repo <owner/repo> and GH_TOKEN",
    ),
]


class GateParityError(Exception):
    """A structural problem: the input could not be read as expected."""


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

HOOK_RUN = re.compile(r'^run\s+"[^"]*"\s+(\S+)(?:\s+(.*?))?\s*$')
JOB_KEY = re.compile(r"^  (\S+):\s*$")
CI_STEP = re.compile(r"^\s+- name:\s*(.*?)\s*$")
CI_RUN = re.compile(r"^\s+run:\s*(.*?)\s*$")
CI_GATE_CMD = re.compile(r"^python\s+((?:tools|examples)/\S+)(?:\s+(.*))?$")
CI_LABEL = re.compile(r"^(\d+)\s*/\s*(\d+)\b")


def parse_hook(text: str) -> "list[tuple[int, str, tuple]]":
    """Return [(line, script, args)] for every `run "label" <script> <args>`."""
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = HOOK_RUN.match(line)
        if m is None:
            continue
        script = m.group(1)
        args = tuple(shlex.split(m.group(2) or ""))
        found.append((lineno, script, args))
    return found


def _gates_job_span(lines: "list[str]") -> "tuple[int, int]":
    """Line span [start, end) of the body of the `gates:` job."""
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == "  gates:":
            start = i + 1
            break
    if start is None:
        raise GateParityError("no `gates:` job found in " + WORKFLOW_REL)
    for j in range(start, len(lines)):
        if JOB_KEY.match(lines[j]) is not None:
            return start, j
    return start, len(lines)


def parse_ci(text: str) -> "list[tuple[int, str, str, tuple]]":
    """Return [(line, label, script, args)] for gate steps in the `gates` job."""
    lines = text.splitlines()
    start, end = _gates_job_span(lines)
    steps = []
    last_name = None
    last_name_line = None
    for k in range(start, end):
        line = lines[k]
        m = CI_STEP.match(line)
        if m is not None:
            last_name = m.group(1)
            last_name_line = k + 1
            continue
        r = CI_RUN.match(line)
        if r is None:
            continue
        command = r.group(1)
        g = CI_GATE_CMD.match(command)
        if g is not None and last_name is not None:
            steps.append(
                (
                    last_name_line,
                    last_name,
                    g.group(1),
                    tuple(shlex.split(g.group(2) or "")),
                )
            )
        # A `run:` that is not a gate step (e.g. `python -VV`) ends the step.
        last_name = None
        last_name_line = None
    return steps


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def check_labels(ci: "list[tuple[int, str, str, tuple]]") -> "list[str]":
    """Labels must be 1..M in order, and M must equal the number of steps."""
    problems = []
    if not ci:
        return ["no gate steps found in the `gates:` job"]
    declared = None
    for position, (lineno, label, script, _) in enumerate(ci, 1):
        m = CI_LABEL.match(label)
        if m is None:
            problems.append(
                "line %d: step running %s carries no `N/M` label (%r); the "
                "label is what makes a stale sync visible" % (lineno, script, label)
            )
            continue
        num, total = int(m.group(1)), int(m.group(2))
        if num != position:
            problems.append(
                "line %d: expected label %d/M but found %d/%d"
                % (lineno, position, num, total)
            )
        if declared is None:
            declared = total
        elif total != declared:
            problems.append(
                "line %d: label total %d disagrees with %d seen earlier"
                % (lineno, total, declared)
            )
    if declared is not None and declared != len(ci):
        problems.append(
            "the labels claim %d gates but %d gate steps were found"
            % (declared, len(ci))
        )
    return problems


def check_parity(
    hook: "list[tuple[int, str, tuple]]",
    ci: "list[tuple[int, str, str, tuple]]",
    exceptions: "list[tuple[str, tuple, tuple, str]]" = None,
) -> "list[str]":
    """The two gate lists must be equal, up to the declared exceptions."""
    if exceptions is None:
        exceptions = list(EXCEPTIONS)
    problems = []

    if len(hook) != len(ci):
        problems.append(
            "the hook runs %d gate(s) but the `gates:` job runs %d" % (len(hook), len(ci))
        )

    hook_only = [script for _, script, _ in hook]
    ci_only = [script for _, _, script, _ in ci]

    for position, (h, c) in enumerate(zip(hook, ci), 1):
        h_line, h_script, h_args = h
        c_line, _c_label, c_script, c_args = c
        if h_script != c_script:
            problems.append(
                "step %d: the hook runs %s (line %d) but CI runs %s (line %d)"
                % (position, h_script, h_line, c_script, c_line)
            )
            continue
        if h_args == c_args:
            continue
        if any(
            e[0] == h_script and e[1] == h_args and e[2] == c_args for e in exceptions
        ):
            continue
        problems.append(
            "step %d: %s takes different arguments -- hook %s (line %d) vs CI %s "
            "(line %d)" % (position, h_script, list(h_args), h_line, list(c_args), c_line)
        )

    if len(hook) != len(ci):
        extra_h = hook_only[len(ci):] if len(hook) > len(ci) else []
        extra_c = ci_only[len(hook):] if len(ci) > len(hook) else []
        for script in extra_h:
            problems.append("only in the hook: %s" % script)
        for script in extra_c:
            problems.append("only in CI: %s" % script)

    # An exception that is no longer a real difference is a stale claim.
    for script, h_args, c_args, reason in exceptions:
        matched = False
        for h, c in zip(hook, ci):
            if h[1] == script and c[2] == script and h[2] == h_args and c[3] == c_args:
                matched = True
                break
        if not matched:
            problems.append(
                "declared exception for %s no longer describes a real difference "
                "-- hook %s vs CI %s; remove it or update it (reason on file: %s)"
                % (script, list(h_args), list(c_args), reason)
            )

    return problems


# --------------------------------------------------------------------------- #
# Self test: every check must be shown able to fail.
# --------------------------------------------------------------------------- #

def _quote_args(args: "tuple") -> str:
    """Re-quote a parsed argv so the fixture text round-trips through shlex.

    A fixture that drops quotes does not test the parser, it tests the fixture:
    `${{ github.repository }}` would come back as three tokens and the control
    would fail for the wrong reason.
    """
    out = []
    for token in args:
        if token == "" or any(c in token for c in ' \t"$'):
            out.append('"%s"' % token.replace("\\", "\\\\").replace('"', '\\"'))
        else:
            out.append(token)
    return " ".join(out)


def _hook_text(pairs: "list[tuple[str, tuple]]") -> str:
    out = ["#!/bin/sh", "set -u", ""]
    for i, (script, args) in enumerate(pairs, 1):
        out.append('run "gate %d" %s %s' % (i, script, _quote_args(args)))
    return "\n".join(out) + "\n"


def _ci_text(
    pairs: "list[tuple[str, tuple]]",
    label_total: "int | None" = None,
    hide_label_at: "int | None" = None,
) -> str:
    total = len(pairs) if label_total is None else label_total
    out = [
        "name: gates",
        "jobs:",
        "  gates:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "      - name: Interpreter under test",
        "        run: python -VV",
    ]
    for i, (script, args) in enumerate(pairs, 1):
        name = "unnamed gate" if hide_label_at == i else "%d/%d gate" % (i, total)
        out.append("      - name: %s" % name)
        out.append("        if: always()")
        out.append(
            "        run: python %s%s"
            % (script, (" " + _quote_args(args)) if args else "")
        )
    out.append("  negative-control:")
    out.append("    runs-on: ubuntu-latest")
    out.append("    steps:")
    out.append("      - name: A - passes")
    out.append("        run: python tools/make-manifest.py --check")
    return "\n".join(out) + "\n"


BASE = [
    ("tools/gate-lint.py", ("--selftest",)),
    ("tools/check-catalog.py", ()),
    ("tools/check-catalog.py", ("--scan-leaks",)),
    ("tools/check-line-endings.py", ()),
]


def _run_case(name, hook_pairs, ci_pairs, expect_problems, exceptions=None, **ci_kw):
    hook = parse_hook(_hook_text(hook_pairs))
    ci = parse_ci(_ci_text(ci_pairs, **ci_kw))
    exc = list(EXCEPTIONS) if exceptions is None else exceptions
    problems = check_parity(hook, ci, exceptions=exc) + check_labels(ci)
    got = len(problems) > 0
    ok = got == expect_problems
    return ok, name, expect_problems, problems


def selftest() -> int:
    """Prove every check can fail: three green controls, five red controls."""
    cases = []

    # --- green controls: these must stay silent ---
    # BASE contains no excepted script, so the exception list is empty here: an
    # exception that names a script the fixture does not contain is stale by
    # definition, and the stale-exception check below relies on that.
    cases.append(_run_case("identical lists pass", BASE, BASE, False, exceptions=[]))
    cases.append(
        _run_case(
            "declared exception is honoured",
            [(EXCEPTIONS[0][0], EXCEPTIONS[0][1])],
            [(EXCEPTIONS[0][0], EXCEPTIONS[0][2])],
            False,
        )
    )

    # --- red controls: each must be caught ---
    cases.append(
        _run_case("CI is missing a gate", BASE, BASE[:-1], True)
    )
    cases.append(
        _run_case("the hook is missing a gate", BASE[:-1], BASE, True)
    )
    cases.append(
        _run_case(
            "an argument differs",
            [("tools/check-line-endings.py", ("--selftest",))],
            [("tools/check-line-endings.py", ())],
            True,
        )
    )
    cases.append(
        _run_case("a label is missing", BASE, BASE, True, hide_label_at=2)
    )
    cases.append(
        _run_case(
            "the label total is stale", BASE, BASE, True, label_total=len(BASE) - 1
        )
    )
    # Dead control for the exception machinery itself: nudge one character of an
    # excepted pair and the exception must stop matching.
    cases.append(
        _run_case(
            "an edited exception stops matching",
            [("tools/verify_release_consistency.py", ("--repo-path", ".", "--no-remote"))],
            [("tools/verify_release_consistency.py", ("--repo-path", ".", "--repo"))],
            True,
        )
    )
    # An exception that no longer describes a difference is a stale claim.
    hook = parse_hook(_hook_text([("tools/verify_release_consistency.py", ("--repo-path", ".", "--no-remote"))]))
    ci = parse_ci(_ci_text([("tools/verify_release_consistency.py", ("--repo-path", ".", "--no-remote"))]))
    stale = check_parity(hook, ci, exceptions=list(EXCEPTIONS)) + check_labels(ci)
    cases.append((len(stale) > 0, "a stale exception is reported", True, stale))

    # A step with no label at all in an otherwise well-formed file.
    cases.append(
        _run_case(
            "a step running a gate with no label is caught",
            BASE,
            BASE,
            True,
            hide_label_at=1,
        )
    )

    failures = 0
    for ok, name, expected_red, problems in cases:
        want = "red" if expected_red else "green"
        if ok:
            print("  ok    %-46s (wanted %s)" % (name, want))
        else:
            failures += 1
            print("  FAIL  %-46s (wanted %s, got %d problem(s))" % (name, want, len(problems)))
            for p in problems:
                print("          - %s" % p)

    print("")
    if failures:
        print("gate-parity: selftest FAILED -- %d control(s) misbehaved." % failures)
        return 1
    print("gate-parity: selftest passed (%d controls)." % len(cases))
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-path",
        default=str(Path(__file__).resolve().parents[1]),
        help="repository root (default: the parent of this script's directory)",
    )
    parser.add_argument("--selftest", action="store_true", help="prove this gate can fail")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = Path(args.repo_path)
    hook_path = root / HOOK_REL
    wf_path = root / WORKFLOW_REL
    for p in (hook_path, wf_path):
        if not p.is_file():
            print("gate-parity: FAILED -- %s is missing." % p, file=sys.stderr)
            print("gate-parity: a file that is not there cannot be compared.", file=sys.stderr)
            return 1

    try:
        hook = parse_hook(hook_path.read_text(encoding="utf-8"))
        ci = parse_ci(wf_path.read_text(encoding="utf-8"))
    except GateParityError as exc:
        print("gate-parity: FAILED -- %s" % exc, file=sys.stderr)
        return 1

    if not hook:
        print(
            "gate-parity: FAILED -- no `run` lines found in %s. An empty list is "
            "not an agreeing list." % HOOK_REL,
            file=sys.stderr,
        )
        return 1

    problems = check_parity(hook, ci) + check_labels(ci)
    if problems:
        print("gate-parity: the hook and CI have drifted.", file=sys.stderr)
        for p in problems:
            print("  - %s" % p, file=sys.stderr)
        print("", file=sys.stderr)
        print("gate 14 FAILED: %s" % WORKFLOW_REL, file=sys.stderr)
        return 1

    print(
        "OK: hook and CI agree on %d gate(s), labels 1/%d..%d/%d, %d declared "
        "exception(s)." % (len(hook), len(ci), len(ci), len(ci), len(EXCEPTIONS))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
