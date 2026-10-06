#!/usr/bin/env python3
"""S5 gate-register crosswalk entry point (v2) -- the runnable companion to the
FG-TIDA contribution (use-cases #21, Annex S5 sections 7-10 and Annex T08).

What this example is, and what changed on 2026-10-06
----------------------------------------------------
It makes the scenario-local gate register **Q0-Q6** executable against the S5
fixture branches, and cross-walks it to the four-case negative-control matrix of
[`examples/T08-S5Q2`](../T08-S5Q2/).

The adversarial review of 2026-10-05 (ITU FG-TIDA use-cases #21, comment on
@zhaoxinghua09-cell) asked for the run to be a **blinded experiment** before it
joins any joint comparison. That request is now the shape of the code:

    simulation.py   this entry point; a reader of the harness
    harness.py      owns the branch identities and builds the observables
    implementation.py   the artifact under test; sees observables only

so a runner can no longer decide "I am on the ambiguity branch" -- it only ever
sees what was observed. The branch table, the mutation suite, and the
independent probe of the target state all live on the harness side.

What it demonstrates, gate by gate:

  I0-ordinary : Q1/Q2/Q4 CAPABILITY_ABSENT (no queryable decision basis), Q2
                not performed -- the stale queued patch executes during the
                breach (Annex S5 section 10.1).
  I1-defended : Q2 runs but Q3 reads a stale cache and Q4 omits the
                superseding generation -> CONTROL_EXECUTED_FAILED, stale state
                accepted as current (Annex S5 section 10.2).
  I2-complete : every gate carries evidence; Q6 recheck-to-act binding holds to
                the action boundary; bounded ambiguity produces escalation, not
                silent permission; and the positive-continuity branch still
                EXECUTEs within the latency budget (a deny-all runner fails it).

Fixture branches, per Annex S5 section 7.1, with **Patch B and the freeze as
two independent controls** (review point R-4):

  continuity      nothing supersedes, no freeze          -> EXECUTE
  supersession    Patch B supersedes, no freeze          -> REASSESS / requalify
  prohibition     no supersession, freeze in force       -> DENY (prohibition)
  patch-and-freeze  both                                 -> REASSESS / requalify
  act-window      freeze lands after the verdict, before the action
                                                         -> blocked at the boundary
  ambiguity       the authoritative source is unavailable inside the horizon
                                                         -> bounded HOLD / escalation

Crosswalk (see README.md for the full table):
  S5 Q1 <-> case A (omitted condition / SF-006)
  S5 Q2 <-> case B (temporal value drift)
  S5 Q4 <-> case B variant (superseding state transition)
  S5 Q6 <-> case D (check-then-act window)
  S5 positive continuity control <-> case C (clean baseline / deny-all catch)
  S5 ambiguous branch <-> an explicit extension: an unknown state must not be
                     permission (bounded HOLD), which the four-case matrix
                     leaves as roadmap.

Mutation suite (who tests the tester): four mutants of the I2 gate layer,
injected by the harness after the runner has ruled --
  M1-no-supersession  (Q4 outcome discarded)   killed by: supersession, patch-and-freeze
  M2-cache-read       (stale read served)      killed by: supersession, patch-and-freeze
  M3-no-binding       (Q6 dropped)             killed by: act-window
  M4-blanket-deny     (all gates pass, target still untouched; scope bug)
                                               killed by: continuity
The kill criterion is the three-channel observation
(guard decision, attempted action, **independently probed target state**) --
never the runner's own self-reported repair flag.

Deterministic: no randomness, no clock, no network. stdlib only, Python 3.9+.
A model result -- not an AWS product execution.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="qregister",
        description="Executable crosswalk of the S5 Q0-Q6 gate register over a "
                    "blinded fixture: the harness withholds the branch "
                    "identity, the runner sees observables only, and the target "
                    "state is measured independently.",
    )
    parser.add_argument("--branch", choices=sorted(harness.BRANCHES),
                        help="print the observables and the I0/I1/I2 traces for "
                             "one branch (the branch name stays outside the runner)")
    parser.add_argument("--crosswalk", action="store_true",
                        help="print the crosswalk table and the product anchors")
    parser.add_argument("--mutants", action="store_true",
                        help="print the gate-layer mutation kill matrix")
    parser.add_argument("--selftest", action="store_true",
                        help="assert blinding, controls, traces and mutants (default)")
    args = parser.parse_args(argv)

    harness.check_spec_agreement()
    if args.crosswalk:
        harness._print_crosswalk()
        return 0
    if args.mutants:
        matrix = harness._kill_matrix()
        for name, kills in matrix.items():
            print("%-20s %s" % (name, "killed on " + ", ".join(sorted(kills))
                                if kills else "SURVIVED"))
        return 0 if all(matrix.values()) else 1
    if args.branch:
        harness._print_branch(args.branch)
        return 0
    return harness.selftest()


if __name__ == "__main__":
    sys.exit(main())
