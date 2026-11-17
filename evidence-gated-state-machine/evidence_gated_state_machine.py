#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_gated_state_machine.py
================================
Minimal, runnable reference implementation of the four operational constructs
proposed in the supplemental public comment to FDA docket FDA-2026-N-7874
(Agentic AI & Foundation Models):

  1. Entity-level registration spine     (agent / model / tool / dataset, versioned + hash-chained)
  2. Evidence-gated state transitions     (a transition is INVALID when its evidence is unmet)
  3. Named silent-failure patterns        (stable headline accuracy but degraded subgroup, etc.)
  4. Human-authorized capability expansion (authority != capability; tier-crossing needs a human receipt)

This is a STATE-MACHINE DEMONSTRATION, NOT a medical product. It makes no
clinical claim. It exists to show that the proposed constructs are expressible
in a small, testable implementation that manufacturers' existing tooling
(design controls, change management, audit trails) can host.

License: Apache-2.0. This demonstration script is supporting evidence for the
accompanying public comment (Round 3, docket FDA-2026-N-7874); the accompanying
comment text itself is all rights reserved and not covered by this license.

Run:
    python evidence_gated_state_machine.py
Exit code 0 = all self-checks passed (the constructs behave as proposed).
Exit code 1 = a self-check failed (the demonstration is broken, do NOT cite).
"""

import hashlib
import json
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


class DenialReceipt(Exception):
    """Raised when a lifecycle-affecting transition's evidence requirement is
    unmet. The transition does NOT occur; a denial receipt is recorded.
    This is the 'invalidity, not discouragement' property."""


class EntityKind(Enum):
    AGENT = auto()
    MODEL = auto()
    TOOL = auto()
    DATASET = auto()


@dataclass
class Entity:
    kind: EntityKind
    identity: str          # e.g. "orchestrator", "gpt-class", "imaging-db"
    version: str           # e.g. "v1.0", "rev-Q3"
    permissions: Tuple[str, ...] = ()  # what this entity may do inside the device
    _hash: str = field(default="", repr=False)

    def materialize(self, prev_hash: str) -> str:
        payload = json.dumps(
            {"kind": self.kind.name, "identity": self.identity,
             "version": self.version, "permissions": list(self.permissions)},
            sort_keys=True,
        ).encode("utf-8")
        self._hash = hashlib.sha256(prev_hash.encode("utf-8") + payload).hexdigest()[:16]
        return self._hash


class Registry:
    """Entity-level registration spine. Each registration event and each
    configuration change leaves a hash-chained record (audit trail)."""

    def __init__(self) -> None:
        self.entities: Dict[Tuple[str, str, str], Entity] = {}
        self.chain: List[str] = ["genesis"]

    def register(self, e: Entity) -> str:
        h = e.materialize(self.chain[-1])
        self.chain.append(h)
        self.entities[(e.kind.name, e.identity, e.version)] = e
        return h

    def contains(self, kind: EntityKind, identity: str, version: str) -> bool:
        return (kind.name, identity, version) in self.entities

    def verify_chain(self) -> bool:
        """Re-walk the chain; returns True iff every link is consistent.
        Side-effect-free: recomputes each link WITHOUT overwriting the stored
        hash, so tampering with a registered entity's data is detected."""
        prev = "genesis"
        for e in self.entities.values():
            payload = json.dumps(
                {"kind": e.kind.name, "identity": e.identity,
                 "version": e.version, "permissions": list(e.permissions)},
                sort_keys=True,
            ).encode("utf-8")
            recomputed = hashlib.sha256(prev.encode("utf-8") + payload).hexdigest()[:16]
            if recomputed != e._hash:
                return False
            prev = e._hash
        return True


class Transition(Enum):
    INITIAL_ACTIVATION = auto()
    MODEL_UPDATE = auto()
    TOOL_CHANGE = auto()
    DATASET_REFRESH = auto()
    CAPABILITY_EXPANSION = auto()
    RETURN_TO_SERVICE = auto()


# Per-transition-type evidence requirements, pre-declared by the sponsor.
EVIDENCE_REQUIREMENTS: Dict[Transition, List[str]] = {
    Transition.INITIAL_ACTIVATION: ["nonclinical_benchmark", "clinical_confirmation"],
    Transition.MODEL_UPDATE: ["version_manifest", "benchmark_rerun"],
    Transition.TOOL_CHANGE: ["source_provenance", "regression_results"],
    Transition.DATASET_REFRESH: ["validity_window", "representativeness"],
    Transition.CAPABILITY_EXPANSION: ["tier_crossing_justification"],
    Transition.RETURN_TO_SERVICE: ["reverification_evidence", "recovery_rationale"],
}


