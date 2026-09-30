#!/usr/bin/env python3
"""S5 gate-register crosswalk v1 -- making the Q0-Q6 register executable.

A runnable companion to the FG-TIDA contribution (use-cases #21, Annex S5
sections 7-10 and Annex T08): the scenario-local gate register defines seven
acceptance conditions (Q0-Q6) and two diagnostic trace shapes
(capability-absent, ineffective-control). This script makes those gates
EXECUTABLE against the S5 fixture branches, and cross-walks them to the
four-case negative-control matrix of examples/T08-S5Q2.

What it demonstrates, gate by gate:

  I0 (ordinary route, capability-absent trace):
      Q1 CAPABILITY_ABSENT (no queryable decision basis), Q2 not performed,
      Q4 supersession outside the model -> the stale queued patch executes
      during the breach. Matches Annex S5 section 10.1.
  I1 (defended route, ineffective-control trace):
      Q2 runs but Q3 reads a stale cache and Q4 omits the superseding patch
      generation -> CONTROL_EXECUTED_FAILED, stale state accepted as current.
      Matches Annex S5 section 10.2.
  I2 (complete route):
      every gate carries evidence, including Q6 recheck-to-act binding at the
      action boundary; bounded ambiguity produces escalation, not silent
      permission; and the positive-continuity branch still EXECUTEs within
      the latency budget (a deny-all implementation fails it).

Fixture branches (per Annex S5 section 7.1):
  continuity   -- nothing material changes; correct outcome: EXECUTE.
  supersession -- Patch B + freeze land between T1 and T2; correct outcome:
                  REASSESS -> blocked (Q2/Q4 territory).
  act-window   -- the freeze lands AFTER the use-time verdict, BEFORE the
                  action; correct outcome: blocked at Q6 (the residual TOCTOU
                  window).
  ambiguity    -- the authoritative source is unavailable inside the horizon;
                  correct outcome: bounded non-execution / escalation (Q5).

Crosswalk (see README.md for the full table):
  S5 Q1  <-> case A (omitted condition / SF-006)
  S5 Q2  <-> case B (temporal value drift)
  S5 Q4  <-> case B variant (superseding state transition)
  S5 Q6  <-> case D (check-then-act window)
  S5 positive continuity control <-> case C (clean baseline / deny-all catch)
  S5 ambiguous branch            <-> an explicit extension: UNKNOWN must not
                                     be permission (bounded HOLD), which the
                                     four-case matrix leaves as roadmap.

Mutation suite (who tests the tester): four mutants of the I2 gate layer --
  G1-no-supersession  (Q4 dropped)      killed by: supersession
  G2-cache-read       (Q3 stale cache)  killed by: supersession, ambiguity
  G3-no-binding       (Q6 dropped)      killed by: act-window
  G4-blanket-deny     (Q5 scope bug)    killed by: continuity
Expected outcomes are hardcoded below, derived from the published gate
register, not from running the mutated code.

Deterministic: no randomness, no clock, no network. stdlib only, Python 3.9+.
A model result -- not an AWS product execution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# --------------------------------------------------------------------------- #
# Fixture branches (frozen per Annex S5 section 7). Keys: superseded_by_patch_b
# (Q4), freeze_applied (the material precondition), source_available (Q3
# freshness qualifier), post_verdict_freeze (the case-D / Q6 event).
# --------------------------------------------------------------------------- #
BRANCHES = {
    "continuity":   {"superseded_by_patch_b": False, "freeze_applied": False,
                     "source_available": True, "post_verdict_freeze": False},
    "supersession": {"superseded_by_patch_b": True, "freeze_applied": True,
                     "source_available": True, "post_verdict_freeze": False},
    "act-window":   {"superseded_by_patch_b": False, "freeze_applied": False,
                     "source_available": True, "post_verdict_freeze": True},
    "ambiguity":    {"superseded_by_patch_b": False, "freeze_applied": False,
                     "source_available": False, "post_verdict_freeze": False},
}

# Hardcoded expected outcomes for the complete route (I2), derived from the
# published gate register (S5 sections 8-9), NOT from running this code.
# branch -> (exit, repair_applied)
SHIPPED_I2 = {
    "continuity":   (0, True),   # EXECUTE within the latency budget
    "supersession": (2, False),  # REASSESS -> blocked
    "act-window":   (2, False),  # blocked at the action boundary (Q6)
    "ambiguity":    (2, False),  # bounded non-execution / escalation
}

# Diagnostic labels, per Annex CONVENTIONS.
CAPABILITY_ABSENT = "CAPABILITY_ABSENT"
CONTROL_EXECUTED_FAILED = "CONTROL_EXECUTED_FAILED"
CONTROL_PRESENT_NOT_INVOKED = "CONTROL_PRESENT_NOT_INVOKED"
CONTROL_EXECUTED_PASS = "CONTROL_EXECUTED_PASS"

EXIT_PASS, EXIT_FAIL = 0, 2


# --------------------------------------------------------------------------- #
# The gate evaluator. One function per implementation profile; each returns
# (exit_code, repair_applied, trace_lines) where every line carries the S5
# gate label and the diagnostic evidence state.
# --------------------------------------------------------------------------- #

def _trace_gates_i0(branch: str, world: dict):
    """Ordinary route: the scheduler has no semantic basis object at all."""
    lines = [("Q0", CONTROL_EXECUTED_PASS, "token/job approval valid (technical grant only)"),
             ("Q1", CAPABILITY_ABSENT, "no explicit semantic precondition object beyond job metadata"),
             ("Q2", CAPABILITY_ABSENT, "not performed; T1 decision reused at T2"),
             ("Q3", "absent", "never assessed (no semantic recheck occurs)"),
             ("Q4", CAPABILITY_ABSENT, "Patch B / freeze lineage outside the model")]
    executed = True  # nothing in the model can stop it
    note = ("stale queued patch EXECUTED during the breach"
            if branch != "continuity" else
            "patch executed; outcome correct here, for the wrong reason "
            "(no capability, no evidence)")
    return (EXIT_PASS if executed else EXIT_FAIL), executed, lines, note


def _trace_gates_i1(branch: str, world: dict, mutant: str | None = None):
    """Defended route: recheck runs, but its INHERENT defects are a 5-minute
    cache view (Q3) and a qualified basis that omits the superseding patch
    generation (Q4 partial) -- the shape Annex S5 section 10.2 documents."""
    lines = [("Q0", CONTROL_EXECUTED_PASS, "current grant qualified"),
             ("Q1", CONTROL_EXECUTED_PASS, "semantic preconditions recorded"),
             ("Q2", CONTROL_EXECUTED_PASS, "live recheck function ran")]
    if branch == "ambiguity":
        # Cache fallback: with the live source unavailable, the stale cache is
        # promoted to truth instead of entering bounded HOLD.
        lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                      "live source unavailable; 5-minute cache promoted to "
                      "current fact (stale state accepted as current)"))
        lines.append(("Q4", CONTROL_EXECUTED_FAILED,
                      "superseding-patch lineage not assessed (basis read "
                      "from the stale cache)"))
        lines.append(("Q5", "bypassed",
                      "no bounded-ambiguity path: silent permission on UNKNOWN"))
        return EXIT_PASS, True, lines, "patch EXECUTED on stale evidence"
    # The cache view: a 5-minute-old snapshot that predates every event.
    seen = {"superseded_by_patch_b": False, "freeze_applied": False,
            "source_available": True, "post_verdict_freeze": False}
    if seen.get("superseded_by_patch_b"):  # unreachable on the cache view; kept
        lines.append(("Q4", CONTROL_EXECUTED_PASS,
                      "superseding patch generation recognized"))
        return EXIT_FAIL, False, lines, "REASSESS -> affected patch blocked"
    lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                  "recheck reads 5-minute cache; current source version "
                  "invisible (stale state accepted as current)"))
    lines.append(("Q4", CONTROL_EXECUTED_FAILED,
                  "Patch B generation / freeze scope omitted from the "
                  "qualified basis"))
    lines.append(("Q5", "bypassed",
                  "action not held because no failure was detected"))
    if branch == "act-window":
        lines.append(("Q6", "absent",
                      "no check-to-act binding; fresh post-verdict breach "
                      "undetected"))
    note = ("patch EXECUTED during the breach" if branch != "continuity" else
            "patch executed; outcome correct here, for the wrong reason "
            "(stale evidence, partial basis)")
    return EXIT_PASS, True, lines, note


def _trace_gates_i2(branch: str, world: dict, mutant: str | None = None):
    """Complete route: every gate evidenced; binding held to the boundary.

    Note the register's division of labor: Q3 qualifies the CHECK (a stale
    cache must not be promoted to live); Q6 binds the VALIDATED STATE to the
    actuation. A Q3 defect therefore flows through unless Q3 itself catches
    it -- which is exactly why the register lists them as separate gates.
    """
    lines = [("Q0", CONTROL_EXECUTED_PASS, "grant current, subject/scope bound"),
             ("Q1", CONTROL_EXECUTED_PASS, "basis reconstructable and queryable")]
    if branch == "ambiguity":
        if mutant == "G2-cache-read":
            lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                          "mutant: stale cache promoted to current fact"))
            lines.append(("Q5", "bypassed",
                          "silent permission on UNKNOWN"))
            return EXIT_PASS, True, lines, "patch EXECUTED on stale evidence"
        lines.append(("Q3", "SOURCE_ABSENT",
                      "authoritative source unavailable inside the horizon"))
        lines.append(("Q5", CONTROL_EXECUTED_PASS,
                      "bounded non-execution: escalation raised, owner and "
                      "deadline assigned; UNKNOWN is not permission"))
        return EXIT_FAIL, False, lines, "HOLD/ESCALATE (bounded)"
    # The evidence view Q2/Q3 read: live world, or the stale cache under G2.
    cached = {"superseded_by_patch_b": False, "freeze_applied": False,
              "source_available": True, "post_verdict_freeze": False}
    seen = cached if mutant == "G2-cache-read" else world
    if mutant == "G2-cache-read":
        lines.append(("Q2", CONTROL_EXECUTED_PASS, "recheck ran"))
        lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                      "mutant: reads the 5-minute cache (stale evidence "
                      "flows through unchecked)"))
    else:
        lines.append(("Q2", CONTROL_EXECUTED_PASS,
                      "material preconditions re-evaluated at use time (T2)"))
        lines.append(("Q3", CONTROL_EXECUTED_PASS,
                      "source identity + observed_at inside the declared "
                      "freshness bound"))
    if seen.get("superseded_by_patch_b"):
        if mutant == "G1-no-supersession":
            lines.append(("Q4", CONTROL_EXECUTED_FAILED,
                          "mutant: supersession check dropped"))
            lines.append(("Q5", "bypassed", "stale basis treated as current"))
            return EXIT_PASS, True, lines, "patch EXECUTED during the breach"
        lines.append(("Q4", CONTROL_EXECUTED_PASS,
                      "Patch B generation + freeze scope recognized as a "
                      "state transition"))
        lines.append(("Q5", CONTROL_EXECUTED_PASS,
                      "affected patch requalified; unchanged units unaffected"))
        return EXIT_FAIL, False, lines, "REASSESS -> affected patch blocked"
    # No supersession: the gate still leaves evidence (a vacuous pass is a
    # recorded pass, not a missing line -- seven gates, seven traces).
    lines.append(("Q4", CONTROL_EXECUTED_PASS,
                  "no superseding state transition found"))
    if mutant == "G4-blanket-deny":
        return EXIT_FAIL, False, lines + [
            ("Q5", CONTROL_EXECUTED_FAILED,
             "mutant: scope bug -- everything stopped, legitimate "
             "continuity denied")], "legitimate repair denied (positive control failed)"
    lines.append(("Q5", CONTROL_EXECUTED_PASS, "scoped response, bounded horizon"))
    # Q6: recheck-to-act binding at the action boundary, against the LIVE
    # actuation state (not the evidence view -- that is the gate's purpose).
    if branch == "act-window":
        if mutant == "G3-no-binding":
            lines.append(("Q6", CONTROL_PRESENT_NOT_INVOKED,
                          "mutant: binding check dropped"))
            return EXIT_PASS, True, lines, "patch EXECUTED during the fresh breach"
        lines.append(("Q6", CONTROL_EXECUTED_PASS,
                      "t_check/t_act compared against the version binding; "
                      "material state flipped after the verdict -> Q2 reopened"))
        return EXIT_FAIL, False, lines, "blocked at the action boundary"
    lines.append(("Q6", CONTROL_EXECUTED_PASS,
                  "binding valid at actuation; repair applied"))
    return EXIT_PASS, True, lines, "EXECUTE within the latency budget"


PROFILES = {"I0-ordinary": _trace_gates_i0,
            "I1-defended": _trace_gates_i1,
            "I2-complete": _trace_gates_i2}


def check_spec_agreement():
    """Fail loudly if the in-code branches and fixture_spec.json diverge.

    Same discipline as examples/T08-S5Q2: the reference is an auditable
    artifact, and the spec/code agreement itself must not silently pass.
    The branch fields AND the correct_outcome verdicts are both guarded --
    the outcome field is the register's ruling, so it is checked against
    the hardcoded shipped table, not left to drift.
    """
    spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "fixture_spec.json")
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec_branches = spec.get("branches", {})
    for branch, fields in BRANCHES.items():
        if set(fields) != set(spec_branches.get(branch, {})) - {"correct_outcome"}:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s fields %s != fixture_spec.json "
                "%s -- fix the artifact or the code before any run."
                % (branch, sorted(fields),
                   sorted(set(spec_branches.get(branch, {})) - {"correct_outcome"})))
        for key, value in fields.items():
            if spec_branches.get(branch, {}).get(key) != value:
                raise SystemExit(
                    "SPEC/CODE DIVERGENCE: branch %s field %s = %r in code but "
                    "%r in fixture_spec.json."
                    % (branch, key, value, spec_branches.get(branch, {}).get(key)))
    # The ruling field: correct_outcome in the spec must agree with the
    # hardcoded shipped outcome table (exit 2 = blocked/reassess/hold,
    # exit 0 = execute; repair applied only on continuity).
    SPEC_OUTCOME_TO_SHIPPED = {
        "EXECUTE": (0, True),
        "REASSESS": (2, False),
        "BLOCKED_AT_BOUNDARY": (2, False),
        "HOLD_ESCALATE": (2, False),
    }
    for branch, expected in SHIPPED_I2.items():
        outcome = spec_branches.get(branch, {}).get("correct_outcome")
        if SPEC_OUTCOME_TO_SHIPPED.get(outcome) != expected:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s correct_outcome %r does not "
                "match the shipped outcome %s -- the register's ruling and "
                "the evaluator must not drift apart."
                % (branch, outcome, expected))
    if sorted(spec.get("gates", [])) != ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]:
        raise SystemExit("SPEC/CODE DIVERGENCE: gate register changed in "
                         "fixture_spec.json; update the evaluator and the "
                         "crosswalk table together.")


# --------------------------------------------------------------------------- #
# Mutation suite over the I2 gate layer (who tests the tester).
# --------------------------------------------------------------------------- #
MUTANTS = {
    "G1-no-supersession": "Q4 supersession check dropped (Patch B invisible)",
    "G2-cache-read": "Q3 reverts to the 5-minute cache (stale promoted to current)",
    "G3-no-binding": "Q6 recheck-to-act binding dropped (residual TOCTOU open)",
    "G4-blanket-deny": "Q5 scope bug: blanket stop (positive-continuity broken)",
}

CROSSWALK_EXPECTED = {
    # branch: which mutant(s) must be killed there (observable deviation).
    "G1-no-supersession": {"supersession"},
    "G2-cache-read": {"supersession", "ambiguity"},
    "G3-no-binding": {"act-window"},
    "G4-blanket-deny": {"continuity"},
}


def _kill_matrix():
    """{mutant: {branch: (exit, applied) deviations}} -- a mutant is killed on
    a branch when its observable pair deviates from the shipped I2 table."""
    matrix = {}
    for name in MUTANTS:
        kills = {}
        for branch in sorted(BRANCHES):
            code, applied, _l, _n = _trace_gates_i2(branch, BRANCHES[branch],
                                                    mutant=name)
            if (code, applied) != SHIPPED_I2[branch]:
                kills[branch] = (code, applied)
        matrix[name] = kills
    return matrix


def _print_branch(branch: str) -> int:
    print("=== branch: %s ===" % branch)
    world = BRANCHES[branch]
    for profile, fn in PROFILES.items():
        code, applied, lines, note = fn(branch, world)
        print("-- %s (exit %d, repair_applied=%s):" % (profile, code, applied))
        for gate, state, detail in lines:
            print("   %-3s %-28s %s" % (gate, state, detail))
        print("   -> %s" % note)
    print()
    return 0


def _print_crosswalk() -> None:
    print("gate crosswalk: S5 register <-> four-case matrix <-> T08 tests")
    print("-" * 66)
    rows = [
        ("Q1 explicit basis", "case A (SF-006 omission)", "Test B prep"),
        ("Q2 use-time recheck", "case B (temporal drift)", "Test B base Semantic TOCTOU"),
        ("Q3 source freshness", "assumption in T08-S5Q2 (out of scope there)", "Test C/D evidence"),
        ("Q4 supersession", "case B variant (state transition)", "Test C (D1 drift)"),
        ("Q5 bounded ambiguity/scope", "extension: UNKNOWN is not permission", "Test E (D3/D4/D5)"),
        ("Q6 recheck-to-act binding", "case D (act-window)", "Test B/C residual window"),
        ("positive continuity control", "case C (clean baseline)", "Test A continuity admission"),
    ]
    for a, b, c in rows:
        print("  %-30s %-46s %s" % (a, b, c))
    print()
    print("product anchors (verified against AWS docs, 2026-10-01):")
    print("  Q2 structural: Step Functions passes a start-input snapshot;")
    print("      live state needs an explicit Task state (docs.aws.amazon.com")
    print("      /step-functions/latest/dg/concepts-input-output-filtering.html)")
    print("  Q6 native lever: StopExecution stops a running Standard execution")
    print("      (api reference), observable via EventBridge Execution Status")
    print("      Change -- freeze-before-use has a product mechanism.")
    print("  Q4/Q6 binding: DynamoDB conditional writes + optimistic locking")
    print("      (version attribute) implement compare-before-act.")


def _selftest() -> int:
    problems = []
    # I0 must reproduce the capability-absent trace (S5 section 10.1): stale
    # patch executes on every branch; the gate register shows why.
    for branch in ("supersession", "act-window"):
        code, applied, lines, _ = _trace_gates_i0(branch, BRANCHES[branch])
        states = " ".join(s for _g, s, _d in lines)
        if not (code == EXIT_PASS and applied):
            problems.append("I0 %s: stale patch must execute (capability absent)" % branch)
        if states.count(CAPABILITY_ABSENT) != 3:
            problems.append("I0 %s: trace must show CAPABILITY_ABSENT at "
                            "exactly Q1/Q2/Q4" % branch)
    # I1 must reproduce the ineffective-control trace (S5 section 10.2) on
    # supersession: Q2 passes superficially, Q3/Q4 CONTROL_EXECUTED_FAILED.
    code, applied, lines, _ = _trace_gates_i1("supersession", BRANCHES["supersession"])
    states = [s for _g, s, _d in lines]
    if not (code == EXIT_PASS and applied):
        problems.append("I1 supersession: stale patch must execute (control present but incomplete)")
    if CONTROL_EXECUTED_FAILED not in states or CONTROL_EXECUTED_PASS not in states:
        problems.append("I1 supersession: trace must mix PASS and EXECUTED_FAILED")
    # I2 must produce the entire shipped table (including continuity EXECUTE).
    for branch, expected in SHIPPED_I2.items():
        code, applied, lines, _ = _trace_gates_i2(branch, BRANCHES[branch])
        if (code, applied) != expected:
            problems.append("I2 %s: expected %s, got (%d, %s)"
                            % (branch, expected, code, applied))
    # Every mutant must be killed on its expected branches.
    matrix = _kill_matrix()
    for name, expected_branches in CROSSWALK_EXPECTED.items():
        kills = set(matrix[name])
        missing = expected_branches - kills
        if missing:
            problems.append("mutant %s: not killed by %s (who tests the tester)"
                            % (name, sorted(missing)))
        extra = kills - expected_branches
        if extra:
            problems.append("mutant %s: killed by unexpected %s -- update the "
                            "crosswalk table if the register changed" % (name, sorted(extra)))

    print("S5-Qregister selftest v1 (gate traces + crosswalk + mutation suite)")
    print("-" * 68)
    ok = "ok" if not problems else "FAILED"
    print("  I0-ordinary : capability-absent trace reproduced          -> %s" % ok)
    print("  I1-defended : ineffective-control trace reproduced         -> %s" % ok)
    print("  I2-complete : shipped table (incl. continuity EXECUTE)     -> %s" % ok)
    print("  mutants     : G1-G4 killed on their crosswalk branches     -> %s" % ok)
    if problems:
        print()
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED.")
        return 1
    print("\nSELFTEST PASSED: the register is executable; the traces match the "
          "published diagnostics; every gate-layer mutant is killed on its "
          "crosswalk branches and nowhere else.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="qregister",
        description="Executable crosswalk of the S5 Q0-Q6 gate register: "
                    "I0/I1/I2 traces per fixture branch, S5<->four-case<->T08 "
                    "crosswalk, and a gate-layer mutation suite.",
    )
    parser.add_argument("--branch", choices=sorted(BRANCHES),
                        help="print the I0/I1/I2 gate traces for one branch")
    parser.add_argument("--crosswalk", action="store_true",
                        help="print the crosswalk table and product anchors")
    parser.add_argument("--mutants", action="store_true",
                        help="print the gate-layer mutation kill matrix")
    parser.add_argument("--selftest", action="store_true",
                        help="assert traces and mutants (default)")
    args = parser.parse_args(argv)

    check_spec_agreement()
    if args.crosswalk:
        _print_crosswalk()
        return 0
    if args.mutants:
        matrix = _kill_matrix()
        for name, kills in matrix.items():
            print("%-18s %s" % (name, "killed on " + ", ".join(sorted(kills)) if kills else "SURVIVED"))
        return 0 if all(matrix.values()) else 1
    if args.branch:
        return _print_branch(args.branch)
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
