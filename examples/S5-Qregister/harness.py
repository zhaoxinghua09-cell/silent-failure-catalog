#!/usr/bin/env python3
"""S5-Qregister harness (v2) -- holds the branch identities, blinds the runner.

Why this file exists separately from ``implementation.py``
----------------------------------------------------------
The 2026-10-05 adversarial review on FG-TIDA use-cases #21 (comment on
@zhaoxinghua09-cell) required the run under comparison to be a **blinded
experiment**: whatever is evaluated must see only *observables*, and the
identity of the branch (which fixture produced those observables) must never
travel with them. Placing the branch table here and nowhere else makes that a
structural property, not a convention:

  * ``implementation.py`` imports nothing from this module, so it has no name
    in scope for ``BRANCHES``. That closes the *ordinary* escape only, and
    this file no longer claims more: a lazy ``import harness``, a read of
    ``fixture_spec.json`` off disk, or an ``os.environ`` / ``sys.modules``
    trick would all reach around the boundary. Those routes are scanned for
    by :func:`_assert_blind` (added after review round 2 judged the earlier
    "closed by module boundaries" sentence false) and fail the selftest on
    sight;
  * this module builds the :class:`Observation` and hands it over, so the
    branch name stops at this line;
  * the harness also owns a **stateful model of the target**
    (:class:`TargetModel`) that its own actuator rewrites, and reads the model
    back after the run (:func:`probe_target_state`) -- "the guard said
    EXECUTE, the action said APPLY, and the target did not move" is a state
    of that object, not a boolean the runner gets to supply.

Three observation channels, per review point R-5:

  1. guard decision     -- what the runner ruled
  2. attempted action   -- whether the repair was pushed at the target
  3. target state       -- measured here, from the harness's own model of the
                           target, independent of what the runner claims

The kill criterion for the mutation suite compares the whole triple, never a
runner-supplied boolean.

A model result -- not an AWS product execution.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import implementation as impl  # noqa: E402  (boundary: the artifact under test)

FREEZE_NONE = impl.FREEZE_NONE
FREEZE_ACTIVE = impl.FREEZE_ACTIVE
FREEZE_POST_VERDICT = impl.FREEZE_POST_VERDICT

GUARD_EXECUTE = impl.GUARD_EXECUTE
GUARD_REASSESS = impl.GUARD_REASSESS
GUARD_DENY = impl.GUARD_DENY
GUARD_BOUNDARY = impl.GUARD_BOUNDARY
GUARD_HOLD = impl.GUARD_HOLD

ACTION_APPLY = impl.ACTION_APPLY
ACTION_NONE = impl.ACTION_NONE

EXIT_PASS, EXIT_FAIL = impl.EXIT_PASS, impl.EXIT_FAIL


# --------------------------------------------------------------------------- #
# The branch table. HELD HERE, NEVER PASSED TO THE IMPLEMENTATION.
# --------------------------------------------------------------------------- #
# patch_b and freeze are two independent controls: the four combinations are
# four separate branches, so a runner that merges them cannot produce the right
# answer on more than one of them.
BRANCHES = {
    "continuity": {
        "patch_b": False, "freeze": False, "source_available": True,
        "post_verdict_freeze": False,
        "label": "nothing material changes (positive control)",
        "correct_outcome": "EXECUTE",
    },
    "supersession": {
        "patch_b": True, "freeze": False, "source_available": True,
        "post_verdict_freeze": False,
        "label": "Patch B supersedes the queued generation, no freeze",
        "correct_outcome": "REASSESS",
    },
    "prohibition": {
        "patch_b": False, "freeze": True, "source_available": True,
        "post_verdict_freeze": False,
        "label": "freeze in force, nothing supersedes (prohibition)",
        "correct_outcome": "DENY",
    },
    "patch-and-freeze": {
        "patch_b": True, "freeze": True, "source_available": True,
        "post_verdict_freeze": False,
        "label": "Patch B supersedes AND a freeze is in force",
        "correct_outcome": "REASSESS",
    },
    "act-window": {
        "patch_b": False, "freeze": False, "source_available": True,
        "post_verdict_freeze": True,
        "label": "freeze lands after the verdict, before the action",
        "correct_outcome": "BLOCKED_AT_BOUNDARY",
    },
    "ambiguity": {
        "patch_b": False, "freeze": False, "source_available": False,
        "post_verdict_freeze": False,
        "label": "authoritative source unavailable inside the horizon",
        "correct_outcome": "HOLD_ESCALATE",
    },
}

# The shipped triple per branch: (guard decision, attempted action, target
# changed). Hardcoded from the published register, NOT derived from running the
# code -- deriving the expectation from the code under test would make every
# assertion tautological.
SHIPPED = {
    "continuity":     (GUARD_EXECUTE, ACTION_APPLY, True),
    "supersession":   (GUARD_REASSESS, ACTION_NONE, False),
    "prohibition":    (GUARD_DENY, ACTION_NONE, False),
    "patch-and-freeze": (GUARD_REASSESS, ACTION_NONE, False),
    "act-window":     (GUARD_BOUNDARY, ACTION_NONE, False),
    "ambiguity":      (GUARD_HOLD, ACTION_NONE, False),
}

SPEC_OUTCOME_TO_GUARD = {
    "EXECUTE": GUARD_EXECUTE,
    "REASSESS": GUARD_REASSESS,
    "DENY": GUARD_DENY,
    "BLOCKED_AT_BOUNDARY": GUARD_BOUNDARY,
    "HOLD_ESCALATE": GUARD_HOLD,
}

GATE_SET = ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]


# --------------------------------------------------------------------------- #
# Mutation suite. Injected HERE, applied after the runner has already ruled, so
# the defect never lives inside the artifact under test: a mutant written into
# the code under comparison would be a defect we authored, not a defect we
# measured.
# --------------------------------------------------------------------------- #
MUTANTS = {
    "M1-no-supersession":
        "the Q4 supersession outcome is discarded: a superseding generation "
        "is let through as EXECUTE",
    "M2-cache-read":
        "the use-time read is served from the stale (pre-event) view",
    "M3-no-binding":
        "the Q6 recheck-to-act binding is skipped: a post-verdict freeze no "
        "longer blocks",
    "M4-blanket-deny":
        "scope bug: every gate satisfied and the target still not touched "
        "(a blanket stop, positive control broken)",
}

MUTANT_KILLERS = {
    "M1-no-supersession": {"supersession", "patch-and-freeze"},
    "M2-cache-read": {"supersession", "patch-and-freeze"},
    "M3-no-binding": {"act-window"},
    "M4-blanket-deny": {"continuity"},
}


def check_spec_agreement():
    """Fail loudly if the branch table and fixture_spec.json diverge.

    Same discipline as the sibling example: the fixture is an auditable
    artifact, and the code-vs-spec agreement itself must not silently pass.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixture_spec.json")
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec_branches = spec.get("branches", {})
    keys = {"patch_b", "freeze", "source_available", "post_verdict_freeze"}
    action_names = {ACTION_APPLY: "APPLY", ACTION_NONE: "NONE"}
    for branch, fields in BRANCHES.items():
        other = set(spec_branches.get(branch, {})) - {"correct_outcome",
                                                      "expected_action",
                                                      "expected_target_changed"}
        if other != keys:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s fields %s != fixture_spec.json "
                "%s -- fix the artifact or the code before any run."
                % (branch, sorted(keys), sorted(other)))
        for key in sorted(keys):
            if spec_branches[branch][key] != fields[key]:
                raise SystemExit(
                    "SPEC/CODE DIVERGENCE: branch %s field %s = %r in the "
                    "harness but %r in fixture_spec.json."
                    % (branch, key, fields[key], spec_branches[branch][key]))
        # S4: the shipped triple lives in the spec too, so a reader auditing
        # the fixture alone sees the expectations, and a drift between the
        # spec and SHIPPED stops the run before any trace is printed.
        if spec_branches[branch].get("expected_action") \
                != action_names[SHIPPED[branch][1]]:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s expected_action %r does not "
                "match the shipped attempted action %r."
                % (branch, spec_branches[branch].get("expected_action"),
                   action_names[SHIPPED[branch][1]]))
        if spec_branches[branch].get("expected_target_changed") \
                != SHIPPED[branch][2]:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s expected_target_changed %r "
                "does not match the shipped target channel %r."
                % (branch, spec_branches[branch].get("expected_target_changed"),
                   SHIPPED[branch][2]))
        if SPEC_OUTCOME_TO_GUARD.get(spec_branches[branch]["correct_outcome"]) \
                != SHIPPED[branch][0]:
            raise SystemExit(
                "SPEC/CODE DIVERGENCE: branch %s correct_outcome %r does not "
                "match the shipped guard %r."
                % (branch, spec_branches[branch]["correct_outcome"],
                   SHIPPED[branch][0]))
    if sorted(spec.get("gates", [])) != sorted(GATE_SET):
        raise SystemExit("SPEC/CODE DIVERGENCE: the gate register changed in "
                         "fixture_spec.json; update the evaluator and the "
                         "crosswalk table together.")
    if sorted(spec.get("branches", {})) != sorted(BRANCHES):
        raise SystemExit("SPEC/CODE DIVERGENCE: fixture_spec.json branches %s "
                         "!= harness branches %s."
                         % (sorted(spec.get("branches", {})), sorted(BRANCHES)))


