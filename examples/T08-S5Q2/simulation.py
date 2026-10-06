#!/usr/bin/env python3
"""T08-S5Q2 stateful simulation v4 -- four contrasting cases, auditable spec,
and a mutation suite that answers "who tests the tester".

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
  v4  adversarial pass (the review continued against ourselves): the selftest
      asserted that the *shipped* validators discriminate, but nothing
      asserted that the selftest itself would catch a *broken* validator.
      Mutation testing closes that loop: four programmatic mutants of the
      after-implementation (skip the coverage diff / read the stale snapshot /
      skip the action-boundary re-check / blanket-deny despite a satisfied
      gate set) are executed against the cases, and the selftest fails unless
      every mutant is *killed* -- i.e., observable behavior deviates from the
      shipped table on at least one case. The selftest also now asserts the
      FAIL diagnostics *name the offending condition*, not merely any failure.
  v5  review round 2 (2026-10-06): the action-boundary re-verification runs
      UNCONDITIONALLY before every permitted actuation -- not only when the
      fixture declares a post-verdict event -- so the C trace shows the
      recheck holding on an unchanged world and case D is where it bites
      (dakleyer condition #3). The fourth mutant is ``M4-blanket-deny``:
      every gate satisfied yet the action still refused, the over-blocking
      shape the clean baseline exists to kill (dakleyer condition #4; the
      previous polarity-flip mutant also flipped the exit code without
      inverting ``repair_applied``, an internally inconsistent mutant -- it
      is gone, not patched).

Each case runs two implementations on the identical world trace:

  before  -- registry-driven pre-flight over the *queue-time snapshot*,
             verdict inherited to the action (SF-006 + SF-011 shape).
  after   -- (1) coverage diff against the spec-derived reference,
             (2) evaluation of declared conditions against state read *at use
             time*, (3) UNCONDITIONAL re-verification at the *action boundary*
             before every permitted actuation (closing the case-D window),
             (4) an explicit prevention trace.

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
                                          # the discriminating properties AND
                                          # that every mutant is killed
  python simulation.py --case A-omitted   # paired traces for one case
  python simulation.py --case B-temporal
  python simulation.py --case C-clean
  python simulation.py --case D-actwindow
  python simulation.py --mutants          # print the mutation kill matrix

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

# --------------------------------------------------------------------------- #
# Mutation suite: programmatic mutants of the after-implementation. Each
# mutant disables exactly one defense; the selftest requires that every
# mutant is *killed* (its observable behavior deviates from the shipped
# table below on at least one case). The expected table is hardcoded, not
# derived by running the shipped code -- deriving it from a run would make
# the assertion tautological.
# --------------------------------------------------------------------------- #
MUTANTS = {
    "M1-no-coverage-diff":
        "after-impl skips the SF-006 coverage diff (undeclared conditions unchecked)",
    "M2-stale-read":
        "after-impl reads the queue-time snapshot instead of use-time state",
    "M3-no-boundary-recheck":
        "after-impl trusts the verdict and skips the action-boundary re-check",
    "M4-blanket-deny":
        "after-impl blocks even though every gate is satisfied (a blanket "
        "stop; the over-blocking shape the clean baseline exists to catch)",
}

# Shipped after-implementation behavior: case -> (exit, repair_applied, stage).
# The stage pins WHICH defense fired; the mutation kill criterion compares the
# full triple, so a mutant caught by a different defense than the shipped one
# is still killed (M2 vs the unconditional boundary recheck, review round 2).
SHIPPED_AFTER = {
    "A-omitted": (EXIT_FAIL, False, "coverage"),
    "B-temporal": (EXIT_FAIL, False, "use-time"),
    "C-clean": (EXIT_PASS, True, "executed"),
    "D-actwindow": (EXIT_FAIL, False, "boundary"),
}


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
    # The shipped after-implementation table lives in the spec too (review
    # round 2, S4): a drift between fixture_spec.json and SHIPPED_AFTER stops
    # the run before any trace is printed.
    spec_after = spec.get("shipped_after", {})
    if sorted(spec_after) != sorted(SHIPPED_AFTER):
        raise SystemExit(
            "SPEC/CODE DIVERGENCE: fixture_spec.json shipped_after cases %s != "
            "simulation SHIPPED_AFTER %s." % (sorted(spec_after),
                                              sorted(SHIPPED_AFTER)))
    for case, expected in SHIPPED_AFTER.items():
        got = spec_after[case]
        if got.get("exit") != expected[0] \
                or got.get("repair_applied") != expected[1] \
                or got.get("stage") != expected[2]:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: case %s shipped_after %r does not "
                "match SHIPPED_AFTER %r." % (case, got, expected))


def _run_case(case: str, impl: str, mutant: str | None = None):
    """Run one case on one implementation, optionally under a mutant.

    Returns (exit_code, lines, repair_applied, stage). ``repair_applied``
    tracks the target state so the prevention claim is observable, not
    implied; ``stage`` names WHICH defense (or none) produced the outcome --
    gate / coverage gap / use-time read / action boundary / executed /
    blanket. Without the stage, a mutant disabled by a *different* defense
    catching the same breach (M2 masked by the unconditional boundary
    recheck, found in review round 2) would pass for the shipped behavior.
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
            return EXIT_FAIL, lines, repair_applied, "gate"
        say(PREFLIGHT, "verdict: PASS (all declared conditions held *at queue time*)")
    else:
        # Step 1: coverage diff against the spec-derived reference.
        # (M1 disables it: undeclared conditions go unchecked -- SF-006.)
        if mutant != "M1-no-coverage-diff":
            undeclared = sorted(set(REFERENCE) - set(declared))
            if undeclared:
                say(PREFLIGHT, "verdict: FAIL -- coverage gap: %s exist in the "
                    "reference but are undeclared (SF-006)" % undeclared)
                say(BLOCKED, "disposition: blocked at the gate -> target state "
                    "UNCHANGED (prevention demonstrated, Q6 trace)")
                return EXIT_FAIL, lines, repair_applied, "coverage"
        # Step 2: evaluate declared conditions against state read AT USE TIME.
        # (M2 reverts the source to the queue-time snapshot -- the defect the
        # requirement forbids.)
        read_source = snapshot if mutant == "M2-stale-read" else world
        say(PREFLIGHT,
            "after-impl: coverage complete (%d/%d); re-reading state at use time"
            % (len(declared), len(REFERENCE)))
        failed = [p for p in declared if not read_source.get(p)]
        if failed:
            say(PREFLIGHT, "verdict: FAIL -- declared condition(s) %s changed "
                "between queue and use (S5-Q2 breach: verdict inherited from "
                "queue time is forbidden)" % sorted(failed))
            say(BLOCKED, "disposition: blocked at the gate -> target state "
                "UNCHANGED (prevention demonstrated, Q6 trace)")
            return EXIT_FAIL, lines, repair_applied, "use-time"
        say(PREFLIGHT, "verdict: PASS (reassessed at use; conditions hold)")
        if mutant == "M4-blanket-deny":
            # The mutant: a scope bug that refuses the action although every
            # gate is satisfied. It models the over-blocking validator; the
            # clean baseline (case C) is the case that kills it.
            say(PREFLIGHT, "verdict: PASS (every declared condition holds -- "
                "all gates satisfied)")
            say(BLOCKED, "disposition: blocked anyway -- blanket deny despite "
                "a fully satisfied gate set (scope bug; target state "
                "UNCHANGED)")
            return EXIT_FAIL, lines, repair_applied, "blanket"

    # -- t2.5 (case D): the world changes AFTER the verdict, BEFORE the action.
    if post_event is not None:
        key, value = post_event
        world[key] = value
        say(PREFLIGHT, "world event (post-verdict): %s -> %s  "
            "(after the gate's verdict, before the action)" % (key, value))

    # -- t3: the attempted action. The after implementation re-verifies at the
    # action boundary -- UNCONDITIONALLY, before every permitted actuation
    # (2026-10-06 review, dakleyer condition #3: the recheck must not depend
    # on the fixture declaring a post-verdict event; most runs re-verify an
    # unchanged world, case D is the run where it bites). The before
    # implementation acts on the inherited verdict. (M3 disables the
    # re-verification.)
    say(PREFLIGHT, "attempted action: apply repair to target")
    if impl == "after" and mutant != "M3-no-boundary-recheck":
        failed_now = [p for p in declared if not world.get(p)]
        if failed_now:
            say(BLOCKED, "disposition: BLOCKED at the action boundary -- "
                "re-verification caught %s flipping after the verdict "
                "(check-then-act gap closed; target state UNCHANGED)"
                % sorted(failed_now))
            return EXIT_FAIL, lines, repair_applied, "boundary"
        say(PREFLIGHT, "boundary re-verification: conditions re-read at the "
            "action boundary -> hold (unconditional recheck)")
    repair_applied = True
    if case == "C-clean":
        say(EXECUTED, "disposition: executed -> target state CHANGED "
            "(legitimate repair, no breach)")
    else:
        say(EXECUTED, "disposition: executed -> target state CHANGED "
            "(repair applied during a breach; prevention never demonstrated)")
    return EXIT_PASS, lines, repair_applied, "executed"


