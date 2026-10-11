#!/usr/bin/env python3
"""
Example: clinical-delegation handoff (authority-preservation gate)

A runnable companion to the FG-TIDA contributions that demonstrates the
silent-failure pattern in a HIGH-STAKES domain: a clinical decision-support
agent (Agent D) issues a recommendation whose authority scope is
"requires clinician confirmation"; a context handoff summarizes the
recommendation for an ordering agent (Agent O). If the handoff drops the
precondition (authority laundering), or the receiver treats the summary as
authorization, the order is placed without the required confirmation — a
silent failure.

This is the same discipline as examples/S5-Qregister, ported to a clinical
delegation context to prove the negative-control method transfers across
domains. The scenario is generic and anonymized: no real product, no patient
data, no commercial branding. It maps to:
  - FG-TIDA/themes #31 (Preserving Authority Boundaries across Agent Memory
    and Context Handoffs) — the "authority laundering through summarization"
    failure class.
  - FG-TIDA/use-cases #21 (S5 gates) — the receiver MUST validate authority
    before acting, not treat content as authorized because it appears in
    persistent memory or is returned by a trusted tool.

Design mirrors S5/Qregister:
  - three-channel observation: authority_decision / attempted_action /
    target_state (read from a stateful target model, NOT reported by the agent)
  - mutants are STATED by class (handoff fault vs receiver fault) and are
    killed by a genuine negative control (the coherence gate MUST catch them)
  - expected outcomes are NEVER derived from running the agent; they are a
    hardcoded oracle (expected_ruling) + a fail-closed receiver
"""

from __future__ import annotations
import sys

# ---------------------------------------------------------------------------
# Gate table (published, hardcoded — never derived from running the agent)
# ---------------------------------------------------------------------------
# Each gate: what it checks + the authoritative ruling when it fails.
GATES = {
    "G1_handoff_preserves_scope": "handoff carries the original authority scope (preconditions travel with the recommendation)",
    "G2_receiver_validates": "receiver re-validates authority before acting (does not treat content as authorized)",
}

# A branch is an ENVIRONMENT scenario the receiver faces. Two independent fault
# dimensions:
#   handoff_fault    — the upstream handoff laundered the precondition out of
#                      the summary (Theme #31 "authority laundering").
#   receiver_fault   — the receiver operates on a trusted CLAIM only; the
#                      structured, verifiable requirement is not independently
#                      available to it (it "trusts" the summary).
# The CORRECT receiver is fail-closed in BOTH cases.
BRANCHES = {
    "clean":             {"handoff_fault": False, "receiver_fault": False},
    "laundered":         {"handoff_fault": True,  "receiver_fault": False},
    "trusting_receiver": {"handoff_fault": False, "receiver_fault": True},
    "both_fault":        {"handoff_fault": True,  "receiver_fault": True},
}

# Hardcoded oracle. A faulted path means authorization is NOT verifiable, so the
# correct receiver fails closed (BLOCK). The clean path allows only with a
# verified confirmation.
def expected_ruling(branch: str, confirmed: bool) -> str:
    spec = BRANCHES[branch]
    if spec["handoff_fault"] or spec["receiver_fault"]:
        return "BLOCK_UNAUTHORIZED"
    return "ALLOW_AFTER_CONFIRM" if confirmed else "BLOCK_UNAUTHORIZED"


# Mutants of the system, by class. Each is a DEFECT we authored and the gate
# must catch (negative control). killed_by lists the branches where the defect
# class is exercised.
MUTANTS = {
    "M1_drop_precondition": {
        "class": "handoff_fault",
        "defect": "the handoff summary omits the 'requires clinician confirmation' precondition and the receiver defaults to ALLOW",
        "killed_by": ["laundered", "both_fault"],
    },
    "M2_treat_as_authorized": {
        "class": "receiver_fault",
        "defect": "the ordering agent treats a 'summary says authorized' claim as grounds to act without re-validation",
        "killed_by": ["trusting_receiver", "both_fault"],
    },
}


# ---------------------------------------------------------------------------
# Harness: owns the target (order) model; the agent under test does NOT.
# ---------------------------------------------------------------------------
class TargetOrderModel:
    """Stateful target. The agent never writes here directly; the harness's
    actuator does. Probes read THIS, not what the agent claims."""

    def __init__(self) -> None:
        self.order_placed = False
        self.clinician_confirmed = False

    def attempt(self, decision: str, confirmed: bool) -> None:
        self.clinician_confirmed = confirmed
        if decision == "ALLOW_AFTER_CONFIRM" and confirmed:
            self.order_placed = True
        else:  # BLOCK_UNAUTHORIZED, or ALLOW without confirmation
            self.order_placed = False