def _table_rows(section):
    """Data rows (cell lists) of the markdown table(s) in *section*.

    Separator rows (``|---|---|``) are filtered out. Implemented with
    comprehensions on purpose: a statement-level ``continue`` guard with no
    failure path is the unchecked-empty shape this repo's own linter flags.
    """
    stripped = (ln.strip() for ln in section.splitlines())
    table_lines = [ln for ln in stripped if ln.startswith("|")]
    cell_rows = [[c.strip() for c in ln.strip("|").split("|")]
                 for ln in table_lines]
    return [r for r in cell_rows if r and set("".join(r)) - set("-| ")]


def check_readme_agreement():
    """S1 gate: README.md must agree with the code it documents.

    Two tables in the README restate things the code also holds:
      * the crosswalk table must match :data:`CROSSWALK_ROWS` (what
        ``--crosswalk`` prints);
      * the "who tests the tester" table must match ``MUTANTS`` and
        ``MUTANT_KILLERS`` (mutant names and their designated killer sets).
    A README that drifts from the code is a document describing a program
    that does not exist -- this turns that drift into a red selftest.
    """
    problems = []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "README.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    # -- crosswalk table vs CROSSWALK_ROWS -----------------------------------
    m = re.search(r"## Crosswalk[^\n]*\n(.*?)\n## ", text, re.S)
    if not m:
        problems.append("README.md: the crosswalk section could not be located")
    else:
        # data rows only, via comprehensions on purpose: a statement-level
        # `continue` guard with no failure path is the unchecked-empty shape
        # this repo's own linter (SFL-003) flags
        first_cells = [cells[0] for cells in _table_rows(m.group(1))
                       if cells and cells[0] != "S5 gate"]
        expected = [row[0] for row in CROSSWALK_ROWS]
        if first_cells != expected:
            problems.append(
                "README.md: crosswalk first-column %s != _print_crosswalk() "
                "rows %s -- the two displays disagree."
                % (first_cells, expected))

    # -- mutant table vs MUTANTS / MUTANT_KILLERS ----------------------------
    m = re.search(r"## Who tests the tester[^\n]*\n(.*?)\n## ", text, re.S)
    if not m:
        problems.append("README.md: the mutant table could not be located")
    else:
        seen = {}
        rows = [r for r in _table_rows(m.group(1))
                if r and r[0] != "Mutant"]  # the known header row
        for cells in rows:
            name_m = re.match(r"`([^`]+)`", cells[0]) if cells else None
            if not name_m:
                problems.append("README.md: mutant row %r does not name a "
                                "backticked mutant" % (cells[:1] or ["?"]))
                continue
            name = name_m.group(1)
            if len(cells) < 3:
                problems.append("README.md: mutant row %r has no 'killed by' "
                                "column" % name)
                continue
            killers = set(re.findall(r"`([^`]+)`", cells[-1]))
            seen[name] = killers
        if sorted(seen) != sorted(MUTANTS):
            problems.append(
                "README.md: mutant rows %s != harness MUTANTS %s."
                % (sorted(seen), sorted(MUTANTS)))
        for name, killers in seen.items():
            if name in MUTANT_KILLERS and killers != MUTANT_KILLERS[name]:
                problems.append(
                    "README.md: mutant %s 'killed by' %s != MUTANT_KILLERS %s."
                    % (name, sorted(killers), sorted(MUTANT_KILLERS[name])))
    return problems