class Gate:
    """Evidence-gated state transitions. The operational core of change control:
    every lifecycle-affecting change is a transition; a transition is GRANTED
    only when its declared evidence requirements are satisfied."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.receipts: List[dict] = []

    def attempt(
        self,
        transition: Transition,
        evidence: Dict[str, object],
        human_authorized: bool = False,
    ) -> dict:
        required = EVIDENCE_REQUIREMENTS[transition]
        missing = [r for r in required if not evidence.get(r)]

        if missing:
            receipt = {"transition": transition.name, "status": "DENIED",
                       "missing": missing, "human_authorized": human_authorized}
            self.receipts.append(receipt)
            raise DenialReceipt(
                f"transition {transition.name} DENIED - unmet evidence: {missing}")

        # Bright-line rule: capability expansion is a human-authorized transition.
        if transition is Transition.CAPABILITY_EXPANSION and not human_authorized:
            receipt = {"transition": transition.name, "status": "DENIED",
                       "missing": ["human_authorization"], "human_authorized": False}
            self.receipts.append(receipt)
            raise DenialReceipt(
                "capability expansion DENIED - authority != capability; "
                "human authorization required")

        receipt = {"transition": transition.name, "status": "GRANTED",
                   "evidence": [r for r in required], "human_authorized": human_authorized}
        self.receipts.append(receipt)
        return receipt


# --- Silent-failure detectors (postmarket monitoring vocabulary) -----------

def detect_population_drift(headline_accuracy: float, subgroup_accuracy: float,
                            threshold: float = 0.05) -> bool:
    """Stable headline accuracy but degraded subpopulation performance."""
    return (headline_accuracy - subgroup_accuracy) > threshold


def detect_expired_input(validity_window_end: str, current_date: str) -> bool:
    """A tool/dataset still in use but outside its declared validity window."""
    return current_date > validity_window_end


def detect_path_deviation(declared_envelope: set, observed_trajectory: set) -> bool:
    """Agent completes tasks through workflows outside its declared envelope."""
    return not observed_trajectory.issubset(declared_envelope)


def demo() -> None:
    print("== evidence_gated_state_machine - self-check ==")

    # 1) Entity registration spine + hash-chained audit trail
    reg = Registry()
    reg.register(Entity(EntityKind.AGENT, "orchestrator", "v1.0",
                        permissions=("read_only",)))
    reg.register(Entity(EntityKind.MODEL, "gpt-class", "v1.0"))
    reg.register(Entity(EntityKind.TOOL, "imaging-db", "2026.09",
                        permissions=("lookup",)))
    reg.register(Entity(EntityKind.DATASET, "qual-set", "rev-Q3"))
    assert reg.verify_chain(), "audit chain must be consistent after registration"
    assert reg.contains(EntityKind.TOOL, "imaging-db", "2026.09")
    print("  [PASS] entity registration spine: 4 entities registered, chain verifiable")

    # 2) Evidence-gated transition - GRANTED path
    gate = Gate(reg)
    r1 = gate.attempt(Transition.MODEL_UPDATE,
                      {"version_manifest": "manifest.json",
                       "benchmark_rerun": "pass@0.98"})
    assert r1["status"] == "GRANTED"
    print("  [PASS] evidence-gated transition (model update, evidence met): GRANTED")

    # 2b) Evidence-gated transition - DENIED path (invalidity, not discouragement)
    denied = False
    try:
        gate.attempt(Transition.TOOL_CHANGE, {"source_provenance": "ok"})
        # regression_results missing -> must raise
    except DenialReceipt as e:
        denied = True
        assert "regression_results" in e.args[0]
    assert denied, "unmet evidence MUST deny the transition (binary, inspectable)"
    assert gate.receipts[-1]["status"] == "DENIED"
    print("  [PASS] evidence-gated transition (tool change, evidence unmet): DENIED + receipt recorded")

    # 3) Human-authorized capability expansion - DENIED without human authority
    denied2 = False
    try:
        gate.attempt(Transition.CAPABILITY_EXPANSION,
                     {"tier_crossing_justification": "move to direct-clinical-influence"},
                     human_authorized=False)
    except DenialReceipt:
        denied2 = True
    assert denied2, "capability expansion without human authority MUST be denied"
    print("  [PASS] capability expansion without human authorization: DENIED")

    # 3b) GRANTED once a distinct human authority grants it
    r2 = gate.attempt(Transition.CAPABILITY_EXPANSION,
                     {"tier_crossing_justification": "move to direct-clinical-influence"},
                     human_authorized=True)
    assert r2["status"] == "GRANTED" and r2["human_authorized"] is True
    print("  [PASS] capability expansion with human authorization: GRANTED (authority != capability)")

    # 4) Silent-failure detectors - named patterns return True
    assert detect_population_drift(0.97, 0.86), "subgroup drift must be detected"
    assert detect_expired_input("2026.09.01", "2026.10.01"), "expired input must be detected"
    assert detect_path_deviation({"read_only", "lookup"},
                                 {"read_only", "external_record_write"}), \
        "path deviation must be detected"
    print("  [PASS] silent-failure detectors: population drift / expired input / path deviation all fire")

    # 5) Return-to-service only through the gate (non-monotonic re-qualification)
    r3 = gate.attempt(Transition.RETURN_TO_SERVICE,
                     {"reverification_evidence": "rerun-pass",
                      "recovery_rationale": "monitored condition cleared"})
    assert r3["status"] == "GRANTED"
    print("  [PASS] return-to-service: granted only through a new evidence-carrying transition")

    print(f"== audit trail: {len(gate.receipts)} receipts, chain depth {len(reg.chain)}")
    print("== RESULT: all self-checks passed (constructs behave as proposed)")


if __name__ == "__main__":
    try:
        demo()
    except AssertionError as exc:
        print(f"[FAIL] self-check FAILED: {exc}")
        sys.exit(1)
    except DenialReceipt as exc:
        print(f"[FAIL] unexpected denial: {exc}")
        sys.exit(1)
    sys.exit(0)
