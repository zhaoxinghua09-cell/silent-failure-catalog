#!/usr/bin/env python3
"""T08-S5Q2 stateful simulation -- an always-green pre-flight, step by step.

A runnable companion to the modeled walkthrough promoted from the FG-TIDA
contribution (use-cases #21, Annex T08 / UC-21, requirement S5-Q2):
"Material preconditions are reassessed at use, not inherited from queue time."

The world is stateful: the workflow is enqueued while a freeze holds, the
freeze is lifted *while the item sits in the queue*, and the pre-flight gate
runs at use time. Two validators are compared on the identical trace:

  before  -- registry-driven pre-flight that evaluates the *queue-time
             snapshot* over the *declared* registry only. It reports PASS on
             the violated world. This is SF-006 (undeclared = unchecked,
             see ../../failures/SF-006-undeclared-not-checked.md) and the
             inherited-verdict shape of S5-Q2 in one trace.
  after   -- the same trace with the SF-006 reverse-coverage control applied:
             re-derive what the workflow actually depends on *at use time*,
             diff against what is declared, then check. It fails, naming the
             undeclared precondition.

Usage
-----
  python simulation.py                  # selftest (default): runs both traces
                                        # and asserts the discriminating property
  python simulation.py --trace before   # prints the silent-failure trace; exits 0
  python simulation.py --trace after    # prints the controlled trace;   exits 2

Deterministic: no randomness, no clock, no network. stdlib only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import sys

# --------------------------------------------------------------------------- #
# The declared registry (what the pre-flight check iterates) and the actual
# dependency set (what the workflow truly needs at use time). The gap between
# them is the SF-006 defect: anything undeclared is never checked, never missed.
# --------------------------------------------------------------------------- #
DECLARED_REGISTRY = ("grant_valid", "subject_in_scope", "diag_complete")
ACTUAL_DEPENDENCIES = DECLARED_REGISTRY + ("freeze_still_holds",)

# Workflow states (a minimal T08-style Step Functions lifecycle).
QUEUED, PREFLIGHT, EXECUTED, ABORTED = "QUEUED", "PREFLIGHT", "EXECUTED", "ABORTED"

EXIT_SILENT_PASS = 0   # before-mode: reproduces the silent failure, exits green
EXIT_CONTROLLED_FAIL = 2  # after-mode: the control fires, exits non-zero


def _world_at_queue_time() -> dict:
    """Material state when the remediation is enqueued: the freeze holds."""
    return {
        "grant_valid": True,
        "subject_in_scope": True,
        "diag_complete": True,
        "freeze_still_holds": True,
    }


def _simulate(mode: str):
    """Run the full stateful trace in one of the two modes.

    Returns (exit_code, lines). The trace is identical up to the pre-flight
    step; only the validator differs. Everything is printed as it happens so
    the state changes are visible, not implied.
    """
    lines = []

    def say(step: str, state: str, text: str) -> None:
        lines.append(f"t{len(lines)}  {state:<9} {text}" + (f"  [{step}]" if step else ""))

    # -- t0: enqueue. The gate's future verdict is captured here, at queue time.
    snapshot = dict(_world_at_queue_time())
    say("enqueue", QUEUED, "material enqueued; queue-time snapshot recorded")

    # -- t1: the world changes while nobody is looking. The freeze that
    #        authorized this remediation is lifted. The snapshot does not move.
    world = dict(snapshot)
    world["freeze_still_holds"] = False
    say("", QUEUED,
        "world event: freeze lifted (freeze_still_holds -> False); "
        "snapshot still says True")

    # -- t2: the pre-flight gate runs at use time.
    if mode == "before":
        # Evaluates the DECLARED registry over the QUEUE-TIME SNAPSHOT.
        # - undeclared preconditions are invisible by construction (SF-006);
        # - even declared ones are judged on data inherited from queue time,
        #   which is exactly what S5-Q2 forbids.
        failed = [p for p in DECLARED_REGISTRY if not snapshot.get(p)]
        say("preflight", PREFLIGHT,
            "registry-driven check: %d declared precondition(s) evaluated "
            "against the queue-time snapshot" % len(DECLARED_REGISTRY))
        if failed:
            say("abort", ABORTED, "declared precondition failed: %s" % sorted(failed))
            return 1, lines
        verdict = "PASS"
        say("", PREFLIGHT, "verdict: PASS  <-- "
            "the violated, undeclared precondition was never in the frame")
        # -- t3: execution proceeds on a stale authorization.
        say("execute", EXECUTED, "remediation executed; the system fails silently")
    else:
        # The SF-006 reverse-coverage control: re-derive the actual dependency
        # set AT USE TIME, diff against the declared registry, then check.
        undeclared = sorted(set(ACTUAL_DEPENDENCIES) - set(DECLARED_REGISTRY))
        stale = sorted(set(DECLARED_REGISTRY) - set(ACTUAL_DEPENDENCIES))
        say("preflight", PREFLIGHT,
            "reverse-coverage control: actual-at-use vs declared, "
            "%d vs %d item(s)" % (len(ACTUAL_DEPENDENCIES), len(DECLARED_REGISTRY)))
        if undeclared or stale:
            reasons = []
            if undeclared:
                reasons.append(
                    "%s exist but are undeclared (S5-Q2 breach: "
                    "preconditions not reassessed at use)" % undeclared)
            if stale:
                reasons.append("%s declared but inapplicable" % stale)
            say("abort", ABORTED, "verdict: FAIL  -- " + "; ".join(reasons))
            return EXIT_CONTROLLED_FAIL, lines
        # (unreachable with the shipped fixture; kept so the control's green
        # branch is explicit rather than implied)
        verdict = "PASS"
        say("", PREFLIGHT, "verdict: PASS")
        say("execute", EXECUTED, "remediation executed; preconditions held at use")
        return 0, lines

    return EXIT_SILENT_PASS, lines


def _selftest() -> int:
    """The demo validates itself: the property is the discriminator.

    A catalog about silent passes must not silently pass, so the selftest
    asserts both halves (SF-011 discipline, see
    ../../failures/SF-011-always-green-oracle.md):
      1. before-mode PASSES on the violated world  -> the blindness is real;
      2. after-mode  FAILS on the same world       -> the control can see it.
    A validator that did neither (or both) would make the two traces identical,
    and the assertion below would fire.
    """
    before_code, before_lines = _simulate("before")
    after_code, after_lines = _simulate("after")

    problems = []
    if "PASS" not in " ".join(before_lines):
        problems.append("before-mode did not reproduce the silent PASS")
    if before_code != EXIT_SILENT_PASS:
        problems.append("before-mode exit code is %d, expected %d (the silent "
                        "failure must exit green to be silent)"
                        % (before_code, EXIT_SILENT_PASS))
    if "freeze_still_holds" not in " ".join(after_lines):
        problems.append("after-mode did not name the undeclared precondition")
    if after_code != EXIT_CONTROLLED_FAIL:
        problems.append("after-mode exit code is %d, expected %d"
                        % (after_code, EXIT_CONTROLLED_FAIL))

    print("T08-S5Q2 selftest")
    print("-----------------")
    print("  trace before : %d line(s), exit %d -> %s"
          % (len(before_lines), before_code,
             "silent PASS (reproduced)" if not problems else "UNEXPECTED"))
    print("  trace after  : %d line(s), exit %d -> %s"
          % (len(after_lines), after_code,
             "controlled FAIL (reproduced)" if len(problems) < 2 else "UNEXPECTED"))
    if problems:
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED: the two traces no longer discriminate.")
        return 1
    print("\nSELFTEST PASSED: identical world, two verdicts -- the control can fail, "
          "the registry-driven check cannot.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulation",
        description="Stateful simulation of an always-green pre-flight "
                    "(UC-21 S5-Q2 / T08-AWS, SF-006 + SF-011).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--trace", choices=["before", "after"],
                      help="run one trace and exit with its verdict's code")
    mode.add_argument("--selftest", action="store_true",
                      help="run both traces and assert they discriminate (default)")
    args = parser.parse_args(argv)

    if args.trace:
        code, lines = _simulate(args.trace)
        print("\n".join(lines))
        return code
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
