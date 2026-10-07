#!/usr/bin/env python3
"""S9 gate -- checker mutation: prove that every self-check can fail.

Why this exists
---------------
The mutation suite inside ``examples/S5-Qregister`` proves that the *artifact
under test* is watched: break the runner, a mutant dies. Nothing proved that
the *checks themselves* are load-bearing. Review round 3 (FG-TIDA
``use-cases#21``, 2026-10-07) found the crosswalk agreement gate comparing only
its first column -- a defect that had survived every selftest run, because no
mutation had ever been aimed at the gate.

A check nobody ever watched fail is a hope, not a control.

What it does
------------
It mutates the harness's own checks, one decision point at a time, and requires
each mutation to make ``selftest()`` fail. A mutation that *survives* marks a
check that cannot fail on the defect it claims to catch.

Two sentinels ground the tool itself:

  * ``SENTINEL-inert``  -- a purely textual change that MUST survive; if the
    tool reports it as killed, the tool is reporting everything as killed;
  * ``SENTINEL-fatal``  -- a change that MUST die; if the tool reports it as
    surviving, the tool cannot see a real failure at all.

Second-order layer
------------------
Each *negative control* is itself a check ("the gate must object to this
tampered input"). To prove a negative control is load-bearing, the tool removes
it and requires that at least one checker mutation *becomes a survivor* as a
result. A control whose removal changes nothing is decorative.

Usage
-----
    <python> tools/checker-mutation.py [--verbose]
    exit 0  iff every non-exempt mutation is killed and both sentinels behave.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S5_DIR = os.path.join(REPO, "examples", "S5-Qregister")
HARNESS = os.path.join(S5_DIR, "harness.py")

# --------------------------------------------------------------------------- #
# The mutation set.
#
# Each entry: id, a one-line claim about the decision point, `old` / `new`
# source text (must appear exactly once), and a role:
#   role="check"    a check that claims to catch something -> must die
#   role="control"  a negative control (a guard of a guard) -> must be
#                   load-bearing, proven by the second-order layer
#   role="sentinel" a grounding sample -> fixed expectation
# --------------------------------------------------------------------------- #
MUTATIONS = [
    # -- sentinels: these ground the tool itself ------------------------------
    dict(id="SENTINEL-inert", role="sentinel", must_survive=True,
         claim="a purely textual change is semantically inert",
         old="# Building the observation: the one-way boundary.",
         new="# Building the observation: the one-way boundary (inert sentinel)."),
    dict(id="SENTINEL-fatal", role="sentinel", must_survive=False,
         claim="a changed crosswalk row must break README agreement",
         old='("Q1 explicit basis", "case A (SF-006 omission)", "Test B prep"),',
         new='("Q1 explicit basis!", "case A (SF-006 omission)", "Test B prep"),'),

    # -- the crosswalk agreement gate (S1) ------------------------------------
    dict(id="CW-firstcolumn", role="check",
         claim="crosswalk compares every column, not just the first",
         old="for i, (got, want) in enumerate(zip(rows, expected)):",
         new="for i, (got, want) in enumerate(zip([r[:1] for r in rows], "
             "[r[:1] for r in expected])):"),
    dict(id="CW-class-column", role="check",
         claim="the mutant's *class* column is compared, not only its killers",
         old="            if name in MUTANT_CLASS \\",
         new="            if False and name in MUTANT_CLASS \\"),
    dict(id="CW-row-count", role="check",
         claim="a deleted crosswalk row is caught, not silently truncated",
         old="        if len(rows) != len(expected):",
         new="        if False and len(rows) != len(expected):"),

    # -- observation coherence ------------------------------------------------
    dict(id="COH-any", role="check",
         claim="a self-contradictory record is rejected at all",
         old="    exit_code, guard, action, target_changed = observed\n"
             "    problems = []",
         new="    exit_code, guard, action, target_changed = observed\n"
             "    return []\n"
             "    problems = []"),
    dict(id="COH-target-vs-action", role="check",
         claim="the target moves exactly when the repair was attempted",
         old="    if target_changed != (action == ACTION_APPLY):",
         new="    if False and target_changed != (action == ACTION_APPLY):"),

    # -- blinding and self-report ---------------------------------------------
    dict(id="BLIND", role="check",
         claim="the runner cannot see the branch identity",
         old="    problems = []\n"
             "    if src is None:\n"
             "        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
             '                            "implementation.py")',
         new="    return []\n"
             "    problems = []\n"
             "    if src is None:\n"
             "        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
             '                            "implementation.py")'),
    dict(id="SELFREPORT", role="check",
         claim="the runner has no vocabulary for the target state",
         old="    module = impl if module is None else module\n"
             "    offenders = []\n"
             "    for slot in module.Verdict.__slots__:",
         new="    return []\n"
             "    module = impl if module is None else module\n"
             "    offenders = []\n"
             "    for slot in module.Verdict.__slots__:"),

    # -- spec agreement --------------------------------------------------------
    dict(id="SPEC-field", role="check",
         claim="each branch field is compared against fixture_spec.json",
         old="            if spec_branches[branch][key] != fields[key]:",
         new="            if False and spec_branches[branch][key] != fields[key]:"),

    # -- the row-4 trace distinction ------------------------------------------
    dict(id="ROW4-both-reasons", role="check",
         claim="(T,T) carries both reasons and (T,F) does not",
         old='    if "BOTH REASONS PRESENT" not in tt_text.upper():',
         new='    if False and "BOTH REASONS PRESENT" not in tt_text.upper():'),

    # -- mutation-suite survival reporting ------------------------------------
    dict(id="SUITE-survivors", role="check",
         claim="a surviving mutant is reported as a failure",
         old="    return [m for m, kills in matrix.items() if not kills]",
         new="    return []"),

    # -- negative controls (guards of guards) ---------------------------------
    dict(id="NEG-readme", role="control",
         claim="the README negative control is load-bearing",
         old="    problems = []\n    base = _synthetic_readme_text()",
         new="    return []\n    problems = []\n    base = _synthetic_readme_text()"),
    dict(id="NEG-coherence", role="control",
         claim="the coherence negative control is load-bearing",
         old="    problems = []\n    contradictory = (",
         new="    return []\n    problems = []\n    contradictory = ("),
    dict(id="NEG-xwalk-rows", role="control",
         claim="the crosswalk row-count control is load-bearing",
         old="    base = _synthetic_readme_text()\n"
             "    if check_readme_agreement(text=base):",
         new="    return []\n"
             "    base = _synthetic_readme_text()\n"
             "    if check_readme_agreement(text=base):"),
    dict(id="NEG-spec", role="control",
         claim="the spec-agreement negative control is load-bearing",
         old="    divergent = json.loads(json.dumps(spec))",
         new="    return []\n    divergent = json.loads(json.dumps(spec))"),
    dict(id="NEG-blind", role="control",
         claim="the blinding negative control is load-bearing",
         old='    if not _assert_blind(src="import harness\\n"):',
         new='    return []\n    if not _assert_blind(src="import harness\\n"):'),
    dict(id="NEG-selfreport", role="control",
         claim="the self-report negative control is load-bearing",
         old='    class _Verdict:\n        __slots__ = ("guard_decision", "target_changed")',
         new='    return []\n    class _Verdict:\n        __slots__ = ("guard_decision", "target_changed")'),
    dict(id="NEG-row4", role="control",
         claim="the row-4 negative control is load-bearing",
         old='    problems = []\n    if not _check_row4_traces("freeze prohibition applies",',
         new='    return []\n    problems = []\n    if not _check_row4_traces("freeze prohibition applies",'),
    dict(id="NEG-survivors", role="control",
         claim="the survivor-detection negative control is load-bearing",
         old='    fake = {"FAKE-hole": set(), "FAKE-caught": {"continuity"}}',
         new='    return []\n    fake = {"FAKE-hole": set(), "FAKE-caught": {"continuity"}}'),
]

# Mutations whose survival is *expected* because their catch is a separate
# check that this gate reports on in its own right (kept explicit, with a
# reason, rather than silently tolerated).
EXEMPT_SURVIVAL = {
    "NEG-readme": "removal is caught by the second-order layer, not by selftest",
    "NEG-coherence": "removal is caught by the second-order layer, not by selftest",
}

# One scratch package, prepared once and rewritten per variant. Nothing is
# deleted: each run overwrites harness.py in place.
SCRATCH = tempfile.mkdtemp(prefix="ckmut-")
PKG = os.path.join(SCRATCH, "S5-Qregister")
shutil.copytree(S5_DIR, PKG, ignore=shutil.ignore_patterns("__pycache__"))


def run_variant(source, verbose=False):
    """Write *source* as harness.py in the scratch copy and run its selftest.

    Returns (passed: bool, tail: str).
    """
    with open(os.path.join(PKG, "harness.py"), "w", encoding="utf-8") as fh:
        fh.write(source)
    proc = subprocess.run([sys.executable, "harness.py"], cwd=PKG,
                          capture_output=True, text=True, timeout=120)
    passed = proc.returncode == 0
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    if verbose:
        print("      exit=%d | %s" % (proc.returncode, " / ".join(tail)))
    return passed, "\n".join(tail)


def apply_mutation(source, mut):
    count = source.count(mut["old"])
    if count != 1:
        raise SystemExit("FATAL: mutation %s anchor appears %d times (want 1)."
                         % (mut["id"], count))
    return source.replace(mut["old"], mut["new"], 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with open(HARNESS, encoding="utf-8") as fh:
        base = fh.read()

    base_passed, _ = run_variant(base, args.verbose)
    print("S9 checker-mutation gate")
    print("-" * 70)
    print("  baseline selftest (unmutated)          -> %s"
          % ("PASS" if base_passed else "FAIL"))
    if not base_passed:
        print("\nThe package does not pass before mutation; fix it first.")
        return 1

    failures = []
    for mut in MUTATIONS:
        mutated = apply_mutation(base, mut)
        passed, _tail = run_variant(mutated, args.verbose)
        if mut["role"] == "sentinel":
            want_survive = mut["must_survive"]
            if passed != want_survive:
                failures.append(
                    "sentinel %s: expected to %s but did not -- the tool cannot "
                    "discriminate, so its verdicts mean nothing."
                    % (mut["id"], "survive" if want_survive else "die"))
            else:
                print("  + %-22s %s (sentinel ok)"
                      % (mut["id"], "survived" if passed else "killed"))
            continue
        if mut["role"] == "control":
            continue  # judged by the second-order layer below
        if passed:
            if mut["id"] in EXEMPT_SURVIVAL:
                print("  ~ %-22s survived (exempt: %s)"
                      % (mut["id"], EXEMPT_SURVIVAL[mut["id"]]))
            else:
                failures.append(
                    "check %s: mutating it did NOT fail the selftest -- the "
                    "check \"%s\" is decorative for that defect."
                    % (mut["id"], mut["claim"]))
        else:
            print("  + %-22s killed" % mut["id"])

    # -- second order: a negative control must be load-bearing ----------------
    checker_ids = [m["id"] for m in MUTATIONS if m["role"] == "check"]
    unpaired = []
    for ctrl in [m for m in MUTATIONS if m["role"] == "control"]:
        with_ctrl = apply_mutation(base, ctrl)
        newly_surviving = []
        for cid in checker_ids:
            cmut = next(m for m in MUTATIONS if m["id"] == cid)
            if cmut["old"] not in with_ctrl:
                # The control's change rewrote this check's anchor, so there is
                # nothing to pair. Recorded explicitly rather than swallowed:
                # a silent skip here would be the very defect this gate hunts.
                unpaired.append("%s x %s" % (ctrl["id"], cid))
                continue
            pair = with_ctrl.replace(cmut["old"], cmut["new"], 1)
            passed, _ = run_variant(pair, False)
            if passed:
                newly_surviving.append(cid)
        if newly_surviving:
            print("  + %-22s load-bearing (removal lets %s survive)"
                  % (ctrl["id"], ",".join(newly_surviving)))
        else:
            failures.append(
                "control %s: removing it lets no checker mutation survive -- "
                "the control is decorative (it guards nothing)." % ctrl["id"])
    if unpaired:
        print("  note: %d control x check pair(s) could not be composed "
              "(overlapping anchors), reported not skipped: %s"
              % (len(unpaired), ", ".join(unpaired)))

    print("-" * 70)
    if failures:
        print("S9 FAILED: %d finding(s)" % len(failures))
        for f in failures:
            print("  FAIL %s" % f)
        return 1
    print("S9 PASSED: every check dies on a targeted mutation; every negative "
          "control is load-bearing; the tool is grounded by two sentinels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
