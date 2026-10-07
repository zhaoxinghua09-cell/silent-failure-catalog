#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""defect-closure.py — gate 10: every defect has a closed loop.

Why this exists
---------------
A repository whose subject is "a check believed to be running, and not running"
has an obvious obligation: when it finds a defect in itself, the finding must be
turned into a **change to the checking**, not into a paragraph. Twice now a
defect was recorded as prose -- the eleven in `docs/building-this-catalog.md`, and
the four ITU FG-TIDA raised on the S5 example -- and prose cannot be interrogated.
No tool could ask the only questions that matter:

  * what SHAPE was this defect?          -> class (SF-nnn, docs/taxonomy.md)
  * WHY did our checking miss it?        -> escape_cause (E1..E4, below)
  * what ROOT CAUSE was changed?         -> not "where it broke" but "which gate
                                            was missing / blind / toothless"
  * what GATE now kills this class, and how was that gate shown to fire?

`docs/defect-ledger.json` records one entry per defect. This gate refuses to pass
until every entry answers all four. An open defect is a class still open.

The escape-cause taxonomy (orthogonal to the SF- classes)
---------------------------------------------------------
  E1  no gate existed at the time
  E2  a gate existed but did not cover this shape
      (a substring standing in for a structure, a first column for a table,
       a sample set that never contained the case)
  E3  a gate fired but had no landing -- printed, noted, logged, and never
      entered the exit code
  E4  a gate existed but had never been shown capable of failing -- a decorative
      gate; believed to be running, not discriminating

E4 is the family this repository keeps rediscovering: it is taxonomy Rule 2
("no negative control means no evidence") turned back on the checks themselves.
The class and the escape cause are different axes: `class` is what the defect
looks like, `escape_cause` is why our checking let it through.

This gate also answers the question the four ITU points really asked: of the
defects we have found, HOW MANY were escaped by a decorative gate rather than a
missing one? The summary line prints that distribution, because a changing mix of
E1..E4 is the only honest measure of whether "we check harder now" is true.

Usage
-----
  python tools/defect-closure.py                  # validate docs/defect-ledger.json
  python tools/defect-closure.py --ledger PATH    # an explicit ledger
  python tools/defect-closure.py --selftest       # positive + negative controls