# --------------------------------------------------------------------------- #
# Building the observation: the one-way boundary.
# --------------------------------------------------------------------------- #
def observables_for(branch):
    """branch -> Observation. The branch name dies on the return of this call."""
    f = BRANCHES[branch]
    generation = 3 if f["patch_b"] else 2
    return impl.Observation(
        current_generation=generation,
        source_version="src@%s" % ("live" if f["source_available"] else "absent"),
        source_available=f["source_available"],
        freeze_state=(FREEZE_POST_VERDICT if f["post_verdict_freeze"]
                      else FREEZE_ACTIVE if f["freeze"] else FREEZE_NONE),
        supersession_lineage=("patch-b@gen3",) if f["patch_b"] else (),
        timestamps={"observed_at": 1700000000, "t_check": 1700000000,
                    "t_act": 1700000009},
        authority_state="current_grant_bounded_to_gen%d" % generation,
        binding_tokens=("t_check", "t_act") if not f["post_verdict_freeze"]
                       else ("t_check",),
    )


def stale_view(obs):
    """The pre-event view: the world as it looked before Patch B and the
    freeze landed. Used by the M2 mutant, and available to nobody else."""
    return impl.Observation(
        current_generation=2,
        source_version=obs.source_version,
        source_available=obs.source_available,
        freeze_state=FREEZE_NONE,
        supersession_lineage=(),
        timestamps={"observed_at": 1699999990, "t_check": 1699999990,
                    "t_act": 1699999999},
        authority_state="current_grant_bounded_to_gen2",
        binding_tokens=("t_check", "t_act"),
    )


