#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Negative controls for tools/impl-mutation.py (S11).

Why this file exists
--------------------
On 2026-10-08, T-n-Nelson reported in FG-TIDA use-cases#21 that the gate could
pass while holding a live, non-exempt survivor, and that its score double-
counted timeouts. Both were true. A fix that is only "the good case still
passes" is not evidence -- the good case passed before the fix too.

So this suite does the opposite: it **breaks the world in specific, named ways**
and asserts the gate **fails**. Each arm below is a mutation of the *evidence*,
not of the code under test: `run_variant` is replaced with a stub that reports a
chosen verdict for a chosen mutant, and everything else (baseline, the
bytecode-cache control, the noop sentinel) still executes for real.

An arm that cannot make the gate fail is reported INCONCLUSIVE, never PASS --
see `_arm_inconclusive`. A suite where every arm passes without ever producing
a failure is itself a decoration (I1).

Usage
-----
    python tools/impl-mutation-negctl.py            # all arms
    python tools/impl-mutation-negctl.py --list     # list arms and exit

Exit codes
----------
    0  every arm produced the failure it claims to produce
    1  at least one arm did not (gate stayed green / wrong finding)
"""

import argparse
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# `impl-mutation.py` carries a hyphen, so it cannot be imported by name.
# Loaded by path instead; its module-level scratch copy is intended.
_spec = importlib.util.spec_from_file_location(
    "impl_mutation", os.path.join(HERE, "impl-mutation.py"))
G = importlib.util.module_from_spec(_spec)
sys.modules["impl_mutation"] = G
_spec.loader.exec_module(G)

_VERDICT_FAIL = "fail"
_VERDICT_PASS = "pass"
_VERDICT_TIMEOUT = "timeout"


def _read_base():
    with io.open(G.IMPL, "r", encoding="utf-8") as fh:
        return fh.read()


def _mutant_sources(base):
    """Map exact spliced source -> mutant id, for every candidate mutation."""
    out = {}
    for mut_id, s, e, new, _old in G.candidate_mutations(base)[0]:
        out[G.source_splice(base, s, e, new)] = mut_id
    return out


class Recorder:
    """Replaces G.run_variant for the duration of one arm."""

    def __init__(self, verdicts):
        self.verdicts = verdicts or {}   # mut_id -> verdict
        self.seen = {}
        self.real_calls = 0

    def __call__(self, source, timeout, pin_mtime=None):
        # The bytecode-cache control is a real control: it must keep running
        # against the real child process, or a stubbed-out cache control would
        # falsify the arm's own premise. It is the only caller that pins mtime.
        if pin_mtime is not None:
            self.real_calls += 1
            return G.__dict__["_real_run_variant"](source, timeout, pin_mtime)
        mut_id = self.seen.get(source)
        if mut_id is None or mut_id not in self.verdicts:
            self.real_calls += 1
            return G.__dict__["_real_run_variant"](source, timeout, pin_mtime)
        result = self.verdicts[mut_id]
        return dict(result=result, elapsed=0.01, tail="(negctl stub: %s)" % result)


def _run_gate(verdicts, argv=None):
    """Run main() with a stubbed run_variant; return (rc, printed, findings)."""
    base = _read_base()
    rec = Recorder(verdicts)
    rec.seen = _mutant_sources(base)
    G.__dict__["_real_run_variant"] = G.__dict__["run_variant"]
    G.run_variant = rec
    buf = io.StringIO()
    old, oldargv = sys.stdout, sys.argv
    sys.stdout = buf
    # main() parses sys.argv itself; our own flags must not reach it.
    sys.argv = ["impl-mutation.py"]
    try:
        rc = G.main()
    except SystemExit as exc:          # argparse in main() bailed out
        rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old
        sys.argv = oldargv
        G.run_variant = G.__dict__["_real_run_variant"]
    text = buf.getvalue()
    findings = [ln.strip()[5:] for ln in text.splitlines() if ln.startswith("  FAIL ")]
    return rc, text, findings


def _arm_inconclusive(name, rc, text):
    """Gate stayed green where the arm asserts it must fail."""
    print("  [%s] %s" % ("INCONCLUSIVE" if rc == 0 else "??", name))
    if rc == 0:
        print("        gate returned 0 -- this arm never proved anything")
    return False


def _expect_fail(name, verdicts, must_mention, note):
    """Assert: gate fails (rc=1) AND at least one finding mentions `must_mention`."""
    rc, text, findings = _run_gate(verdicts)
    if rc == 0:
        return _arm_inconclusive(name, rc, text)
    hit = any(must_mention.lower() in f.lower() for f in findings)
    ok = rc == 1 and hit
    print("  [%s] %-28s rc=%d  findings=%d  matched=%s"
          % ("PASS" if ok else "FAIL", name, rc, len(findings), hit))
    if not ok:
        for f in findings:
            print("        FAIL %s" % f[:120])
        print("        expected a finding mentioning: %s" % must_mention)
    return ok


def _parse_numbers(text):
    """Pull (killed, timeout_killed, exempt_survivors, real_mutants, score)."""
    killed = tmo = exempt = real = None
    score = None
    for ln in text.splitlines():
        m = re.search(r"killed (\d+) \(incl\. (\d+) timeout\) \| "
                      r"disclosed-equivalent survivor (\d+) \| real mutants (\d+)", ln)
        if m:
            killed, tmo, exempt, real = (int(m.group(1)), int(m.group(2)),
                                         int(m.group(3)), int(m.group(4)))
        if "mutation score (equivalents excluded)" in ln:
            score = float(ln.split("->")[1].split("(")[0].strip())
    return killed, tmo, exempt, real, score


def _expect_ratio(name, verdicts, exp_killed, exp_denom, note):
    """Assert: reported kills == expected, and score == expected kills / denom.

    The expected numbers come from the arm's own scene, not from the gate's
    output -- otherwise a gate that mis-states its own denominator would be
    believed twice (once for the denominator, once for the score).

    An earlier version of this arm asserted only `score <= 1.0`. That bound is
    satisfiable by double counting behind a `min(1.0, ...)` clamp: a mutant
    test that re-introduced the timeout defect behind such a clamp left every
    arm green. A bound that only bites above 1.0 is a bound a clamp can
    silence, so the scenes here keep the score *below* 1 and check the ratio.
    """
    _rc, text, _f = _run_gate(verdicts)
    killed, tmo, _surv, _real, score = _parse_numbers(text)
    exp_score = exp_killed / exp_denom
    ok = (killed == exp_killed) and score is not None and abs(score - exp_score) <= 1e-3
    print("  [%s] %-28s killed=%s(exp %s) score=%s(exp %.4f)"
          % ("PASS" if ok else "FAIL", name, killed, exp_killed, score, exp_score))
    if not ok:
        print("        numerator or denominator is not the one the scene "
              "specified (%s)" % note)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    base = _read_base()
    muts = G.candidate_mutations(base)[0]
    ids = [m[0] for m in muts]
    non_exempt = [i for i in ids if i not in G.EXEMPT_SURVIVAL]
    cmp_ids = [i for i in ids if i.startswith("CMP")]
    exempt_ids = [i for i in ids if i in G.EXEMPT_SURVIVAL]

    arms = [
        ("NC-1 survivor must fail", "fail", None),
        ("NC-2 timeout not double counted", None, 1.0),
        ("NC-3 exempt killed => denom full", None, 1.0),
        ("NC-4 sentinel survivor must fail", "fail", None),
        ("NC-5 zero kills must fail", "fail", None),
    ]
    if args.list:
        for a in arms:
            print(a[0])
        print("mutants=%d non_exempt=%d exempt=%s cmp=%s"
              % (len(ids), len(non_exempt), exempt_ids, cmp_ids[:3]))
        return 0

    print("S11 negative controls (%d arms)" % len(arms))
    print("  mutants=%d  non-exempt=%d  exempt=%s  first CMP=%s"
          % (len(ids), len(non_exempt), exempt_ids or "-",
             cmp_ids[0] if cmp_ids else "-"))
    print("-" * 70)

    results = []

    # NC-1: one non-exempt survivor anywhere => the gate must fail on the
    # survivor itself, not merely on the score.
    if non_exempt:
        v = {i: _VERDICT_FAIL for i in ids}
        v[non_exempt[0]] = _VERDICT_PASS
        # keep enough kills that the score threshold alone would NOT fail
        results.append(_expect_fail(
            "NC-1 survivor must fail", v, "NON-EXEMPT SURVIVORS",
            "one non-exempt survivor, score still >= 0.90"))
    else:
        print("  [SKIP] NC-1 -- no non-exempt mutant available")

    # NC-2: a timeout is one kill, counted once. The scene leaves the score
    # *below* 1 on purpose -- at or above it, a `min(1.0, ...)` clamp can hide
    # a doubled numerator entirely, which is how the mutant test below got
    # through an earlier version of this arm.
    if len(non_exempt) >= 2:
        v = {i: _VERDICT_FAIL for i in ids}
        v[non_exempt[0]] = _VERDICT_PASS        # survivor (drags score down)
        v[non_exempt[1]] = _VERDICT_TIMEOUT     # one timeout kill
        if exempt_ids:
            v[exempt_ids[0]] = _VERDICT_PASS    # exempt survivor removes 1 from denom
        results.append(_expect_ratio(
            "NC-2 timeout counted once", v,
            len(non_exempt) - 1,          # kills: all but the survivor
            len(ids) - 1,                 # denom: 12 less the exempt survivor
            "one timeout, one survivor -- score must be killed/denom exactly"))
    else:
        print("  [SKIP] NC-2 -- needs two non-exempt mutants")

    # NC-3: an exemption may only shrink the denominator when its mutant really
    # survives. Here the exempt mutant is killed, so the denominator must stay
    # full; a timeout is present so a doubled numerator cannot hide behind a
    # clamp.
    if exempt_ids and len(non_exempt) >= 2:
        v = {i: _VERDICT_FAIL for i in ids}
        v[exempt_ids[0]] = _VERDICT_FAIL        # exempt mutant dies
        v[non_exempt[0]] = _VERDICT_PASS
        v[non_exempt[1]] = _VERDICT_TIMEOUT
        results.append(_expect_ratio(
            "NC-3 exempt killed", v,
            len(ids) - 1,                 # kills: all but the survivor
            len(ids),                     # denom stays full: exemption unused
            "exempt mutant killed -- denom must stay 12, score = 11/12"))
    else:
        print("  [SKIP] NC-3 -- needs an exempt and two non-exempt mutants")

    # NC-4: the fatal sentinel must not be reported "killed" while the same id
    # sits in the survivor list.
    if cmp_ids:
        v = {i: _VERDICT_FAIL for i in ids}
        v[cmp_ids[0]] = _VERDICT_PASS
        results.append(_expect_fail(
            "NC-4 sentinel survivor", v, "SENTINEL-fatal",
            "first CMP mutant survives; sentinel must contradict, not agree"))
    else:
        print("  [SKIP] NC-4 -- no CMP mutant available")

    # NC-5: a suite that kills nothing proves nothing, whatever the score says.
    v = {i: _VERDICT_PASS for i in ids}
    results.append(_expect_fail(
        "NC-5 zero kills", v, "mutation score",
        "every mutant survives; score 0.000 must fail the threshold"))

    print("-" * 70)
    not_ok = sum(1 for r in results if not r)
    print("%s  %d/%d arms passed" % ("OK" if not_ok == 0 else "FAILED",
                                     len(results) - not_ok, len(results)))
    return 1 if not_ok else 0


if __name__ == "__main__":
    sys.exit(main())
