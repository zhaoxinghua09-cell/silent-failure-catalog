#!/usr/bin/env python3
"""T08-S5Q2 stateful simulation v2 -- three contrasting cases, one reference.

A runnable companion to the FG-TIDA contribution (use-cases #21, Annex T08 /
UC-21, requirement S5-Q2): "Material preconditions are reassessed at use, not
inherited from queue time."

Semantics (aligned with the S5 scenario): an *active freeze prohibits* the
change; lifting it removes that restriction. The gate therefore consumes the
*permitting* condition ``no_applicable_freeze`` (naming per the 2026-09-30
joint review on use-cases #21): the repair is authorized while no freeze
applies, and a freeze may become applicable *before* the queued item reaches
its pre-flight gate. All registry conditions are permitting, so one uniform
checker suffices; the before/after difference is purely the data source
(queue-time snapshot vs use-time read).

v1 demonstrated one thing only: SF-006 detects an *omission* relative to a
stipulated reference. The joint review (2026-09-30, use-cases #21) correctly
distinguished that from use-time reassessment and prevention. v2 therefore
ships the three contrasting cases requested for the bounded review, plus an
explicit prevention trace:

  case A (omitted condition)  -- the freeze is never declared. Set-difference
                                 against the reference finds the coverage gap.
  case B (temporal, decisive) -- the freeze IS declared in both lists; its
                                 *value* changes between queue and use. A
                                 checker that re-reads the queue-time snapshot
                                 passes; a checker that reads state at use
                                 fails. Set-difference alone finds nothing
                                 here; only the use-time read does.
  case C (clean baseline)     -- declared, unchanged, valid. Execution remains
                                 permitted (legitimate-activity control).

Each case runs two implementations on the identical world trace:

  before  -- registry-driven pre-flight that evaluates the *queue-time
             snapshot* over the *declared* registry (SF-006 +
             inherited-verdict shape).
  after   -- the controlled implementation: (1) coverage diff against a
             stipulated-complete reference, then (2) evaluation of declared
             conditions against state read *at use time*, then (3) an
             explicit prevention trace: attempted action -> disposition ->
             resulting target state.

Qualifications kept explicit (per the joint review):
  * The reference's completeness is *stipulated* for the bounded fixture;
    its provenance is an assumption of the demo, not a result.
  * A use-time read implements reassessment here; establishing *freshness*
    of that read (Q3 territory) is out of scope and stated as an assumption.
  * A model result -- not an AWS product execution.

Usage
-----
  python simulation.py                  # selftest (default): runs all three
                                        # cases on both implementations and
                                        # asserts the discriminating properties
  python simulation.py --case A-omitted # paired verdicts for one case
  python simulation.py --case B-temporal
  python simulation.py --case C-clean

Deterministic: no randomness, no clock, no network. stdlib only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import sys

# --------------------------------------------------------------------------- #
# The declared registry as v1 shipped it, the stipulated-complete reference,
# and the three case fixtures. In every fixture the pre-flight runs at use
# time; only what the checker reads (snapshot vs live state) differs.
# --------------------------------------------------------------------------- #
DECLARED_REGISTRY_V1 = ("grant_valid", "subject_in_scope", "diag_complete")

# Stipulated-complete reference for the bounded fixture (assumption, not result).
# All conditions are permitting (must hold at use). "no_applicable_freeze" is
# True while no freeze applies; a freeze becoming applicable flips it to False.
REFERENCE = ("grant_valid", "subject_in_scope", "diag_complete",
             "no_applicable_freeze")

# Case -> (declared registry, initial world, world event or None).
# "world event" is a (key, new_value) applied to the live world after queueing.
CASES = {
    "A-omitted": (
        DECLARED_REGISTRY_V1,
        {"grant_valid": True, "subject_in_scope": True, "diag_complete": True,
         "no_applicable_freeze": True},
        ("no_applicable_freeze", False),
    ),
    "B-temporal": (
        REFERENCE,
        {"grant_valid": True, "subject_in_scope": True, "diag_complete": True,
         "no_applicable_freeze": True},
        ("no_applicable_freeze", False),
    ),
    "C-clean": (
        REFERENCE,
        {"grant_valid": True, "subject_in_scope": True, "diag_complete": True,
         "no_applicable_freeze": True},
        None,
    ),
}

QUEUED, PREFLIGHT, EXECUTED, BLOCKED = "QUEUED", "PREFLIGHT", "EXECUTED", "BLOCKED"

EXIT_PASS = 0
EXIT_FAIL = 2


def _run_case(case: str, impl: str):
    """Run one case on one implementation.

    Returns (exit_code, lines). `repair_applied` tracks the target state so
    the prevention claim is observable, not implied.
    """
    declared, initial, event = CASES[case]
    lines = []

    def say(state: str, text: str) -> None:
        lines.append("t%d  %-9s %s" % (len(lines), state, text))

    # -- t0: enqueue. The checker's data source is fixed here: snapshot.
    snapshot = dict(initial)
    say(QUEUED, "material enqueued; queue-time snapshot: %s"
        % {k: snapshot[k] for k in sorted(snapshot)})

    # -- t1: the world may change while the item sits in the queue.
    world = dict(initial)
    if event is not None:
        key, value = event
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
        # Step 1: coverage diff against the stipulated-complete reference.
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

    # -- t3: the attempted action and the resulting target state (Q6 trace).
    say(PREFLIGHT, "attempted action: apply repair to target")
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
    """Assert the discriminating properties across all three cases.

    A catalog about silent passes must not silently pass (SF-011 discipline,
    see ../../failures/SF-011-always-green-oracle.md). The properties:
      A: before PASSes the omitted-condition world; after FAILs on coverage.
      B: before PASSes the value-drift world (stale snapshot) AND the repair
         is applied during an active freeze; after FAILs at use time AND the
         target state is unchanged (prevention).
      C: both PASS and the legitimate repair is applied.
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

    print("T08-S5Q2 selftest v2 (three contrasting cases)")
    print("-" * 46)
    ok = "ok" if not problems else "FAILED"
    print("  A-omitted : before=PASS(silent)  after=FAIL(coverage gap)   -> %s" % ok)
    print("  B-temporal: before=PASS(stale)   after=FAIL(use-time read)  -> %s" % ok)
    print("  C-clean   : before=PASS          after=PASS (both execute)  -> %s" % ok)
    if problems:
        print()
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED: the cases no longer discriminate.")
        return 1
    print("\nSELFTEST PASSED: set-difference catches omissions; the use-time "
          "read catches value drift; prevention is shown as "
          "attempt->disposition->target-state, not implied.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulation",
        description="Stateful simulation of an always-green pre-flight, v2: "
                    "three contrasting cases (UC-21 S5-Q2 / T08-AWS, SF-006 + SF-011).",
    )
    parser.add_argument("--case", choices=sorted(CASES),
                        help="run both implementations on one case and print the paired traces")
    parser.add_argument("--selftest", action="store_true",
                        help="run all cases and assert they discriminate (default)")
    args = parser.parse_args(argv)

    if args.case:
        return _print_paired(args.case)
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