Exit code: 0 = every defect closed; 1 = at least one is not.
"""
import argparse
import json
import os
import re
import sys

LEDGER_DEFAULT = os.path.join("docs", "defect-ledger.json")

REQUIRED_FIELDS = (
    "id", "date", "source", "symptom", "class", "escape_cause",
    "found_by", "root_cause", "gate_added", "evidence",
    "siblings_scanned", "closed",
)
NONEMPTY_FIELDS = ("symptom", "found_by", "root_cause", "gate_added", "evidence")
ALLOWED_SOURCES = ("external-review", "self-test")
ESCAPE_CAUSES = ("E1", "E2", "E3", "E4")
CLASS_RE = re.compile(r"^SF-(\d{3})$")
CLASS_MIN, CLASS_MAX = 1, 14

# A `gate_added` that names no artifact is a claim, not a gate. This pattern pulls
# the path-like tokens out of the prose so the gate can require each one to exist --
# and, if it is a tool, to be invoked by `.githooks/pre-commit`. It exists because
# on 2026-10-07 an entry (D-017) was recorded closed while the check it promised was
# not yet in the tree: the gate trusted free text. It cannot verify that a sentence
# is true, but it can refuse to accept a named gate that is not there.
GATE_ARTIFACT_RE = re.compile(
    r"(tools/[A-Za-z0-9_.\-]+\.py"
    r"|\.githooks/[A-Za-z0-9_.\-]+"
    r"|\.github/workflows/[A-Za-z0-9_.\-]+\.ya?ml"
    r"|[A-Za-z0-9_\-]+\.py)")


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_artifact(root, token):
    """Resolve a path-like token used in `gate_added`, or None if it is not there."""
    if os.path.isfile(os.path.join(root, token)):
        return os.path.join(root, token)
    if "/" not in token and os.path.isfile(os.path.join(root, "tools", token)):
        return os.path.join(root, "tools", token)
    return None


def _hook_invokes(root, path, hook_text=None):
    """True if the gate hook runs this tool. A tool no gate invokes is not wired.

    A hook that cannot be read returns the string "missing" (truthy-but-failing), so the
    caller reports it rather than passing: rule 12 -- an unrunnable check is a failed check.
    """
    if hook_text is None:
        try:
            with open(os.path.join(root, ".githooks", "pre-commit"), encoding="utf-8") as fh:
                hook_text = fh.read()
        except OSError:
            return "missing"
    return os.path.basename(path) in hook_text



def validate(ledger, root=None, hook_text=None):
    """Return a list of problems. Empty list == the ledger is fully closed."""
    root = root or _repo_root()
    problems = []
    if not isinstance(ledger, dict):
        return ["ledger: top level is not a JSON object"]

    taxonomy = ledger.get("escape_cause_taxonomy")
    if not isinstance(taxonomy, dict) or not taxonomy:
        problems.append("ledger: 'escape_cause_taxonomy' is missing -- the escape "
                        "causes must be defined, not assumed")
    else:
        for code in ESCAPE_CAUSES:
            if not str(taxonomy.get(code, "")).strip():
                problems.append("ledger: escape_cause %s is not defined in "
                                "escape_cause_taxonomy" % code)

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return problems + ["ledger: 'entries' is not a list"]
    if not entries:
        problems.append("ledger: no defect entries -- an empty defect ledger is "
                        "itself a claim that nothing was ever wrong")

    seen = {}
    for i, e in enumerate(entries):
        where = e.get("id") if isinstance(e, dict) and e.get("id") else "entries[%d]" % i
        if not isinstance(e, dict):
            problems.append("%s: entry is not an object" % where)
            continue
        for field in REQUIRED_FIELDS:
            if field not in e:
                problems.append("%s: missing required field '%s'" % (where, field))
        eid = e.get("id")
        if isinstance(eid, str):
            if eid in seen:
                problems.append("%s: duplicate id (first used by entries[%d])"
                                % (where, seen[eid]))
            seen[eid] = i

        cls = e.get("class")
        m = CLASS_RE.match(cls) if isinstance(cls, str) else None
        if not m:
            problems.append("%s: class %r is not of the form SF-nnn" % (where, cls))
        else:
            n = int(m.group(1))
            if not CLASS_MIN <= n <= CLASS_MAX:
                problems.append("%s: class %s is outside SF-%03d..SF-%03d"
                                % (where, cls, CLASS_MIN, CLASS_MAX))

        if e.get("escape_cause") not in ESCAPE_CAUSES:
            problems.append("%s: escape_cause %r is not one of %s"
                            % (where, e.get("escape_cause"), "/".join(ESCAPE_CAUSES)))
        if e.get("source") not in ALLOWED_SOURCES:
            problems.append("%s: source %r is not one of %s"
                            % (where, e.get("source"), "/".join(ALLOWED_SOURCES)))

        for field in NONEMPTY_FIELDS:
            value = e.get(field)
            if not (isinstance(value, str) and value.strip()):
                problems.append("%s: '%s' is empty -- an unclosed defect is one "
                                "that will recur" % (where, field))

        # a named gate must be real, and a named tool must be wired into the hook
        for token in sorted(set(GATE_ARTIFACT_RE.findall(e.get("gate_added") or ""))):
            path = _resolve_artifact(root, token)
            if path is None:
                problems.append("%s: gate_added names '%s', which does not exist -- "
                                "a gate that is not there is not a gate" % (where, token))
                continue
            wired = _hook_invokes(root, path, hook_text)
            if wired == "missing":
                problems.append("%s: cannot read .githooks/pre-commit to confirm '%s' is "
                                "wired -- an unrunnable check is a failed check (rule 12)"
                                % (where, token))
            elif os.path.basename(os.path.dirname(path)) == "tools" and not wired:
                problems.append("%s: gate_added names '%s', which no gate hook invokes "
                                "-- a tool that never runs checks nothing" % (where, token))

        if e.get("siblings_scanned") is not True:
            problems.append("%s: siblings_scanned is not true -- fixing the named "
                            "instance without scanning the siblings fixes the "
                            "example, not the class" % where)
        if e.get("closed") is not True:
            problems.append("%s: closed is not true -- the class is still open"
                            % where)
    return problems


def summarise(ledger):
    entries = ledger.get("entries") if isinstance(ledger, dict) else []
    by_class, by_escape = {}, {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        by_class[e.get("class")] = by_class.get(e.get("class"), 0) + 1
        by_escape[e.get("escape_cause")] = by_escape.get(e.get("escape_cause"), 0) + 1
    return by_class, by_escape


def _fmt(counts):
    if not counts:
        return "(none)"
    return "  ".join("%s x%d" % (k, counts[k]) for k in sorted(counts))


# --------------------------------------------------------------------------- #
# Self-test: the gate must be shown failing before it can be believed.
# --------------------------------------------------------------------------- #
def _entry(**over):
    base = {
        "id": "D-900", "date": "2026-10-07", "source": "self-test",
        "symptom": "s", "class": "SF-012", "escape_cause": "E4",
        "found_by": "f", "root_cause": "r", "gate_added": "g",
        "evidence": "e", "siblings_scanned": True, "closed": True,
    }
    base.update(over)
    return base


def _ledger(entries):
    return {
        "schema": "defect-ledger/1",
        "escape_cause_taxonomy": {code: "defined for the self-test"
                                  for code in ESCAPE_CAUSES},
        "entries": entries,
    }


def selftest():
    failures = []

    # -- positive control: a well-formed ledger must be accepted --------------
    good = _ledger([_entry()])
    if validate(good):
        failures.append("positive control: a valid ledger was REJECTED: %s"
                        % validate(good))
    else:
        print("  + positive control        a valid ledger is accepted")

    # -- negative controls: each must be CAUGHT, and each must bite a
    #    DIFFERENT rule (otherwise a control is redundant and some rule is
    #    unexercised -- the second-order check) ------------------------------
    negatives = (
        ("empty evidence", _ledger([_entry(evidence="")])),
        ("closed is false", _ledger([_entry(closed=False)])),
        ("class out of range", _ledger([_entry(**{"class": "SF-099"})])),
        ("unknown escape cause", _ledger([_entry(escape_cause="E9")])),
        ("blank gate_added", _ledger([_entry(gate_added="   ")])),
        ("siblings_scanned false", _ledger([_entry(siblings_scanned=False)])),
        ("duplicate id", _ledger([_entry(), _entry()])),
        ("empty ledger", _ledger([])),
        ("gate_added names a missing gate",
         _ledger([_entry(gate_added="audited by tools/does-not-exist-xyz.py")])),
    )
    first_reasons = {}
    for label, led in negatives:
        found = validate(led)
        if not found:
            failures.append("negative control (%s): NOT caught -- the gate cannot "
                            "see this shape" % label)
            continue
        reason = found[0]
        if reason in first_reasons:
            failures.append("second-order (%s): bites the same rule as (%s) -- a "
                            "control that duplicates another leaves some rule "
                            "unexercised" % (label, first_reasons[reason]))
        first_reasons[reason] = label
        print("  + %-22s caught: %s" % (label, reason.split(":", 1)[0]))

    # -- second branch of the artifact rule: a named tool that exists but no gate
    #    invokes. Fed a hook text that mentions nothing, so the tool it names is real
    #    but unwired -- without this the "must be invoked" branch would be an
    #    unexercised rule, which is the very thing this repository catalogs.
    unwired = validate(_ledger([_entry(gate_added="audited by tools/make-manifest.py")]),
                       hook_text="")
    if not unwired or "no gate hook invokes" not in unwired[0]:
        failures.append("artifact control (unwired tool): naming a real tool that no "
                        "gate runs was NOT caught")
    else:
        print("  + %-22s caught: %s" % ("unwired tool", unwired[0].split(":", 1)[0]))

    # -- third branch: the hook itself cannot be read. Rule 12 says an unrunnable check is a
    #    failed check, so this must NOT fail open (it once returned True here -- the one
    #    fail-open branch in a repository whose whole subject is fail-open branches).
    if _hook_invokes(os.path.join(_repo_root(), "no-such-dir"), "tools/x.py") != "missing":
        failures.append("artifact control (unreadable hook): an unreadable .githooks/pre-commit "
                        "did NOT report failure -- the check fails open (rule 12)")
    else:
        print("  + %-22s caught: cannot verify wiring" % "unreadable hook")

    # -- lazy sentinel: an unrelated change must NOT be mistaken for a defect --
    lazy = json.loads(json.dumps(good))
    lazy["_comment"] = "a harmless extra key"
    lazy["entries"][0]["_note"] = "another harmless extra key"
    if validate(lazy):
        failures.append("lazy sentinel: an unrelated extra key was treated as a "
                        "failure -- the gate fires on noise")

    # -- fatal sentinel: the definitive broken ledger must be caught ----------
    fatal = _ledger([_entry(closed=False, evidence="")])
    if not validate(fatal):
        failures.append("fatal sentinel: an unclosed, evidence-free defect was "
                        "accepted")

    print("")
    if failures:
        print("SELF-TEST FAILED: %d problem(s)" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("SELF-TEST PASSED: %d negative controls caught, %d distinct rules bitten, "
          "lazy sentinel survived, fatal sentinel killed"
          % (len(negatives), len(first_reasons)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=LEDGER_DEFAULT)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    try:
        with open(args.ledger, "r", encoding="utf-8") as fh:
            ledger = json.load(fh)
    except FileNotFoundError:
        print("S10 FAILED: ledger not found at %s -- a gate that cannot read its "
              "ledger is a gate that failed" % args.ledger)
        return 1
    except ValueError as exc:
        print("S10 FAILED: ledger at %s is not valid JSON: %s" % (args.ledger, exc))
        return 1

    problems = validate(ledger)
    by_class, by_escape = summarise(ledger)
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []

    print("= defect-closure (gate 10) . %s" % args.ledger)
    print("  entries        : %d" % len(entries))
    print("  by class       : %s" % _fmt(by_class))
    print("  by escape cause: %s" % _fmt(by_escape))
    print("    E1 missing gate . E2 blind gate . E3 no landing . E4 decorative gate")

    if problems:
        print("= verdict: FAILED -- %d defect(s) not closed" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("= verdict: CLOSED (%d/%d) -- every defect answers shape, escape cause, "
          "root cause, gate, evidence" % (len(entries), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