# --------------------------------------------------------------------------- #
# Channel 3, done properly (review round 2, MUST M3): the harness owns a
# stateful model of the target, its own actuator performs the attempted action
# against that model, and the probe reads the model afterwards. The probe is
# therefore NOT a function of (guard decision, attempted action): the same
# (EXECUTE, APPLY) pair lands on a target whose state was genuinely rewritten,
# and a blanket stop shows up as "the target is still at its baseline" -- read
# from the object, the way "the target is still cfg-218" was meant.
# --------------------------------------------------------------------------- #
TARGET_BASELINE_GENERATION = 1   # the target as it sits before any repair
QUEUED_REPAIR_GENERATION = 2     # the generation the queued repair moves it to


class TargetModel:
    """The harness's model of the target system. The runner cannot name it.

    No field of ``Observation`` or ``Verdict`` refers to this object, no
    profile receives it, and the runner has no vocabulary for it -- that is
    what makes a read of this model an *independent* third channel.

    Stated limit (the honesty the review demanded, kept after the rework):
    within this documentary fixture the actuator is deterministic -- an APPLY
    that reaches it always lands. What the rework buys is that channel 3 is a
    read of a state object the runner cannot name and did not write, not a
    formula over the runner's outputs; the "target unchanged" evidence for
    every blocked branch now comes from this object's state.
    """

    __slots__ = ("provisioned_generation", "actuations")

    def __init__(self):
        self.provisioned_generation = TARGET_BASELINE_GENERATION
        self.actuations = 0

    def snapshot(self):
        return (self.provisioned_generation, self.actuations)


def actuate(target, verdict):
    """The harness's actuator: perform the attempted action on the target.

    Deliberately separate from the guard. The guard rules, the actuator moves
    the target, the probe reads the target afterwards. A runner that rules
    EXECUTE but attempts nothing (the blanket-stop shape) leaves the target
    exactly as it was, and the model records exactly that.
    """
    if verdict.attempted_action == ACTION_APPLY:
        target.provisioned_generation = QUEUED_REPAIR_GENERATION
        target.actuations += 1


def probe_target_state(target_before, target_after):
    """Channel 3: read the target model, never the runner's beliefs.

    Takes the pre-run and post-run snapshots of :class:`TargetModel` -- not
    the guard decision, not the attempted action. What changed in the target
    is whatever the actuator did to it; what the runner believes about its
    own success is never consulted.
    """
    return target_before != target_after


def _mutated_obs(branch, mutant, obs):
    if mutant == "M2-cache-read":
        return stale_view(obs)
    return obs