def _paired(case: str):
    """Run both implementations on one case; return (before, after) triples."""
    return _run_case(case, "before"), _run_case(case, "after")


def _kill_matrix():
    """Run every mutant over every case; return {mutant: [killing cases]}.

    A mutant is *killed* by a case when the observable pair
    (exit code, repair_applied) deviates from the hardcoded shipped table.
    """
    matrix = {}
    for name in MUTANTS:
        killers = []
        for case in sorted(CASES):
            observed = _run_case(case, "after", mutant=name)
            if (observed[0], observed[2], observed[3]) != SHIPPED_AFTER[case]:
                killers.append(case)
        matrix[name] = killers
    return matrix


def _print_matrix(matrix) -> None:
    print("mutation matrix (who tests the tester):")
    for name, killers in matrix.items():
        if killers:
            print("  %-23s KILLED by %s" % (name, ", ".join(killers)))
        else:
            print("  %-23s SURVIVED -- a broken validator would pass silently" % name)


def _print_paired(case: str) -> int:
    (bc, bl, _s, _st), (ac, al, _a, _ast) = _paired(case)
    print("=== case %s ===" % case)
    print("-- before-impl (exit %d):" % bc)
    print("\n".join(bl))
    print("-- after-impl (exit %d):" % ac)
    print("\n".join(al))
    print("\n(exit semantics: 1 = the pair discriminates, i.e. the demo held; "
          "0 would mean both validators agreed -- the silent shape.)")
    return 0 if (bc == 0 and ac == 0) or (bc != 0 and ac != 0) else 1


