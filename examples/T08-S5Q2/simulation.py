#!/usr/bin/env python3
"""T08-S5Q2 stateful simulation v3 -- four contrasting cases, auditable spec.

A runnable companion to the FG-TIDA contribution (use-cases #21, Annex T08 /
UC-21, requirement S5-Q2): "Material preconditions are reassessed at use, not
inherited from queue time."

Semantics (aligned with the S5 scenario): an *active freeze prohibits* the
change; lifting it removes that restriction. The gate therefore consumes the
*permitting* condition ``no_applicable_freeze`` (naming per the 2026-09-30
joint review on use-cases #21): the repair is authorized while no freeze
applies, and a freeze may become applicable *before* the queued item reaches
its pre-flight gate -- or *after* the gate's verdict and before the action
itself (case D). All registry conditions are permitting, so one uniform
checker suffices; the before/after difference is purely the data source and
the re-verification policy.

Case history
------------
  v1  one case: SF-006 detects an *omission* relative to a stipulated
      reference.
  v2  the joint review's three contrasting cases + an explicit prevention
      trace (attempted action -> disposition -> resulting target state):
        A (omitted condition)  -- coverage gap via set difference.
        B (temporal, decisive) -- declared condition whose *value* changes
                                  between queue and use; only a use-time read
                                  catches it.
        C (clean baseline)     -- legitimate activity preserved (over-blocking
                                  detector).
  v3  extension past the review (pre-mortem, see extension research notes):
        D (check-then-act window) -- the world changes *after* the use-time
                                     verdict and *before* the action. A verdict
                                     alone is not a control: the after
                                     implementation re-verifies at the action
                                     boundary (atomic check-then-act); the
                                     before implementation executes during the
                                     fresh breach.
      plus: the condition set is no longer stipulated in code. It is derived
      from ``fixture_spec.json``, and the simulation fails loudly at startup if
      code and spec diverge -- reference completeness becomes an *auditable*
      artifact instead of an assumption carried silently.

Each case runs two implementations on the identical world trace:

  before  -- registry-driven pre-flight over the *queue-time snapshot*,
             verdict inherited to the action (SF-006 + SF-011 shape).
  after   -- (1) coverage diff against the spec-derived reference,
             (2) evaluation of declared conditions against state read *at use
             time*, (3) re-verification at the *action boundary* (closing the
             case-D window), (4) an explicit prevention trace.

Qualifications kept explicit (per the joint review):
  * Reference completeness: stipulated for the bounded fixture, but now
    *auditable* (spec file + startup divergence check); how references are
    obtained at catalog scale remains the open architectural question.
  * A use-time read implements reassessment; *freshness* of that read (Q3
    territory: clock skew, logical ordering) is out of scope and stated as an
    assumption in fixture_spec.json.
  * A model result -- not an AWS product execution.

Usage
-----
  python simulation.py                    # selftest (default): all four cases
                                          # on both implementations, asserts
                                          # the discriminating properties
  python simulation.py --case A-omitted   # paired traces for one case
  python simulation.py --case B-temporal
  python simulation.py --case C-clean
  python simulation.py --case D-actwindow

Deterministic: no randomness, no clock, no network. stdlib only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# --------------------------------------------------------------------------- #
# Registries, spec-derived reference, and the four case fixtures.
# --------------------------------------------------------------------------- #
DECLARED_REGISTRY_V1 = ("grant_valid", "subject_in_scope", "diag_complete")

# Derived from fixture_spec.json and asserted against it at startup (below).
REFERENCE = ("grant_valid", "subject_in_scope", "diag_complete",
             "no_applicable_freeze")

# Case -> (declared registry, initial world, pre-gate event, post-verdict event).
# An event is a (key, new_value) applied to the live world; pre-gate events fire
# after queueing (t1), post-verdict events fire after the pre-flight verdict and
# before the action (t2.5, case D only).
_ALL_TRUE = {"grant_valid": True, "subject_in_scope": True,
             "diag_complete": True, "no_applicable_freeze": True}

CASES = {
    "A-omitted": (DECLARED_REGISTRY_V1, dict(_ALL_TRUE),
                  ("no_applicable_freeze", False), None),
    "B-temporal": (REFERENCE, dict(_ALL_TRUE),
                   ("no_applicable_freeze", False), None),
    "C-clean": (REFERENCE, dict(_ALL_TRUE), None, None),
    "D-actwindow": (REFERENCE, dict(_ALL_TRUE),
                    None, ("no_applicable_freeze", False)),
}

QUEUED, PREFLIGHT, EXECUTED, BLOCKED = "QUEUED", "PREFLIGHT", "EXECUTED", "BLOCKED"

EXIT_PASS = 0
EXIT_FAIL = 2


def check_spec_agreement():
    """Fail loudly if the in-code reference and fixture_spec.json diverge.

    This converts the 'stipulated reference' from a silent assumption into an
    auditable artifact: any future edit that touches one side without the
    other stops here, before any trace is printed (SF-011 discipline: the
    spec-vs-code agreement itself must not silently pass).
    """
    spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "fixture_spec.json")
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec_conds = set(spec.get("conditions", {}))
    code_conds = set(REFERENCE)
    if spec_conds != code_conds:
        raise SystemExit(
            "SPEC/CODE DIVERGENCE: fixture_spec.json conditions %s != "
            "simulation REFERENCE %s -- fix the artifact or the code before "
            "any run; a silent drift here would be exactly the failure mode "
            "this catalog documents." % (sorted(spec_conds), sorted(code_conds)))
    for case, (_d, initial, _p, _q) in CASES.items():
        if set(initial) != code_conds:
            raise SystemExit(
                "FIXTURE DIVERGENCE: case %s initial world keys %s do not "
                "match the reference %s." % (case, sorted(initial),
                                             sorted(code_conds)))


def _run_case(case: str, impl: str):
    """Run one case on one implementation.

    Returns (exit_code, lines, repair_applied). ``repair_applied`` tracks the
    target state so the prevention claim is observable, not implied.
    """
    declared, initial, pre_event, post_event = CASES[case]
    lines = []

    def say(state: str, text: str) -> None:
        lines.append("t%d  %-9s %s" % (len(lines), state, text))

    # -- t0: enqueue. The checker's data source is fixed here: snapshot.
    snapshot = dict(initial)
    say(QUEUED, "material enqueued; queue-time snapshot: %s"
        % {k: snapshot[k] for k in sorted(snapshot)})

    # -- t1: the world may change while the item sits in the queue.
    world = dict(initial)
    if pre_event is not None:
        key, value = pre_event
        world[key] = value
        say(QUEUED, "world event: %s -> %s  (snapshot still says %s)"
            % (key, value, snapshot[key]))

    # -- t2: pre-flight at use time.
    repair_applied = False
    if impl == "before":
        say(PREFLIGHT,
            "before-impl: %d declared condition(s) evaluated over the "
            "QUEUE-TIME snapshot" % len(declared))
        failed = [p for p in declared if not snapshot.get(p)]
        if failed:
            say(PREFLIGHT, "verdict: FAIL -- declared condition(s) %s failed "
                "on snapshot" % sorted(failed))
            say(BLOCKED, "disposition: blocked at the gate -> target state "
                "UNCHANGED")
            return EXIT_FAIL, lines, repair_applied
        say(PREFLIGHT, "verdict: PASS (all declared conditions held *at queue time*)")
    else:
        # Step 1: coverage diff against the spec-derived reference.
        undeclared = sorted(set(REFERENCE) - set(declared))
        if undeclared:
            say(PREFLIGHT, "verdict: FAIL -- coverage gap: %s exist in the "
                "reference but are undeclared (SF-006)" % undeclared)
            say(BLOCKED, "disposition: blocked at the gate -> target state "
                "UNCHANGED (prevention demonstrated, Q6 trace)")
            return EXIT_FAIL, lines, repair_applied
        # Step 2: evaluate declared conditions against state read AT USE TIME.
        say(PREFLIGHT,
            "after-impl: coverage complete (%d/%d); re-reading state at use time"
            % (len(declared), len(REFERENCE)))
        failed = [p for p in declared if not world.get(p)]
        if failed:
            say(PREFLIGHT, "verdict: FAIL -- declared condition(s) %s changed "
                "between queue and use (S5-Q2 breach: verdict inherited from "
                "queue time is forbidden)" % sorted(failed))
            say(BLOCKED, "disposition: blocked at the gate -> target state "
                "UNCHANGED (prevention demonstrated, Q6 trace)")
            return EXIT_FAIL, lines, repair_applied
        say(PREFLIGHT, "verdict: PASS (reassessed at use; conditions hold)")

    # -- t2.5 (case D): the world changes AFTER the verdict, BEFORE the action.
    if post_event is not None:
        key, value = post_event
        world[key] = value
        say(PREFLIGHT, "world event (post-verdict): %s -> %s  "
            "(after the gate's verdict, before the action)" % (key, value))

    # -- t3: the attempted action. The after implementation re-verifies at the
    # action boundary (atomic check-then-act); the before implementation acts
    # on the inherited verdict.
    say(PREFLIGHT, "attempted action: apply repair to target")
    if impl == "after" and post_event is not None:
        failed_now = [p for p in declared if not world.get(p)]
        if failed_now:
            say(BLOCKED, "disposition: BLOCKED at the action boundary -- "
                "re-verification caught %s flipping after the verdict "
                "(check-then-act gap closed; target state UNCHANGED)"
                % sorted(failed_now))
            return EXIT_FAIL, lines, repair_applied
    repair_applied = True
    if case == "C-clean":
        say(EXECUTED, "disposition: executed -> target state CHANGED "
            "(legitimate repair, no breach)")
    else:
        say(EXECUTED, "disposition: executed -> target state CHANGED "
            "(repair applied during a breach; prevention never demonstrated)")
    return EXIT_PASS, lines, repair_applied


def _paired(case: str):
    """Run both implementations on one case; return (before, after) triples."""
    return _run_case(case, "before"), _run_case(case, "after")


def _print_paired(case: str) -> int:
    (bc, bl, _), (ac, al, _) = _paired(case)
    print("=== case %s ===" % case)
    print("-- before-impl (exit %d):" % bc)
    print("\n".join(bl))
    print("-- after-impl (exit %d):" % ac)
    print("\n".join(al))
    return 0 if (bc == 0 and ac == 0) or (bc != 0 and ac != 0) else 1


def _selftest() -> int:
    """Assert the discriminating properties across all four cases.

    A catalog about silent passes must not silently pass (SF-011 discipline,
    see ../../failures/SF-011-always-green-oracle.md). The properties:
      A: before PASSes the omitted-condition world; after FAILs on coverage.
      B: before PASSes the value-drift world (stale snapshot) AND the repair
         is applied during an active freeze; after FAILs at use time AND the
         target state is unchanged (prevention).
      C: both PASS and the legitimate repair is applied (over-blocking
         detector).
      D: both PASS the pre-flight; the world then flips post-verdict; before
         executes during the fresh breach (verdict alone is not a control),
         after blocks at the action boundary (target unchanged).
    """
    problems = []

    (bc, bl, b_applied), (ac, al, a_applied) = _paired("A-omitted")
    if bc != EXIT_PASS or "PASS" not in " ".join(bl):
        problems.append("A: before-impl must silently PASS the omitted-condition world")
    if ac != EXIT_FAIL or "coverage gap" not in " ".join(al):
        problems.append("A: after-impl must FAIL naming the coverage gap")
    if not b_applied:
        problems.append("A: before-impl must realize the breach (repair applied)")

    (bc, bl, b_applied), (ac, al, a_applied) = _paired("B-temporal")
    if bc != EXIT_PASS:
        problems.append("B: before-impl must PASS the value-drift world (stale snapshot)")
    if not b_applied:
        problems.append("B: before-impl must apply the repair during the active freeze")
    if ac != EXIT_FAIL or "changed between queue and use" not in " ".join(al):
        problems.append("B: after-impl must FAIL on the use-time value change")
    if a_applied:
        problems.append("B: after-impl must BLOCK the repair (target unchanged)")

    (bc, bl, b_applied), (ac, al, a_applied) = _paired("C-clean")
    if bc != EXIT_PASS or ac != EXIT_PASS:
        problems.append("C: both implementations must PASS the clean baseline")
    if not (b_applied and a_applied):
        problems.append("C: the legitimate repair must be applied by both")

    (bc, bl, b_applied), (ac, al, a_applied) = _paired("D-actwindow")
    d_before_text = " ".join(bl)
    d_after_text = " ".join(al)
    if bc != EXIT_PASS or "PASS" not in d_before_text:
        problems.append("D: before-impl must PASS the pre-flight (verdict was valid at use)")
    if "post-verdict" not in d_before_text or not b_applied:
        problems.append("D: before-impl must execute during the fresh breach "
                        "(check-then-act gap demonstrated)")
    if ac != EXIT_FAIL or "action boundary" not in d_after_text:
        problems.append("D: after-impl must block at the action boundary")
    if a_applied:
        problems.append("D: after-impl must leave the target unchanged")

    print("T08-S5Q2 selftest v3 (four contrasting cases)")
    print("-" * 46)
    ok = "ok" if not problems else "FAILED"
    print("  A-omitted  : before=PASS(silent)   after=FAIL(coverage gap)      -> %s" % ok)
    print("  B-temporal : before=PASS(stale)    after=FAIL(use-time read)     -> %s" % ok)
    print("  C-clean    : before=PASS           after=PASS (both execute)     -> %s" % ok)
    print("  D-actwindow: before=PASS(breach!)  after=BLOCK(boundary re-check)-> %s" % ok)
    if problems:
        print()
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED: the cases no longer discriminate.")
        return 1
    print("\nSELFTEST PASSED: set-difference catches omissions; the use-time "
          "read catches value drift; the boundary re-check catches "
          "post-verdict drift; prevention is shown as "
          "attempt->disposition->target-state, not implied.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulation",
        description="Stateful simulation of an always-green pre-flight, v3: "
                    "four contrasting cases (UC-21 S5-Q2 / T08-AWS, SF-006 + "
                    "SF-011), spec-derived reference, action-boundary "
                    "re-verification.",
    )
    parser.add_argument("--case", choices=sorted(CASES),
                        help="run both implementations on one case and print the paired traces")
    parser.add_argument("--selftest", action="store_true",
                        help="run all cases and assert they discriminate (default)")
    args = parser.parse_args(argv)

    check_spec_agreement()
    if args.case:
        return _print_paired(args.case)
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