def _apply_mutant(mutant, obs, verdict):
    if mutant == "M1-no-supersession":
        if obs.supersession_lineage:
            return impl.Verdict(GUARD_EXECUTE, ACTION_APPLY, verdict.lines,
                                "MUTANT M1: supersession outcome discarded")
    elif mutant == "M3-no-binding":
        if obs.freeze_state == FREEZE_POST_VERDICT:
            return impl.Verdict(GUARD_EXECUTE, ACTION_APPLY, verdict.lines,
                                "MUTANT M3: action-boundary binding skipped")
    elif mutant == "M4-blanket-deny":
        return impl.Verdict(GUARD_DENY, ACTION_NONE, verdict.lines,
                            "MUTANT M4: blanket deny; target left untouched")
    return verdict


def run(branch, profile="I2-complete", mutant=None):
    """One run of one branch. Returns the three-channel observation tuple.

    (exit, guard decision, attempted action, target changed) -- the target
    changed value is read from the harness's own :class:`TargetModel` after
    its actuator performed the attempted action; it is never derived from the
    verdict and never asked of the runner.
    """
    target = TargetModel()
    target_before = target.snapshot()
    obs = _mutated_obs(branch, mutant, observables_for(branch))
    exit_code, verdict = impl.run(profile, obs)
    if mutant:
        verdict = _apply_mutant(mutant, obs, verdict)
    actuate(target, verdict)
    return (exit_code, verdict.guard_decision, verdict.attempted_action,
            probe_target_state(target_before, target.snapshot()))


def _kill_matrix():
    """{mutant: {branch: observed triple}} for mutants that deviate."""
    matrix = {}
    for name in MUTANTS:
        kills = {}
        for branch in sorted(BRANCHES):
            observed = run(branch, "I2-complete", mutant=name)
            if observed[1:] != SHIPPED[branch]:
                kills[branch] = observed[1:]
        matrix[name] = kills
    return matrix


def _executable_text(src):
    """Return (code with comments, docstrings and string literals removed,
    the surviving string literals).

    Prose is allowed to say what the branches are called -- the point of the
    check is the *code*, so the docstrings, the comments and the diagnostic
    strings are removed before the scan. A leak is not a word appearing in a
    message; a leak is a branch name in a position a runner could compare
    against, compare it against.
    """
    import ast
    import io
    import tokenize

    doc_rows = set()

    def _mark_docstring(node):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc_rows.update(range(body[0].lineno, body[0].end_lineno + 1))

    _mark_docstring(ast.parse(src))
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            _mark_docstring(node)

    out = []
    literals = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            if tok.start[0] not in doc_rows:
                literals.append(tok.string.strip().strip('"').strip("'"))
            continue
        out.append(tok.string)
    return " ".join(out), literals


def _assert_no_self_report():
    """The runner must have no vocabulary for the target state at all.

    The structural half of the third observation channel: the harness owns
    the target model, its actuator is the only thing that rewrites it, and
    the probe reads the model -- the runner is never asked about the target
    and has no field in which to answer. If the runner ever grows a field or
    an attribute that speaks about the target, this fails rather than being
    quietly believed.
    """
    offenders = []
    for slot in impl.Verdict.__slots__:
        if re.search(r"target|repair|changed", slot):
            offenders.append("Verdict.%s" % slot)
    for name in dir(impl):
        if not name.startswith("_"):
            if re.search(r"(?i)target|repair_applied", name):
                offenders.append(name)
    return ["%s would let the runner speak about the target state"
            % b for b in offenders]