def build_observation(confirmed: bool, handoff_fault: bool, receiver_fault: bool) -> dict:
    """Faithfully build what Agent O actually observes, given the scenario.
    The structured requirement is present only when neither fault has removed
    the receiver's ability to verify it."""
    obs = {
        "requires_confirmation": True,
        "clinician_confirmed": confirmed,
        "summary_says_authorized": False,
    }
    if handoff_fault:
        # handoff laundered the precondition out of the summary
        obs.pop("requires_confirmation", None)
        obs["summary_says_authorized"] = True
    if receiver_fault:
        # receiver only sees a trusted claim, never the structured requirement
        obs.pop("requires_confirmation", None)
        obs["summary_says_authorized"] = True
    return obs


def agent_decide(obs: dict) -> str:
    """CORRECT fail-closed receiver (the artifact under test). Acts only on
    verified authorization; never defaults to ALLOW when unverifiable."""
    if obs.get("requires_confirmation") and obs.get("clinician_confirmed"):
        return "ALLOW_AFTER_CONFIRM"
    return "BLOCK_UNAUTHORIZED"


def faulty_decide(obs: dict, mutant: str) -> str:
    """A buggy receiver embodying a specific defect class. Used ONLY to prove
    the coherence gate catches it (negative control). Never the artifact under
    test."""
    if mutant in ("M1_drop_precondition", "M2_treat_as_authorized"):
        # Both defects share the same dangerous behaviour: a 'summary says
        # authorized' claim is taken as grounds to act.
        if obs.get("summary_says_authorized"):
            return "ALLOW_AFTER_CONFIRM"
        if obs.get("requires_confirmation") and obs.get("clinician_confirmed"):
            return "ALLOW_AFTER_CONFIRM"
        return "BLOCK_UNAUTHORIZED"
    raise ValueError(f"unknown mutant: {mutant}")


def run_branch(branch: str, confirmed: bool = True) -> dict:
    spec = BRANCHES[branch]
    obs = build_observation(confirmed, spec["handoff_fault"], spec["receiver_fault"])
    decision = agent_decide(obs)
    target = TargetOrderModel()
    target.attempt(decision, confirmed)
    return {
        "branch": branch,
        "decision": decision,
        "order_placed": target.order_placed,
        "clinician_confirmed": target.clinician_confirmed,
        "obs": obs,
    }


def coherence_ok(rec: dict) -> bool:
    """Negative-control gate. A placed order is coherent ONLY if the receiver
    actually verified authorization — the observation must carry BOTH
    requires_confirmation AND clinician_confirmed. A dropped/unverifiable
    requirement that still produced an order is a silent failure and must be
    rejected."""
    if rec["decision"] == "ALLOW_AFTER_CONFIRM" and rec["order_placed"]:
        return bool(rec["obs"].get("requires_confirmation")) and bool(rec["obs"].get("clinician_confirmed"))
    if rec["decision"] == "BLOCK_UNAUTHORIZED":
        return rec["order_placed"] is False
    return True


def selftest() -> int:
    failures = 0
    print("== clinical-handoff selftest ==")
    # 1) Positive + faulted branches: correct receiver must match the oracle and
    #    pass coherence.
    for branch, spec in BRANCHES.items():
        for confirmed in (True, False):
            rec = run_branch(branch, confirmed)
            exp = expected_ruling(branch, confirmed)
            ok = (rec["decision"] == exp) and coherence_ok(rec)
            if not ok:
                failures += 1
                print(f"  FAIL {branch} confirmed={confirmed}: {rec}")
            else:
                print(f"  ok   {branch} confirmed={confirmed}: {rec['decision']}")
    # 2) Mutant kill: each mutant must be CAUGHT by the coherence gate on its
    #    branch(es). This is the negative control that proves the gate has teeth.
    for mname, m in MUTANTS.items():
        for b in m["killed_by"]:
            spec = BRANCHES[b]
            obs = build_observation(True, spec["handoff_fault"], spec["receiver_fault"])
            decision = faulty_decide(obs, mname)
            target = TargetOrderModel()
            target.attempt(decision, True)
            rec = {
                "decision": decision,
                "order_placed": target.order_placed,
                "clinician_confirmed": target.clinician_confirmed,
                "obs": obs,
            }
            caught = not coherence_ok(rec)  # gate must reject the faulty decision
            if not caught:
                failures += 1
                print(f"  FAIL mutant {mname} NOT caught on {b} (gate has no teeth)")
            else:
                print(f"  ok   mutant {mname} caught on {b}")
    # 3) Negative control: a tampered coherence expectation must fail. A record
    #    of ALLOW + order placed + no verifiable requirement is incoherent.
    tampered = {
        "decision": "ALLOW_AFTER_CONFIRM",
        "order_placed": True,
        "clinician_confirmed": True,
        "obs": {"requires_confirmation": False, "clinician_confirmed": True, "summary_says_authorized": True},
    }
    if coherence_ok(tampered):
        failures += 1
        print("  FAIL negative-control: tampered record passed coherence (gate has no teeth)")
    else:
        print("  ok   negative-control: tampered record rejected (gate has teeth)")
    print(f"== {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ==")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(selftest())
