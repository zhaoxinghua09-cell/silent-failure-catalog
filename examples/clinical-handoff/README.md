# Example: clinical-delegation handoff (authority-preservation gate)

A runnable companion proving the **silent-failure / authority-preservation**
pattern in a **high-stakes clinical-delegation** context. It is the same
negative-control discipline as [`../S5-Qregister`](../S5-Qregister/) — ported to
show the method **transfers across domains**, not just to IT infrastructure
(AWS Step Functions / DynamoDB anchors used there).

## Why a medical scenario

FG-TIDA is about agentic-AI trust, identity and delegation. The failure class
"authority / evidence is silently lost when it passes through a transformation"
is most dangerous — and most persuasive — in **clinical decision support**, where
a dropped precondition (e.g. "requires clinician confirmation") can mean a
treatment order is placed without the required human authorization. Demonstrating
the gate on a high-stakes scenario makes the pattern **unavoidable** to senior
engineers; demonstrating it on a *generic, anonymized* scenario keeps the
contribution within ToR scope (issue / mapping / reference-implementation) and
clear of any commercial medical-advisory framing.

## The scenario (generic, anonymized — no product, no patient data, no brand)

- Agent **D** (diagnostic-support) issues a recommendation whose authority scope
  is `requires clinician confirmation`.
- A **context handoff** summarizes the recommendation for Agent **O**
  (ordering).
- If the handoff **launders** the precondition (drops it) — or Agent O **treats
  the summary as authorization** without re-validating — the order is placed
  without confirmation: a **silent failure**.

This is exactly the failure class in **FG-TIDA/themes #31** ("Preserving
Authority Boundaries across Agent Memory and Context Handoffs" — the
"authority laundering through summarization" risk) and the S5 gates of
**FG-TIDA/use-cases #21**.

## What it shows (three-channel observation)

| Channel | Captured | Who owns it |
|---|---|---|
| authority decision | what Agent O ruled | Agent O (artifact under test) |
| attempted action | was the order pushed? | harness actuator |
| target state | order-system state read back | **harness's own `TargetOrderModel`**, not Agent O |

The harness owns a stateful target and probes *that* — so an agent that graded
its own homework ("order not placed") is not believed. Expected outcomes are a
**hardcoded oracle** (`expected_ruling`) — never derived from running the agent —
and the receiver is **fail-closed**: any path where authorization is not
verifiable (precondition laundered, or a trusted claim with no structured
requirement) returns `BLOCK_UNAUTHORIZED`. A **negative-control gate**
(`coherence_ok`) rejects any record where an order was placed without a
*verified* requirement, so the assertions cannot become tautological.

## Branches (environment scenarios) and the oracle

| Branch | handoff fault | receiver fault | Expected ruling (confirmed) |
|---|---|---|---|
| `clean` | no | no | `ALLOW_AFTER_CONFIRM` if confirmed, else `BLOCK_UNAUTHORIZED` |
| `laundered` | yes | no | `BLOCK_UNAUTHORIZED` (fail-closed) |
| `trusting_receiver` | no | yes | `BLOCK_UNAUTHORIZED` (fail-closed) |
| `both_fault` | yes | yes | `BLOCK_UNAUTHORIZED` (fail-closed) |

## Mutants (stated by class; killed by a genuine negative control)

| Mutant | Class | Defect | Killed on |
|---|---|---|---|
| `M1_drop_precondition` | handoff fault | handoff omits the confirmation precondition and the receiver defaults to `ALLOW` | `laundered`, `both_fault` |
| `M2_treat_as_authorized` | receiver fault | Agent O treats a "summary says authorized" claim as grounds to act | `trusting_receiver`, `both_fault` |

Each mutant is a defect we *authored* and injected into a `faulty_decide`
variant. The selftest proves the **coherence gate catches it**: a faulty
decision that places an order without a verifiable requirement fails
`coherence_ok`. This is the negative control that gives the example teeth
(R1 — a gate that cannot fail is decoration). A clean run reports
`== PASS (0 failures) ==` with `EXIT=0`.

## Usage

```
python clinical_handoff.py            # selftest (asserts; non-zero on failure)
```

## Mapping to the FG-TIDA catalogue

- `examples/S5-Qregister` — the infrastructure-domain twin (blinded experiment,
  four-mutant matrix, AWS product anchors). This example is the **clinical
  transfer proof**.
- `examples/T08-S5Q2` — the four-case discriminative-power matrix both draw on.
- Core catalogue (`../..`): the silent-failure cases + negative-control test
  patterns both examples instantiate.

> **Qualification:** a model demonstration, not a clinical product. Scenarios are
> generic and anonymized; no real patient data, no specific EHR/vendor, no
> commercial branding. The commercial medical-regulatory advisory stays separate
> from this open reference.