def _assert_blind():
    """Prove the machine that the runner could not see the branch identity.

    Three checks (the third added after review round 2, which correctly
    judged the earlier "closed by module boundaries" claim false):

      * source scan -- no branch name, and no fixture field name, survives in
        the executable text of implementation.py (comments and docstrings
        excluded);
      * contract scan -- every profile takes exactly one Observation;
      * escape scan -- the resourceful routes a module boundary does NOT
        close must be absent from the implementation's executable code:
          - a lazy ``import harness`` (or ``__import__``/``importlib`` with
            the harness name in a string literal) -- the branch table is a
            name in scope again the moment it is imported;
          - reading ``fixture_spec.json`` -- the fixture IS the branch table
            on disk;
          - ``open()`` / ``os.environ`` / ``sys.modules`` -- the generic
            machinery every one of those routes is built from.

    This is a check on the check, in the catalog's own idiom: a blind
    experiment nobody re-verified would be a story, not a result.
    """
    problems = []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "implementation.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    code, literals = _executable_text(src)
    # Resourceful escapes the boundary does not close. Word-bounded, so
    # e.g. "opened" or a docstring mention does not fire; "environ" matches
    # os.environ, "modules" matches sys.modules, "harness" matches any form
    # of importing this module by name.
    escape_tokens = ["harness", "fixture_spec", "environ", "modules", "open"]
    for token in sorted(BRANCHES) + ["patch_b", "post_verdict_freeze",
                                     "superseded_by_patch_b"] + escape_tokens:
        # Word-bounded, so the observable `supersession_lineage` is not
        # mistaken for the `supersession` branch.
        if re.search(r"(?<![A-Za-z0-9_\-])%s(?![A-Za-z0-9_\-])"
                     % re.escape(token), code):
            if token in escape_tokens:
                problems.append(
                    "blinding escape: %r appears in the executable code of "
                    "implementation.py -- a lazy import of the harness, a "
                    "fixture-file read, or an os.environ/sys.modules/open "
                    "route would reach around the module boundary, so any "
                    "use of this machinery in the artifact under test fails "
                    "the selftest" % token)
            else:
                problems.append("blinding leak: branch/fixture token %r survives in "
                                "the executable code of implementation.py -- the "
                                "runner can see the branch identity" % token)
    # A literal that *is* a branch name is the other shape of the leak; a
    # literal naming the harness or the fixture file is the dynamic-import
    # shape (__import__("harness"), importlib.import_module("harness"), ...).
    escape_strings = {"harness", "fixture_spec", "fixture_spec.json"}
    for literal in literals:
        if literal.lower() in BRANCHES:
            problems.append("blinding leak: the runner compares against the "
                            "string literal %r" % literal)
        if literal.lower() in escape_strings:
            problems.append("blinding escape: the runner holds the string "
                            "literal %r -- the dynamic-import / fixture-read "
                            "shape of reaching around the boundary" % literal)
    import inspect
    for _name, fn in impl.PROFILES.items():
        params = inspect.signature(fn).parameters
        if list(params) != ["obs"]:
            problems.append("blinding leak: profile %s takes %s; it must take "
                            "exactly one Observation" % (_name, list(params)))
    return problems


def _print_branch(branch):
    print("=== branch: %s ===" % branch)
    print("    %s" % BRANCHES[branch]["label"])
    print("    observables handed to the runner (branch identity withheld):")
    for k, v in sorted(observables_for(branch).as_record().items()):
        print("      %-22s %s" % (k, v))
    print()
    for profile in sorted(impl.PROFILES):
        exit_code, verdict = impl.run(profile, observables_for(branch))
        print("-- %s (exit %d) guard=%s attempted=%s:"
              % (profile, exit_code, verdict.guard_decision,
                 verdict.attempted_action))
        for gate, state, detail in verdict.lines:
            print("   %-3s %-28s %s" % (gate, state, detail))
        print("   -> %s" % verdict.note)
    observed = run(branch)
    print("   probe (harness, independent): guard=%s attempted=%s target=%s"
          % (observed[1], observed[2],
             "moved to generation %d" % QUEUED_REPAIR_GENERATION
             if observed[3]
             else "unchanged, still at generation %d (baseline)"
                  % TARGET_BASELINE_GENERATION))
    print()


# --------------------------------------------------------------------------- #
# Crosswalk data (S1 gate): one source for the printer and for the README
# agreement check, so the two displays cannot drift apart silently.
# --------------------------------------------------------------------------- #
CROSSWALK_ROWS = [
    ("Q1 explicit basis", "case A (SF-006 omission)", "Test B prep"),
    ("Q2 use-time recheck", "case B (temporal drift)", "Test B base Semantic TOCTOU"),
    ("Q3 source freshness", "assumption in T08-S5Q2 (out of scope there)", "Test C/D evidence"),
    ("Q4 supersession", "case B variant (state transition)",
     "Patch B supersession branch -- separate from D1: D1 changes the "
     "applicable policy/source set after the corrected strong baseline is "
     "frozen, which is a different scenario"),
    ("Q5 bounded ambiguity/scope", "extension: unknown state is not permission",
     "Test E (D3/D4/D5)"),
    ("Q6 recheck-to-act binding", "case D (act-window)", "Test B/C residual window"),
    ("positive continuity control", "case C (clean baseline)", "Test A continuity admission"),
]


