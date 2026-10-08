#!/usr/bin/env python3
"""gate-parity -- the hook and CI must run the same gates, in the same order.

`.githooks/pre-commit` is the specification; `.github/workflows/gates.yml` says
so in its own header ("this file is its echo"). Those two used to be two
hand-written lists, and they drifted: on 2026-09-30 the hook ran five gates
while CI ran six, and nothing noticed until a human counted. The `N/M` step
labels exist for exactly that reason -- and a label is still only a label until
something reads it.

This gate reads them. As of 2026-10-08 it also *writes* one of them.

What it checks
  1. The hook's `run` list and the `gates` job's steps are the same ordered
     list of (script, arguments).
  2. Every step that runs a gate carries an `N/M` label, the labels are 1..M in
     order, and M equals the number of gate steps. A stale `/13` after a
     fourteenth gate is the same drift, one commit later.
  3. Every `# ci-only:` override in the hook names a gate that exists and really
     changes that gate's arguments. An override that no longer describes a real
     difference is reported as stale, so the list cannot accumulate lies. There
     is no separate exception table any more: the one declared difference lives
     on gate 6's own line in the hook.
  4. Neither list runs the same (script, arguments) pair twice. The same script
     with different arguments is fine -- `check-catalog.py` runs twice on
     purpose; the same pair twice is a duplicate, and a duplicate added to both
     lists is the one symmetric edit a local invariant can still see.
  5. The CI step block between the two `GENERATED GATE STEPS` markers equals
     what `--emit-ci` produces from the hook, byte for byte.

What it does not check
  * The `negative-control` job. It is a separate job with deliberately
    different arguments; it is not part of the shared list.
  * Whether a gate can fail. That is each gate's own `--selftest`, and
    `gate-lint.py` for the ones that do not carry one.

Which drift shapes this closes, and which one it cannot
  Check 1 alone could never catch an edit applied to *both* lists at once,
  because both sides still agreed. Three shapes were measured on 2026-10-08
  (independent review, 14 mutated copies); all three came back green:

    H1  the same gate added to both lists (copy-paste);
    H3  the same gate's arguments changed on both sides;
    --  the same gate dropped from both lists, labels renumbered.

  Generating the CI side closes H1 and H3 structurally, not by detection:
  there is no longer a place to add a gate that the hook does not have, and no
  place to write different arguments. Checks 4 and 5 are the backstops if
  someone edits the generated block by hand anyway.

  The third shape -- H2, a gate deleted from the hook and the block regenerated
  -- REMAINS OPEN, and it is not closable here. Both sides derive from one
  source, so the comparison re-establishes agreement the moment the source
  loses a line; a single source cannot witness its own omission. Closing H2
  needs a second registry of expected gates, which is the second source of
  truth this repository forbids. This is measured, not asserted: control N7 in
  `--selftest` deletes a gate from the hook fixture, regenerates the block, and
  requires the result to be GREEN. It is expected to stay green. It is recorded
  so that "the drift is closed" is never claimed for it.

  What H2 costs is bounded though, and the bound is worth stating: deletion now
  happens in ONE place, on one line of one file, so a diff shows it. It is
  visible, it is just not checked.

Reading `gates.yml`
  This repository is stdlib-only and Python ships no YAML parser, so the
  workflow is read with a line scanner. It is deliberately narrow: it walks
  only the `gates:` job, and check 2 fails if the highest label disagrees with
  the number of steps found -- so a scan that silently drops a step fails
  loudly instead of passing quietly. The same reasoning applies to reading the
  hook: `parse_hook` counts the lines that begin with `run ` and refuses to
  return a shorter list than it saw, because a regex that quietly stops matching
  would drop a gate from the specification without saying so.

Exit status: 0 when the two lists agree, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from collections import namedtuple
from pathlib import Path

HOOK_REL = ".githooks/pre-commit"
WORKFLOW_REL = ".github/workflows/gates.yml"

Gate = namedtuple("Gate", "lineno name note script args")

CI_INDENT = "      "
CI_BEGIN = "      # BEGIN GENERATED GATE STEPS -- edit .githooks/pre-commit, then"
CI_END = "      # END GENERATED GATE STEPS"

PROLOGUE = (
    "      # Every gate carries `if: always()` so that a failure in one does not hide\n"
    "      # the state of the others: the job is red if any gate failed, and the report\n"
    "      # is the complete list rather than the first casualty.\n"
)


class GateParityError(Exception):
    """A structural problem: the input could not be read as expected."""


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

HOOK_RUN = re.compile(r'^run\s+"([^"]*)"\s+"([^"]*)"\s+(\S+)(?:\s+(.*?))?\s*$')
HOOK_RUN_START = re.compile(r"^\s*run\s+")
HOOK_CI_ONLY = re.compile(r"^\s*#\s*ci-only:\s+(\S+)\s*(.*?)\s*$")
JOB_KEY = re.compile(r"^  (\S+):\s*$")
CI_STEP = re.compile(r"^\s+- name:\s*(.*?)\s*$")
CI_RUN = re.compile(r"^\s+run:\s*(.*?)\s*$")
CI_GATE_CMD = re.compile(r"^python\s+((?:tools|examples)/\S+)(?:\s+(.*))?$")
CI_LABEL = re.compile(r"^(\d+)\s*/\s*(\d+)\b")


def _strip_quotes(text: str) -> str:
    """Unquote a YAML scalar if it is wholly quoted.

    The generator writes step names as `"6/15 release consistency (...)"`, and a
    scanner that kept the quotes would fail to see the `N/M` label inside one --
    check 2 would report a missing label on a perfectly labelled step, which is
    a false alarm in the direction that trains people to ignore alarms.
    """
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_hook(text: str) -> "list[Gate]":
    """Return the hook's gates, in order.

    Every line that begins with `run ` must parse. The count is enforced rather
    than trusted: a regexp that stops matching half way through the list would
    remove gates from the specification silently, and this gate would then
    happily report that CI agrees with a truncated list.
    """
    gates = []
    started = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if HOOK_RUN_START.match(line):
            started += 1
        m = HOOK_RUN.match(line)
        if m is None:
            continue
        gates.append(
            Gate(lineno, m.group(1), m.group(2), m.group(3),
                 tuple(shlex.split(m.group(4) or "")))
        )
    if started != len(gates):
        raise GateParityError(
            "%d line(s) in %s begin with `run ` but only %d parsed as a gate; "
            "the unparsed ones are being dropped from the specification"
            % (started, HOOK_REL, len(gates))
        )
    return gates


def parse_ci_only(text: str) -> "dict[str, tuple]":
    """Return {script: ci_args} for every `# ci-only:` line in the hook."""
    overrides = {}
    for line in text.splitlines():
        m = HOOK_CI_ONLY.match(line)
        if m is None:
            continue
        overrides[m.group(1)] = tuple(shlex.split(m.group(2) or ""))
    return overrides


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
            last_name = _strip_quotes(m.group(1))
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
# The generator
# --------------------------------------------------------------------------- #

def ci_args_for(gate: Gate, overrides: "dict[str, tuple]") -> tuple:
    """The arguments CI should use for this gate."""
    return overrides.get(gate.script, gate.args)


def emit_ci(
    hook: "list[Gate]",
    overrides: "dict[str, tuple]",
    indent: str = CI_INDENT,
) -> str:
    """Render the CI step block for the `gates:` job from the hook.

    The hook is the specification; this is the echo, written by a program
    instead of by hand. The returned text is exactly what must appear between
    the two markers in `gates.yml`.

    This is the whole point of the change: a gate that exists only in CI is not
    detected here, it is *impossible* here -- the block is overwritten from the
    hook every time, and check 5 fails if anyone writes to it by hand.
    """
    total = len(hook)
    lines = [PROLOGUE.rstrip("\n")]
    for i, gate in enumerate(hook, 1):
        name = "%d/%d %s" % (i, total, gate.name)
        if gate.note:
            name += " (%s)" % gate.note
        args = ci_args_for(gate, overrides)
        command = "python %s%s" % (
            gate.script, (" " + _quote_args(args)) if args else ""
        )
        lines.append('%s- name: "%s"' % (indent, name))
        lines.append("%s  if: always()" % indent)
        lines.append("%s  run: %s" % (indent, command))
    return "\n".join(lines) + "\n"


def emit_region(hook: "list[Gate]", overrides: "dict[str, tuple]") -> str:
    """The whole replaceable region, markers included."""
    return CI_BEGIN + "\n" + emit_ci(hook, overrides) + "\n" + CI_END + "\n"


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
    hook: "list[Gate]",
    ci: "list[tuple[int, str, str, tuple]]",
    overrides: "dict[str, tuple] | None" = None,
) -> "list[str]":
    """The two gate lists must be equal, up to the `# ci-only:` overrides."""
    if overrides is None:
        overrides = {}
    problems = []

    if len(hook) != len(ci):
        problems.append(
            "the hook runs %d gate(s) but the `gates:` job runs %d" % (len(hook), len(ci))
        )

    for position, (h, c) in enumerate(zip(hook, ci), 1):
        c_line, _c_label, c_script, c_args = c
        if h.script != c_script:
            problems.append(
                "step %d: the hook runs %s (line %d) but CI runs %s (line %d)"
                % (position, h.script, h.lineno, c_script, c_line)
            )
            continue
        expected = ci_args_for(h, overrides)
        if expected == c_args:
            continue
        problems.append(
            "step %d: %s should run with %s in CI (hook line %d) but CI has %s "
            "(line %d)" % (position, h.script, list(expected), h.lineno,
                           list(c_args), c_line)
        )

    if len(hook) != len(ci):
        if len(hook) > len(ci):
            for gate in hook[len(ci):]:
                problems.append("only in the hook: %s" % gate.script)
        else:
            for step in ci[len(hook):]:
                problems.append("only in CI: %s" % step[2])

    # An override that is no longer a real difference is a stale claim.
    for script, args in overrides.items():
        matching = [g for g in hook if g.script == script]
        if not matching:
            problems.append(
                "the `# ci-only:` override for %s names no gate in the hook; it "
                "is describing something that is not there" % script
            )
        elif not any(ci_args_for(g, overrides) != g.args for g in matching):
            problems.append(
                "the `# ci-only:` override for %s is stale -- it gives CI exactly "
                "the arguments the hook already uses, so it describes no difference"
                % script
            )

    return problems


def check_unique(
    hook: "list[Gate]",
    ci: "list[tuple[int, str, str, tuple]]",
) -> "list[str]":
    """Neither list may run the same (script, arguments) pair more than once.

    A gate duplicated in one list and then in the other leaves the two lists in
    perfect agreement, so check 1 cannot see it. This one can, and it needs no
    second registry of expected gates: running a gate twice is a contradiction
    inside the list itself.

    The same *script* with different arguments stays legal and expected --
    `check-catalog.py` runs twice, once for the catalog and once for leaks.
    """
    problems = []
    sides = (
        ("the hook", [(g.script, g.args) for g in hook]),
        ("CI", [(step[2], step[3]) for step in ci]),
    )
    for side, pairs in sides:
        first_seen = {}
        for position, key in enumerate(pairs, 1):
            if key in first_seen:
                problems.append(
                    "%s runs %s %s twice (steps %d and %d); the second is a "
                    "duplicate, not a gate"
                    % (side, key[0], list(key[1]), first_seen[key], position)
                )
            else:
                first_seen[key] = position
    return problems


def check_emit(
    workflow_text: str,
    hook: "list[Gate]",
    overrides: "dict[str, tuple]",
) -> "list[str]":
    """The CI step block must equal what `emit_ci()` would produce.

    This is what makes "a gate added to CI but not to the hook" impossible
    rather than merely detectable: there is no longer a place to add one.
    """
    n_begin = workflow_text.count(CI_BEGIN)
    n_end = workflow_text.count(CI_END)
    if n_begin != 1 or n_end != 1:
        return [
            "expected exactly one generated block in %s; found %d BEGIN and %d "
            "END marker(s). A second block would be a gate list nothing "
            "generates." % (WORKFLOW_REL, n_begin, n_end)
        ]
    start = workflow_text.index(CI_BEGIN) + len(CI_BEGIN)
    end = workflow_text.index(CI_END)
    actual = workflow_text[start:end]
    expected = "\n" + emit_ci(hook, overrides) + "\n"
    if actual != expected:
        return [
            "the CI step block does not match `--emit-ci` output; re-run "
            "`python tools/check-gate-parity.py --emit-ci` and replace the "
            "region between the markers"
        ]
    return []


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


def _hook_text(pairs: "list[tuple[str, tuple]]", notes=None) -> str:
    """A hook fixture in the real format: run "<name>" "<note>" <script> <args>."""
    out = ["#!/bin/sh", "set -u", ""]
    for i, (script, args) in enumerate(pairs, 1):
        note = "" if notes is None else notes.get(script, "")
        name = "%s gate %d" % (Path(script).stem.replace("_", " "), i)
        out.append('run "%s" "%s" %s %s' % (name, note, script, _quote_args(args)))
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


def _wf_with_block(hook: "list[Gate]", overrides: "dict[str, tuple]", block=None) -> str:
    """A workflow fixture carrying a generated block.

    `block` defaults to what the generator produces, so the green control is
    "the generator's own output is accepted" -- which is the property check 5
    has to have before it can be trusted to reject anything.
    """
    if block is None:
        block = emit_ci(hook, overrides)
    head = "name: gates\njobs:\n  gates:\n    runs-on: ubuntu-latest\n    steps:\n"
    tail = "  negative-control:\n    runs-on: ubuntu-latest\n"
    return head + CI_BEGIN + "\n" + block + "\n" + CI_END + "\n" + tail


BASE = [
    ("tools/gate-lint.py", ("--selftest",)),
    ("tools/check-catalog.py", ()),
    ("tools/check-catalog.py", ("--scan-leaks",)),
    ("tools/check-line-endings.py", ()),
]

RELEASE = "tools/verify_release_consistency.py"
HOOK_ARGS = ("--repo-path", ".", "--no-remote")
CI_ARGS = ("--repo-path", ".", "--repo", "${{ github.repository }}")


def _run_case(name, hook_pairs, ci_pairs, expect_problems, overrides=None, **ci_kw):
    hook = parse_hook(_hook_text(hook_pairs))
    ci = parse_ci(_ci_text(ci_pairs, **ci_kw))
    ov = {} if overrides is None else overrides
    problems = check_parity(hook, ci, ov) + check_labels(ci) + check_unique(hook, ci)
    got = len(problems) > 0
    ok = got == expect_problems
    return ok, name, expect_problems, problems


def _emit_case(name, hook_pairs, expect_problems, mutate=None, notes=None, overrides=None):
    """A control over check 5: build a block, optionally damage it, compare."""
    hook = parse_hook(_hook_text(hook_pairs, notes=notes))
    ov = {} if overrides is None else overrides
    block = mutate(emit_ci(hook, ov)) if mutate else None
    wf = _wf_with_block(hook, ov, block=block)
    problems = check_emit(wf, hook, ov)
    got = len(problems) > 0
    ok = got == expect_problems
    return ok, name, expect_problems, problems


def selftest() -> int:
    """Prove every check can fail: each control states the verdict it wants.

    No count is written here. The number of controls is printed from `cases`,
    and a number typed into a comment is a second source that only the code can
    keep true -- which is the drift this gate exists to catch.
    """
    cases = []

    # --- green controls: these must stay silent ---
    cases.append(_run_case("identical lists pass", BASE, BASE, False, overrides={}))
    cases.append(
        _run_case(
            "a ci-only override is honoured",
            [(RELEASE, HOOK_ARGS)],
            [(RELEASE, CI_ARGS)],
            False,
            overrides={RELEASE: CI_ARGS},
        )
    )

    # --- red controls: each must be caught ---
    cases.append(_run_case("CI is missing a gate", BASE, BASE[:-1], True))
    cases.append(_run_case("the hook is missing a gate", BASE[:-1], BASE, True))
    cases.append(
        _run_case(
            "an argument differs",
            [("tools/check-line-endings.py", ("--selftest",))],
            [("tools/check-line-endings.py", ())],
            True,
        )
    )
    cases.append(_run_case("a label is missing", BASE, BASE, True, hide_label_at=2))
    cases.append(
        _run_case("the label total is stale", BASE, BASE, True, label_total=len(BASE) - 1)
    )
    # Dead control for the override machinery: nudge one character of the
    # overridden pair and the override must stop matching.
    cases.append(
        _run_case(
            "an edited override stops matching",
            [(RELEASE, HOOK_ARGS)],
            [(RELEASE, ("--repo-path", ".", "--repo"))],
            True,
            overrides={RELEASE: CI_ARGS},
        )
    )
    # An override that no longer describes a difference is a stale claim.
    cases.append(
        _run_case(
            "a stale override is reported",
            [(RELEASE, HOOK_ARGS)],
            [(RELEASE, HOOK_ARGS)],
            True,
            overrides={RELEASE: HOOK_ARGS},
        )
    )
    # ...and one that names a gate that does not exist.
    cases.append(
        _run_case(
            "an override naming no gate is reported",
            BASE,
            BASE,
            True,
            overrides={"tools/nowhere.py": ("--x",)},
        )
    )
    cases.append(
        _run_case("a step running a gate with no label is caught", BASE, BASE, True,
                  hide_label_at=1)
    )

    # Dead control for check 4. The same gate is appended to *both* lists, which
    # is precisely the symmetric edit check 1 is blind to; check 4 must see it.
    # If this control ever passes green, check 4 is decoration.
    dup = list(BASE) + [BASE[0]]
    cases.append(_run_case("the same gate twice in both lists", dup, dup, True))
    # ...and the guard against over-tightening it: BASE already runs
    # check-catalog.py twice with different arguments, and the green control
    # above covers it. A check that flagged that would be the wrong check.

    # --- check 5, N1..N7: the generated block ---
    # N1  positive control: the generator's own output is accepted.
    cases.append(_emit_case("N1 the generator's output is accepted", BASE, False))
    # N2  2026-09-30's shape: a gate added to CI and not to the hook.
    cases.append(
        _emit_case(
            "N2 a gate hand-added to the block is caught",
            BASE,
            True,
            mutate=lambda b: b + '      - name: "5/4 smuggled"\n'
                                 "        if: always()\n"
                                 "        run: python tools/make-manifest.py --check\n",
        )
    )
    # N3  H3's shape: an argument changed inside the block.
    cases.append(
        _emit_case(
            "N3 an argument changed inside the block is caught",
            BASE,
            True,
            mutate=lambda b: b.replace(
                "python tools/check-catalog.py --scan-leaks",
                "python tools/check-catalog.py --scan-leaks --quiet",
            ),
        )
    )
    # N4  a gate deleted from the block. The deleted text is taken from the
    # generator's own output rather than typed out, so the control cannot pass
    # by failing to match anything -- a mutation that does not mutate is a
    # control that tests nothing.
    _one_step = (
        '      - name: "3/4 check-catalog gate 3"\n'
        "        if: always()\n"
        "        run: python tools/check-catalog.py --scan-leaks\n"
    )
    cases.append(
        _emit_case(
            "N4 a gate deleted from the block is caught",
            BASE,
            True,
            mutate=lambda b, _s=_one_step: b.replace(_s, "") if _s in b else b,
        )
    )
    # N5  the hook moved on and the block was not regenerated: a gate is added
    # to the hook, the workflow still shows the old block.
    hook_full = parse_hook(_hook_text(BASE))
    hook_more = parse_hook(_hook_text(BASE + [("tools/make-manifest.py", ("--check",))]))
    cases.append(
        (
            len(check_emit(_wf_with_block(hook_full, {}), hook_more, {})) > 0,
            "N5 a block not regenerated after the hook grew is caught",
            True,
            check_emit(_wf_with_block(hook_full, {}), hook_more, {}),
        )
    )
    # N5b  ...and after the hook shrank. This is the mirror of N7 and the reason
    # N7's green verdict is about one direction only.
    cases.append(
        (
            len(check_emit(_wf_with_block(hook_more, {}), hook_full, {})) > 0,
            "N5b a block not regenerated after the hook shrank is caught",
            True,
            check_emit(_wf_with_block(hook_more, {}), hook_full, {}),
        )
    )
    # N6  the round trip that actually carries punctuation: the emitted run line
    # contains `"${{ github.repository }}"`, which is where quoting breaks if it
    # is going to.
    cases.append(
        _emit_case(
            "N6 a block containing shell-quoted arguments round-trips",
            [(RELEASE, HOOK_ARGS)],
            False,
            overrides={RELEASE: CI_ARGS},
        )
    )
    # N7  THE HONESTY CONTROL. A gate is deleted from the hook and the block is
    # regenerated from it: both sides agree, so this is GREEN. It must stay
    # green. It is here so that "the drift is closed" is never claimed for this
    # shape -- H2 is open, and this control is the evidence.
    hook_minus = parse_hook(_hook_text(BASE[:-1]))
    wf_minus = _wf_with_block(hook_minus, {})
    h2 = check_emit(wf_minus, hook_minus, {}) + check_parity(
        hook_minus, parse_ci(wf_minus), {}
    )
    cases.append((len(h2) == 0,
                  "N7 a gate lost by the hook is NOT caught (H2 stays open)",
                  False, h2))
    # ...and the matching red control, so N7 cannot be satisfied by check 5
    # being broken into always-green: the *same* generator, asked about the
    # larger hook, must reject that block.
    cases.append((len(check_emit(wf_minus, parse_hook(_hook_text(BASE)), {})) > 0,
                  "N7b the same block against the fuller hook is caught",
                  True, check_emit(wf_minus, parse_hook(_hook_text(BASE)), {})))

    failures = 0
    for ok, name, expected_red, problems in cases:
        want = "red" if expected_red else "green"
        if ok:
            print("  ok    %-56s (wanted %s)" % (name, want))
        else:
            failures += 1
            print("  FAIL  %-56s (wanted %s, got %d problem(s))" % (name, want, len(problems)))
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

def _load(root: Path) -> "tuple[list[Gate], dict[str, tuple], str]":
    hook_path = root / HOOK_REL
    wf_path = root / WORKFLOW_REL
    for p in (hook_path, wf_path):
        if not p.is_file():
            raise GateParityError(
                "%s is missing. A file that is not there cannot be compared." % p
            )
    hook_text = hook_path.read_text(encoding="utf-8")
    hook = parse_hook(hook_text)
    if not hook:
        raise GateParityError(
            "no `run` lines found in %s. An empty list is not an agreeing list."
            % HOOK_REL
        )
    return hook, parse_ci_only(hook_text), wf_path.read_text(encoding="utf-8")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-path",
        default=str(Path(__file__).resolve().parents[1]),
        help="repository root (default: the parent of this script's directory)",
    )
    parser.add_argument("--selftest", action="store_true", help="prove this gate can fail")
    parser.add_argument(
        "--emit-ci",
        action="store_true",
        help="print the generated region of %s on stdout and exit" % WORKFLOW_REL,
    )
    parser.add_argument(
        "--check-emit",
        action="store_true",
        help="only run check 5 (the CI block equals the generator's output)",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = Path(args.repo_path)
    try:
        hook, overrides, workflow_text = _load(root)
    except GateParityError as exc:
        print("gate-parity: FAILED -- %s" % exc, file=sys.stderr)
        return 1

    if args.emit_ci:
        sys.stdout.write(emit_region(hook, overrides))
        return 0

    problems = []
    if args.check_emit:
        problems += check_emit(workflow_text, hook, overrides)
    else:
        ci = parse_ci(workflow_text)
        problems += check_parity(hook, ci, overrides)
        problems += check_labels(ci)
        problems += check_unique(hook, ci)
        problems += check_emit(workflow_text, hook, overrides)

    if problems:
        print("gate-parity: the hook and CI have drifted.", file=sys.stderr)
        for p in problems:
            print("  - %s" % p, file=sys.stderr)
        print("", file=sys.stderr)
        print("gate 14 FAILED: %s" % WORKFLOW_REL, file=sys.stderr)
        return 1

    if args.check_emit:
        print("OK: the generated CI step block matches the hook.")
        return 0

    ci = parse_ci(workflow_text)
    print(
        "OK: hook and CI agree on %d gate(s), labels 1/%d..%d/%d, %d ci-only "
        "override(s), generated block matches."
        % (len(hook), len(ci), len(ci), len(ci), len(overrides))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
