#!/usr/bin/env python3
"""S5 gate-register implementation (v2) -- the artifact under test.

THE BOUNDARY OF THIS FILE
-------------------------
This module is the **implementation under test**. It is deliberately kept in a
file of its own so that the blinding required by the 2026-10-05 FG-TIDA review
(use-cases #21, comment on @zhaoxinghua09-cell) is *structural* rather than
conventional:

  * the harness keeps the branch identity (`continuity` / `supersession` /
    `prohibition` / `patch-and-freeze` / `act-window` / `ambiguity`) in
    `harness.py`; the branch **name never crosses this boundary**;
  * what crosses it is an :class:`Observation` -- a record of *observable*
    quantities only (current generation, source state/version, freeze state,
    supersession lineage, timestamps, authority/policy state, binding tokens);
  * this module therefore cannot take a decision "because it is the ambiguity
    branch": it can only take a decision from what it observed, which is the
    property the review asked for;
  * it also **cannot** report the target state. The target state lives in the
    harness's own model (`harness.TargetModel`); after the harness's actuator
    performs the attempted action, the harness reads that model back. Nothing
    here is asked about the target, and nothing here could answer -- an
    implementation that graded its own homework would make the whole
    experiment self-confirming.

  Stated plainly, because a boundary claim is exactly the sort of claim a
  review will test: the module boundary removes the ordinary escape (no name
  in scope), it does not stop a *resourceful* reader. The residual routes --
  a lazy ``import harness``, a read of ``fixture_spec.json``, ``open()``,
  ``os.environ``, ``sys.modules`` -- are not closed by the boundary; they are
  scanned for by the harness's ``_assert_blind``, which fails the selftest if
  any of them appears in this module's executable code. Detection, not
  invisibility, is what actually holds here.

Every gate below is decided from observables, and every decision returns an
explicit three-channel record:

  guard decision  -- what the register ruled (the gate's output)
  attempted action -- whether the repair was actually pushed at the target
  Q0-Q6 trace     -- the per-gate evidence that supports the ruling

Control independence (review point R-4)
---------------------------------------
`patch_b` (Patch B supersedes the queued generation) and `freeze` (a material
freeze is in force) are two *separate* inputs here. They are never merged into
one "supersession" flag, and they are never both implied by one branch: the four
combinations produce four distinct rulings, so a defect that collapses them is
observable. The harness holds the branch table, so which fixture a run came
from stays outside this file.

A model result -- not an AWS product execution.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# The observable contract. This is the ONLY type the harness may hand over,
# and the only thing this implementation may read.
# --------------------------------------------------------------------------- #

FREEZE_NONE = "none"
FREEZE_ACTIVE = "active"           # a freeze in force before the verdict
FREEZE_POST_VERDICT = "post_verdict"  # lands after the verdict, before the act

GUARD_EXECUTE = "EXECUTE"                    # gates satisfied, repair applied
GUARD_REASSESS = "BLOCK_REASSESS"            # Q4 supersession -> requalify
GUARD_DENY = "DENY"                          # active freeze -> prohibition
GUARD_BOUNDARY = "BLOCK_BOUNDARY"            # Q6 binding broken at the act
GUARD_HOLD = "HOLD_ESCALATE"                 # Q5: UNKNOWN is not permission

ACTION_APPLY = "APPLY"
ACTION_NONE = "NONE"


class Observation:
    """Observables only. Deliberately flat, and deliberately not a Mapping.

    A Mapping would let the caller plant an extra key inside a duck-typed
    object and read it back; here the field list is closed, so the only way to
    widen this record is to edit this class -- which the harness-facing
    blinding check reads as a divergence.

    ``supersession_lineage`` is a tuple of generation labels that supersede
    the queued one (empty = nothing superseded it). It is the observable
    counterpart of "Patch B exists", and it is kept separate from
    ``freeze_state`` on purpose: two controls, two channels.
    """

    __slots__ = ("current_generation", "source_version", "source_available",
                 "freeze_state", "supersession_lineage", "timestamps",
                 "authority_state", "binding_tokens")

    def __init__(self, current_generation, source_version, source_available,
                 freeze_state, supersession_lineage, timestamps,
                 authority_state, binding_tokens):
        self.current_generation = current_generation
        self.source_version = source_version
        self.source_available = source_available
        self.freeze_state = freeze_state
        self.supersession_lineage = tuple(supersession_lineage)
        self.timestamps = dict(timestamps)
        self.authority_state = authority_state
        self.binding_tokens = tuple(binding_tokens)

    def as_record(self):
        """A display-friendly view. Contains no branch identity."""
        return {
            "current_generation": self.current_generation,
            "source_version": self.source_version,
            "source_available": self.source_available,
            "freeze_state": self.freeze_state,
            "supersession_lineage": list(self.supersession_lineage),
            "timestamps": dict(self.timestamps),
            "authority_state": self.authority_state,
            "binding_tokens": list(self.binding_tokens),
        }


class Verdict:
    """What the implementation is willing to state. It states no target state."""

    __slots__ = ("guard_decision", "attempted_action", "lines", "note")

    def __init__(self, guard_decision, attempted_action, lines, note):
        self.guard_decision = guard_decision
        self.attempted_action = attempted_action
        self.lines = list(lines)
        self.note = note


CAPABILITY_ABSENT = "CAPABILITY_ABSENT"
CONTROL_EXECUTED_FAILED = "CONTROL_EXECUTED_FAILED"
CONTROL_PRESENT_NOT_INVOKED = "CONTROL_PRESENT_NOT_INVOKED"
CONTROL_EXECUTED_PASS = "CONTROL_EXECUTED_PASS"

EXIT_PASS, EXIT_FAIL = 0, 2


# --------------------------------------------------------------------------- #
# Implementation profiles. Signature: (Observation) -> Verdict.
# No branch argument. No branch state in scope: this module does not import the
# harness, and the harness does not ship a branch table with the observation.
# --------------------------------------------------------------------------- #

def _trace_gates_i0(obs):
    """Ordinary route: the scheduler has no semantic basis object at all.

    Whatever the observables say, nothing in the model can stop the attempt --
    which is the point of the profile, and why it is not a "correct" profile.
    """
    lines = [("Q0", CONTROL_EXECUTED_PASS, "token/job approval valid (technical grant only)"),
             ("Q1", CAPABILITY_ABSENT, "no explicit semantic precondition object beyond job metadata"),
             ("Q2", CAPABILITY_ABSENT, "not performed; queue-time decision reused at use time"),
             ("Q3", "absent", "never assessed (no semantic recheck occurs)"),
             ("Q4", CAPABILITY_ABSENT, "Patch B / freeze lineage outside the model")]
    return Verdict(GUARD_EXECUTE, ACTION_APPLY, lines,
                   "stale queued patch EXECUTED during the breach")


def _trace_gates_i1(obs):
    """Defended route: the recheck runs, its inherent defects do not.

    The two defects are visible as observables: the source is unavailable (so
    the 5-minute cache would be promoted to current fact) and, on the
    check-then-act variant, a freeze landed after the verdict. Nothing here
    names which fixture produced those observables.
    """
    lines = [("Q0", CONTROL_EXECUTED_PASS, "current grant qualified"),
             ("Q1", CONTROL_EXECUTED_PASS, "semantic preconditions recorded"),
             ("Q2", CONTROL_EXECUTED_PASS, "live recheck function ran")]
    if not obs.source_available:
        # The defect: with no live source, the stale cache is promoted to
        # truth instead of entering bounded HOLD.
        lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                      "live source unavailable; 5-minute cache promoted to "
                      "current fact (stale state accepted as current)"))
        lines.append(("Q4", CONTROL_EXECUTED_FAILED,
                      "superseding-patch lineage not assessed (basis read "
                      "from the stale cache)"))
        lines.append(("Q5", "bypassed",
                      "no bounded-ambiguity path: silent permission on unknown state"))
        return Verdict(GUARD_EXECUTE, ACTION_APPLY, lines,
                       "repair EXECUTED on stale evidence")
    lines.append(("Q3", CONTROL_EXECUTED_FAILED,
                  "recheck reads the stale cache; the current source version "
                  "is invisible (stale state accepted as current)"))
    lines.append(("Q4", CONTROL_EXECUTED_FAILED,
                  "Patch B generation / freeze scope omitted from the "
                  "qualified basis"))
    lines.append(("Q5", "bypassed",
                  "action not held because no failure was detected"))
    if obs.freeze_state == FREEZE_POST_VERDICT:
        lines.append(("Q6", "absent",
                      "no check-to-act binding; fresh post-verdict breach "
                      "undetected"))
    return Verdict(GUARD_EXECUTE, ACTION_APPLY, lines,
                   "repair EXECUTED during the breach")


def _trace_gates_i2(obs):
    """Complete route: every gate evidenced, every control decided separately.

    The register's division of labour: Q3 qualifies the CHECK, Q4 detects a
    superseding state transition, the freeze is a prohibition, and Q6 binds the
    validated state to the actuation. Patch B and the freeze are read as two
    independent observables, so a run where only one of them fires is decided
    by exactly that one -- and the two-fire case is decided by Patch B, which
    is the requalification the register prescribes.
    """
    lines = [("Q0", CONTROL_EXECUTED_PASS, "grant current, subject/scope bound"),
             ("Q1", CONTROL_EXECUTED_PASS, "basis reconstructable and queryable")]
    # Q3: source freshness. Unknown source state is not permission (Q5).
    if not obs.source_available:
        lines.append(("Q3", "SOURCE_ABSENT",
                      "authoritative source unavailable inside the horizon"))
        lines.append(("Q5", CONTROL_EXECUTED_PASS,
                      "bounded non-execution: escalation raised, owner and "
                      "deadline assigned; unknown state is not permission"))
        return Verdict(GUARD_HOLD, ACTION_NONE, lines, "HOLD/ESCALATE (bounded)")
    lines.append(("Q2", CONTROL_EXECUTED_PASS,
                  "material preconditions re-evaluated at use time"))
    lines.append(("Q3", CONTROL_EXECUTED_PASS,
                  "source identity + observed_at inside the declared "
                  "freshness bound"))
    # Q4: supersession. Decided on the lineage alone; the freeze is not
    # smuggled in here, and does not need to be.
    if obs.supersession_lineage:
        lines.append(("Q4", CONTROL_EXECUTED_PASS,
                      "superseding generation %s recognized as a state "
                      "transition" % (", ".join(obs.supersession_lineage),)))
        lines.append(("Q5", CONTROL_EXECUTED_PASS,
                      "affected generation requalified; unchanged units unaffected"))
        # Truth-table row 4 (review round 2, MUST M2): when BOTH controls are
        # set, the trace must carry BOTH reasons. (T,T) and (T,F) share the
        # guard decision, so the trace is the only place the second reason can
        # be told apart -- a prohibition silently dropped here would make the
        # two rows indistinguishable to any reader of the record.
        if obs.freeze_state == FREEZE_ACTIVE:
            lines.append(("Q5", CONTROL_EXECUTED_PASS,
                          "BOTH REASONS PRESENT: the superseding generation "
                          "above AND an active freeze in force (prohibition) -- "
                          "the requalification proceeds, and the prohibition is "
                          "recorded alongside it, not hidden by it"))
        return Verdict(GUARD_REASSESS, ACTION_NONE, lines,
                       "REASSESS -> affected generation blocked")
    # Q4 vacuous: no superseding transition. The freeze is a separate control.
    lines.append(("Q4", CONTROL_EXECUTED_PASS, "no superseding state transition found"))
    if obs.freeze_state == FREEZE_ACTIVE:
        lines.append(("Q5", CONTROL_EXECUTED_PASS,
                      "active freeze in force -> scoped prohibition"))
        return Verdict(GUARD_DENY, ACTION_NONE, lines, "DENY (active freeze)")
    lines.append(("Q5", CONTROL_EXECUTED_PASS, "scoped response, bounded horizon"))
    # Q6: recheck-to-act binding, against the live actuation state.
    if obs.freeze_state == FREEZE_POST_VERDICT:
        lines.append(("Q6", CONTROL_EXECUTED_PASS,
                      "binding compared against the live actuation state; the "
                      "freeze flipped after the verdict -> action boundary reopened"))
        return Verdict(GUARD_BOUNDARY, ACTION_NONE, lines,
                       "blocked at the action boundary")
    lines.append(("Q6", CONTROL_EXECUTED_PASS,
                  "binding valid at actuation; repair applied"))
    return Verdict(GUARD_EXECUTE, ACTION_APPLY, lines,
                   "EXECUTE within the latency budget")


PROFILES = {"I0-ordinary": _trace_gates_i0,
            "I1-defended": _trace_gates_i1,
            "I2-complete": _trace_gates_i2}


def run(profile, obs):
    """One run: profile name -> (exit code, Verdict).

    The exit code is derived from the guard decision here so that the harness
    has a single numeric handle; the guard decision itself is the semantic
    output, and the harness compares it alongside the attempted action and the
    independently probed target state.
    """
    fn = PROFILES[profile]
    verdict = fn(obs)
    exit_code = EXIT_PASS if verdict.guard_decision == GUARD_EXECUTE else EXIT_FAIL
    return exit_code, verdict
