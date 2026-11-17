#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Negative-control demo (QC-07: relevant errors must be able to fail).

Demonstrates that the FIXED verify_chain() detects external tampering with a
registered entity's data: the baseline chain verifies True after registration,
then a version field is modified IN PLACE (bypassing register()); the chain
must now verify False.

Companion to evidence_gated_state_machine.py (SHA-256 26ED6159...).
Run:  python demo_tamper_check.py
Exit 0 = tampering detected (fix works); exit 1 = tampering NOT detected.
"""
import sys

from evidence_gated_state_machine import Entity, EntityKind, Registry


def main() -> None:
    print("== negative control: tamper detection (QC-07) ==")
    reg = Registry()
    reg.register(Entity(EntityKind.AGENT, "orchestrator", "v1.0",
                        permissions=("read_only",)))
    reg.register(Entity(EntityKind.MODEL, "gpt-class", "v1.0"))
    assert reg.verify_chain(), "baseline chain must verify True"
    print("  [PASS] baseline chain verifies True after registration")

    # External tamper: modify a registered entity's version field IN PLACE,
    # bypassing register(). The recomputed hash must no longer match the
    # hash stored at registration time.
    target = next(e for e in reg.entities.values() if e.identity == "gpt-class")
    target.version = "v1.1-tampered"
    detected = not reg.verify_chain()
    assert detected, "tampering MUST be detected (verify_chain must return False)"
    print("  [PASS] tampered version field detected: verify_chain() = False")
    print("== RESULT: negative control passed (tampering is detected) ==")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"[FAIL] negative control FAILED: {exc}")
        sys.exit(1)
    sys.exit(0)