def _print_crosswalk():
    print("gate crosswalk: S5 register <-> four-case matrix <-> T08 tests")
    print("-" * 66)
    for a, b, c in CROSSWALK_ROWS:
        print("  %-30s %-46s %s" % (a, b, c))
    print()
    print("product anchors (verified against AWS docs, 2026-10-01):")
    print("  Q2 structural: Step Functions passes a start-input snapshot;")
    print("      live state needs an explicit Task state (docs.aws.amazon.com"
          "/step-functions/latest/dg/concepts-input-output-filtering.html)")
    print("  Q6 abort lever only: a stop primitive exists -- StopExecution "
          "terminates a running Standard execution and is observable via "
          "EventBridge Execution Status Change. It is an ABORT lever, not a "
          "freeze: 'freeze before use' has to be layered on top of such a "
          "primitive, and freeze semantics are not a native feature.")
    print("      (docs.aws.amazon.com/step-functions/latest/apireference/"
          "API_StopExecution.html)")
    print("  Q4/Q6 binding: DynamoDB conditional writes + optimistic locking "
          "(version attribute) implement compare-before-act.")
    print("  RDS: no native change-freeze feature; enforcement is external "
          "(IAM deny on rds:RebootDBInstance / SCP), and the maintenance "
          "window does not gate user-initiated reboots. None of the above is "
          "evidence that a change freeze did not occur -- only that the "
          "levers exist.")