def _selftest() -> int:
    """Assert the discriminating properties AND the mutation kill matrix.

    A catalog about silent passes must not silently pass (SF-011 discipline,
    see ../../failures/SF-011-always-green-oracle.md). The properties:
      A: before PASSes the omitted-condition world; after FAILs on coverage,
         naming the undeclared condition.
      B: before PASSes the value-drift world (stale snapshot) AND the repair
         is applied during an active freeze; after FAILs at use time, naming
         the flipped condition, AND the target state is unchanged.
      C: both PASS and the legitimate repair is applied (over-blocking
         detector); the after-impl trace shows the unconditional boundary
         re-verification running even with no post-verdict event.
      D: both PASS the pre-flight; the world then flips post-verdict; before
         executes during the fresh breach (verdict alone is not a control),
         after blocks at the action boundary, naming the flipped condition.
      M: every mutant of the after-implementation is killed by at least one
         case (who-tests-the-tester, mechanically).
    """
    problems = []

    (bc, bl, b_applied, _st), (ac, al, a_applied, a_stage) = _paired("A-omitted")
    a_after_text = " ".join(al)
    if bc != EXIT_PASS or "PASS" not in " ".join(bl):
        problems.append("A: before-impl must silently PASS the omitted-condition world")
    if ac != EXIT_FAIL or "coverage gap" not in a_after_text:
        problems.append("A: after-impl must FAIL naming the coverage gap")
    if "no_applicable_freeze" not in a_after_text:
        problems.append("A: after-impl diagnostics must name the omitted condition")
    if not b_applied:
        problems.append("A: before-impl must realize the breach (repair applied)")
    if a_stage != "coverage":
        problems.append("A: after-impl must block at the coverage stage, got %r"
                        % a_stage)

    (bc, bl, b_applied, _st), (ac, al, a_applied, a_stage) = _paired("B-temporal")
    b_after_text = " ".join(al)
    if bc != EXIT_PASS:
        problems.append("B: before-impl must PASS the value-drift world (stale snapshot)")
    if not b_applied:
        problems.append("B: before-impl must apply the repair during the active freeze")
    if ac != EXIT_FAIL or "changed between queue and use" not in b_after_text:
        problems.append("B: after-impl must FAIL on the use-time value change")
    if "no_applicable_freeze" not in b_after_text:
        problems.append("B: after-impl diagnostics must name the flipped condition")
    if a_applied:
        problems.append("B: after-impl must BLOCK the repair (target unchanged)")
    if a_stage != "use-time":
        problems.append("B: after-impl must block at the use-time read, got %r "
                        "(a boundary-stage block would mean the use-time read "
                        "is dead)" % a_stage)

    (bc, bl, b_applied, _st), (ac, al, a_applied, _a_stage) = _paired("C-clean")
    c_after_text = " ".join(al)
    if bc != EXIT_PASS or ac != EXIT_PASS:
        problems.append("C: both implementations must PASS the clean baseline")
    if not (b_applied and a_applied):
        problems.append("C: the legitimate repair must be applied by both")
    if "boundary re-verification" not in c_after_text:
        problems.append("C: the after-impl trace must show the unconditional "
                        "boundary re-verification running even with no "
                        "post-verdict event (recheck is not event-gated)")

    (bc, bl, b_applied, _st), (ac, al, a_applied, a_stage) = _paired("D-actwindow")
    d_before_text = " ".join(bl)
    d_after_text = " ".join(al)
    if bc != EXIT_PASS or "PASS" not in d_before_text:
        problems.append("D: before-impl must PASS the pre-flight (verdict was valid at use)")
    if "post-verdict" not in d_before_text or not b_applied:
        problems.append("D: before-impl must execute during the fresh breach "
                        "(check-then-act gap demonstrated)")
    if ac != EXIT_FAIL or "action boundary" not in d_after_text:
        problems.append("D: after-impl must block at the action boundary")
    if "no_applicable_freeze" not in d_after_text:
        problems.append("D: after-impl diagnostics must name the post-verdict flip")
    if a_applied:
        problems.append("D: after-impl must leave the target unchanged")
    if a_stage != "boundary":
        problems.append("D: after-impl must block at the action boundary, got "
                        "%r" % a_stage)

    matrix = _kill_matrix()
    survivors = [m for m, killers in matrix.items() if not killers]
    if survivors:
        problems.append("mutation: surviving mutant(s) %s -- the selftest "
                        "cannot see a broken validator" % survivors)

    print("T08-S5Q2 selftest v5 (four contrasting cases + mutation suite; "
          "unconditional boundary recheck; blanket-deny mutant)")
    print("-" * 62)
    ok = "ok" if not problems else "FAILED"
    print("  A-omitted  : before=PASS(silent)   after=FAIL(coverage gap)      -> %s" % ok)
    print("  B-temporal : before=PASS(stale)    after=FAIL(use-time read)     -> %s" % ok)
    print("  C-clean    : before=PASS           after=PASS (recheck held)     -> %s" % ok)
    print("  D-actwindow: before=PASS(breach!)  after=BLOCK(boundary re-check)-> %s" % ok)
    print()
    _print_matrix(matrix)
    if problems:
        print()
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED: the cases or the mutation matrix no longer hold.")
        return 1
    print("\nSELFTEST PASSED: set-difference catches omissions; the use-time "
          "read catches value drift; the boundary re-check catches "
          "post-verdict drift; prevention is shown as "
          "attempt->disposition->target-state; and every mutant of the "
          "validator is killed -- the tester itself is tested.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulation",
        description="Stateful simulation of an always-green pre-flight, v5: "
                    "four contrasting cases (UC-21 S5-Q2 / T08-AWS, SF-006 + "
                    "SF-011), spec-derived reference, UNCONDITIONAL "
                    "action-boundary re-verification, and a mutation suite "
                    "that kills four broken-validator mutants.",
    )
    parser.add_argument("--case", choices=sorted(CASES),
                        help="run both implementations on one case and print the paired traces")
    parser.add_argument("--mutants", action="store_true",
                        help="run the mutation suite and print the kill matrix")
    parser.add_argument("--selftest", action="store_true",
                        help="run all cases and mutants and assert they discriminate (default)")
    args = parser.parse_args(argv)

    check_spec_agreement()
    if args.mutants:
        matrix = _kill_matrix()
        _print_matrix(matrix)
        return 0 if all(matrix.values()) else 1
    if args.case:
        return _print_paired(args.case)
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