def selftest():
    """Assert the register, the blinding, and the mutation suite.

    ``problems`` fails the run; ``notes`` does not. The split matters: a mutant
    that happens to kill *more* branches than its designated one is not a
    defect in the suite, and folding it into the failure list would train the
    suite to accept whatever shape it happens to have.
    """
    problems = []
    notes = []

    # Specification agreement first: fail before printing anything.
    check_spec_agreement()
    # README/code agreement (S1 gate): the crosswalk and mutant tables must
    # match what this module actually holds.
    problems.extend(check_readme_agreement())

    # Blinding: the runner must not be able to see which branch it is on.
    problems.extend(_assert_blind())
    # Target state: the runner must not be able to *say* it, either.
    problems.extend(_assert_no_self_report())

    # I2 must reproduce every shipped triple, on the observable channels.
    # Channel 3 is read from the harness's TargetModel (MUST M3): for the
    # blocked branches the "target unchanged" evidence is the model still
    # sitting at its baseline generation, not a runner-supplied flag.
    for branch, expected in SHIPPED.items():
        observed = run(branch, "I2-complete")
        if observed[1:] != expected:
            problems.append("I2 %s: expected %s, got %s"
                            % (branch, expected, observed[1:]))

    # Truth-table row 4 (MUST M2): (T,T) and (T,F) share a guard decision, so
    # they must be distinguishable on the trace -- the both-reasons marker
    # present in the (T,T) trace and absent from the (T,F) trace.
    _tt, tt_verdict = impl.run("I2-complete",
                               observables_for("patch-and-freeze"))
    _tf, tf_verdict = impl.run("I2-complete", observables_for("supersession"))
    tt_text = " | ".join(d for _g, _s, d in tt_verdict.lines)
    tf_text = " | ".join(d for _g, _s, d in tf_verdict.lines)
    if "BOTH REASONS PRESENT" not in tt_text.upper():
        problems.append("patch-and-freeze: the trace must carry BOTH reasons "
                        "(supersession AND the freeze prohibition); the "
                        "both-reasons marker is missing from %r" % tt_text)
    if "freeze" not in tt_text.lower():
        problems.append("patch-and-freeze: the trace never mentions the "
                        "freeze -- the second reason is not actually recorded")
    if "BOTH REASONS PRESENT" in tf_text.upper() or "freeze" in tf_text.lower():
        problems.append("supersession: the trace carries freeze/both-reasons "
                        "material -- (T,T) and (T,F) are no longer "
                        "distinguishable on the trace")

    # Control independence (R-4): the four patch_b x freeze combinations must
    # not collapse. This is the assertion that would have failed before the
    # split, when both controls were set together on one branch.
    combos = {
        (False, False): "continuity",
        (True, False): "supersession",
        (False, True): "prohibition",
        (True, True): "patch-and-freeze",
    }
    if sorted(combos) != [(False, False), (False, True), (True, False), (True, True)]:
        raise SystemExit("the control matrix is no longer the full 2x2")
    for combo, name in combos.items():
        if combo != (BRANCHES[name]["patch_b"], BRANCHES[name]["freeze"]):
            problems.append("control %r is not carried by branch %s"
                            % (combo, name))
    ruling = {}
    for combo, name in combos.items():
        ruling[combo] = run(name, "I2-complete")[1]
    if ruling[(True, False)] == ruling[(False, True)]:
        problems.append("control coupling: patch-only and freeze-only produce "
                        "the same ruling -- the two controls are still merged")
    if ruling[(True, True)] not in (GUARD_REASSESS, GUARD_DENY):
        problems.append("control %r produced the unusable ruling %r"
                        % ((True, True), ruling[(True, True)]))

    # I0 / I1 traces: capability-absent and ineffective-control shapes.
    for branch in ("supersession", "act-window"):
        code, verdict = impl.run("I0-ordinary", observables_for(branch))
        states = [s for _g, s, _d in verdict.lines]
        if code != EXIT_PASS or verdict.attempted_action != ACTION_APPLY:
            problems.append("I0 %s: the runner must let the stale patch through"
                            % branch)
        if states.count(impl.CAPABILITY_ABSENT) != 3:
            problems.append("I0 %s: the trace must show CAPABILITY_ABSENT at "
                            "exactly Q1/Q2/Q4" % branch)
    code, verdict = impl.run("I1-defended", observables_for("supersession"))
    states = [s for _g, s, _d in verdict.lines]
    if code != EXIT_PASS or verdict.attempted_action != ACTION_APPLY:
        problems.append("I1 supersession: the defective runner must execute")
    if impl.CONTROL_EXECUTED_FAILED not in states \
            or impl.CONTROL_EXECUTED_PASS not in states:
        problems.append("I1 supersession: the trace must mix PASS and "
                        "EXECUTED_FAILED")

    # Mutation suite: every designated killer must kill, and no mutant may
    # survive anywhere (a surviving mutant means a broken runner would be
    # accepted on that branch).
    matrix = _kill_matrix()
    for name, killers in matrix.items():
        for branch in sorted(set(killers) - MUTANT_KILLERS[name]):
            notes.append("%s also killed on %s (broader than its designated "
                         "branch -- reported, not failed)"
                         % (name, branch))
        for branch in sorted(MUTANT_KILLERS[name] - set(killers)):
            problems.append("mutant %s: not killed by its designated branch %s "
                            "-- who tests the tester" % (name, branch))
    survivors = [m for m, kills in matrix.items() if not kills]
    if survivors:
        problems.append("mutation: surviving mutant(s) %s -- the suite cannot "
                        "see a broken runner on any branch" % survivors)

    print("S5-Qregister selftest v2 (blinded run + observable channels + "
          "mutation suite)")
    print("-" * 70)
    ok = "ok" if not problems else "FAILED"
    print("  blinded      : branch table held by the harness only           -> %s" % ok)
    print("  escapes      : lazy-import/fixture/env routes scanned (M4)      -> %s" % ok)
    print("  target model : channel 3 read from the harness's target object  -> %s" % ok)
    print("  row 4        : (T,T) trace carries both reasons, (T,F) does not -> %s" % ok)
    print("  README       : crosswalk + mutant tables match the code (S1)    -> %s" % ok)
    print("  controls     : patch_b x freeze independent, 2x2 covered       -> %s" % ok)
    print("  I2-complete  : shipped triples on all 6 branches                -> %s" % ok)
    print("  I0/I1        : capability-absent / ineffective-control shapes   -> %s" % ok)
    print("  mutants      : M1-M4 killed, no survivor                        -> %s" % ok)
    if problems:
        print()
        for p in problems:
            print("  FAIL %s" % p)
        print("\nSELFTEST FAILED.")
        return 1
    for n in notes:
        print("  note: %s" % n)
    print("\nSELFTEST PASSED: the runner receives observables only; the branch "
          "identity never leaves the harness; the resourceful escape routes "
          "(lazy import, fixture reads, environ/modules/open) are scanned and "
          "absent; Patch B and the freeze are decided as separate controls; "
          "row 4 carries both reasons on the trace; the target state is read "
          "from the harness's own target model rather than reported by the "
          "runner; and every mutant of the runner is killed by its crosswalk "
          "branches.")
    return 0


if __name__ == "__main__":
    sys.exit(selftest())
