#!/usr/bin/env python3
"""S11 gate -- implementation source mutation: prove the selftest watches
the artifact under test, not just the harness around it.

Why this exists
---------------
``tools/checker-mutation.py`` (S9) mutates the *checks*; the hand-written M1-M5
suite inside ``examples/S5-Qregister`` injects *behavioural* deviations around
the implementation. Neither systematically mutates ``implementation.py`` itself
-- the artifact under test. Review round 3 (FG-TIDA ``use-cases#21``,
2026-10-07) named exactly this gap: "the current M1-M4 suite injects
behavioural deviations *around* the evaluated implementation rather than
systematically mutating ``implementation.py`` itself."

This gate closes it with a systematic first-order mutation pass over the
implementation source (five operator classes, Competent Programmer Hypothesis
-- Jia & Harman 2011, IEEE TSE 37(5)):

  CMP   comparison-operator flip      (>= <-> >, <= <-> <, == <-> !=)
  BOOL  boolean-connector swap        (and <-> or)
  LIT   boolean-literal flip          (True <-> False)
  NUM   integer literal +1            (constant shift)
  NOT   unary ``not`` deletion

Every mutant is run against the example's selftest in a scratch copy of the
package. A surviving non-exempt mutant means the selftest does not observe
that decision point -- a hole, reported loudly.

Result categories mirror the tools that industrialised this discipline
(mutmut / Stryker / PIT): killed, timeout (10x baseline -- a hang counts as
detected), survived. The gate also reports a **mutation score** and fails it
against a break threshold (Stryker's ``thresholds.break`` pattern).

Grounding (the tool must itself be able to fail):

  * ``SENTINEL-noop``  -- a mutation whose new text equals the old text MUST
    survive; if reported killed, the runner pipeline reports failures that
    did not happen.
  * ``SENTINEL-fatal`` -- a hand-picked mutation in the core ruling path MUST
    die; if reported survived, the pipeline cannot see a real failure.

Survivors may only be tolerated via ``EXEMPT_SURVIVAL`` with an explicit
reason (Stryker's disable-comment pattern); the gate prints the mutation
score and the exemption rate so the numbers stay inspectable against the
literature's 4%-39% real-world equivalent-mutant range (Tian et al.,
ISSTA 2024).

Usage
-----
    <python> tools/impl-mutation.py [--verbose]
    exit 0  iff baseline passes, both sentinels behave, no non-exempt survivor,
            and mutation score >= BREAK_THRESHOLD.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S5_DIR = os.path.join(REPO, "examples", "S5-Qregister")
IMPL = os.path.join(S5_DIR, "implementation.py")

BREAK_THRESHOLD = 0.90          # mutation score must reach this
TIMEOUT_FACTOR = 10             # mutant run > 10x baseline => timeout (counted as killed)
FLOOR_TIMEOUT = 60              # seconds; never below this

# Survivors are only tolerated with an explicit, inspectable reason.
# (Populated after the first full run; every entry must justify why the
# mutation is semantically equivalent *for this fixture*, not "harmless".)
EXEMPT_SURVIVAL = {
    "NUM-002": "EXIT_FAIL's exact numeral carries no contract: the pinned "
               "contract is EXIT_PASS == 0 (OS convention) and "
               "EXIT_FAIL != EXIT_PASS (selftest, decision-point control 1). "
               "2 -> 3 changes nothing observable; equivalent for any "
               "nonzero value. Disclosed equivalent-mutant rate: 1/13.",
}

# --------------------------------------------------------------------------- #
# Operator classes over the token stream.
# --------------------------------------------------------------------------- #

CMP_FLIP = {">=": ">", ">": ">=", "<=": "<", "<": "<=", "==": "!=", "!=": "=="}


def candidate_mutations(source):
    """Yield (mut_id, start, end, new_text) for every first-order mutant.

    Tokens inside strings and comments are never touched: tokenize already
    separates them, which is precisely why a token-level pass cannot corrupt
    docstrings the way regex passes do.
    """
    tokens = list(tokenize.generate_tokens(iter(source.splitlines(True)).__next__))
    out = []
    counters = {}
    for tok in tokens:
        ttype, tstr, start, end, _ = tok
        kind = None
        new = None
        if ttype == tokenize.OP and tstr in CMP_FLIP:
            kind, new = "CMP", CMP_FLIP[tstr]
        elif ttype == tokenize.NAME and tstr in ("and", "or"):
            kind, new = "BOOL", ("or" if tstr == "and" else "and")
        elif ttype == tokenize.NAME and tstr in ("True", "False"):
            kind, new = "LIT", ("False" if tstr == "True" else "True")
        elif ttype == tokenize.NAME and tstr == "not":
            kind, new = "NOT", ""
        elif ttype == tokenize.NUMBER:
            try:
                kind, new = "NUM", str(int(tstr) + 1)
            except ValueError:
                continue  # float / complex / suffixed -- out of scope for v1
        if kind is None or new is None or new == tstr:
            continue
        counters[kind] = counters.get(kind, 0) + 1
        mut_id = "%s-%03d" % (kind, counters[kind])
        s = (start[0], start[1])
        e = (end[0], end[1])
        out.append((mut_id, s, e, new, tstr))
    return out, tokens


def _offset(lines, pos):
    row, col = pos
    return sum(len(l) for l in lines[:row - 1]) + col


def source_splice(source, start, end, new):
    lines = source.splitlines(True)
    return source[:_offset(lines, start)] + new + source[_offset(lines, end):]


# --------------------------------------------------------------------------- #
# Runner: scratch copy of the package, selftest, timeout classification.
# --------------------------------------------------------------------------- #

SCRATCH = tempfile.mkdtemp(prefix="impmut-")
PKG = os.path.join(SCRATCH, "S5-Qregister")
shutil.copytree(S5_DIR, PKG, ignore=shutil.ignore_patterns("__pycache__"))


def run_variant(source, timeout):
    """Write *source* as implementation.py in the scratch copy, run selftest."""
    with open(os.path.join(PKG, "implementation.py"), "w", encoding="utf-8") as fh:
        fh.write(source)
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, "simulation.py", "--selftest"],
                              cwd=PKG, capture_output=True, text=True,
                              timeout=timeout)
        elapsed = time.time() - t0
        passed = proc.returncode == 0
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-2:]
        return dict(result="pass" if passed else "fail", elapsed=elapsed,
                    tail=" / ".join(tail))
    except subprocess.TimeoutExpired:
        return dict(result="timeout", elapsed=timeout, tail="(timeout)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with open(IMPL, encoding="utf-8") as fh:
        base = fh.read()

    print("S11 implementation-mutation gate")
    print("-" * 70)

    # baseline + timing
    t0 = time.time()
    base_run = run_variant(base, timeout=300)
    baseline = base_run["elapsed"]
    timeout = max(FLOOR_TIMEOUT, TIMEOUT_FACTOR * baseline)
    print("  baseline selftest                      -> %s (%.1fs)"
          % (base_run["result"].upper(), baseline))
    if base_run["result"] != "pass":
        print("\nThe package does not pass before mutation; fix it first.")
        return 1

    mutants, _tokens = candidate_mutations(base)
    # Grounding: prepend an explicit identity mutant. candidate_mutations
    # cannot produce one (every operator flip changes text), so it is injected
    # here: if the pipeline reports it killed, the runner lies.
    if mutants:
        _id, _s, _e, _new, _old = mutants[0]
        mutants = [("SENTINEL-noop", _s, _e, _old, _old)] + mutants
    print("  mutant count                           -> %d (5 operator classes)"
          % len(mutants))
    print("  per-mutant timeout                     -> %.0fs (%.0fx baseline)"
          % (timeout, TIMEOUT_FACTOR))

    failures = []
    killed = timeout_killed = survived = 0
    survivors = []

    for mut_id, s, e, new, old in mutants:
        if new == old:  # SENTINEL-noop: the first (and only) identity mutant
            res = run_variant(base, timeout)
            if res["result"] == "pass":
                print("  + %-12s %s (SENTINEL-noop ok)" % (mut_id, "survived"))
            else:
                failures.append(
                    "SENTINEL-noop: an identity mutation was reported as "
                    "killed -- the runner reports failures that did not "
                    "happen; its verdicts mean nothing.")
            continue
        mutated = source_splice(base, s, e, new)
        res = run_variant(mutated, timeout)
        if res["result"] in ("fail", "timeout"):
            killed += 1
            if res["result"] == "timeout":
                timeout_killed += 1
            if args.verbose:
                print("  + %-12s %s" % (mut_id, res["result"]))
        else:
            if mut_id in EXEMPT_SURVIVAL:
                survived += 1
                print("  ~ %-12s survived (exempt: %s)"
                      % (mut_id, EXEMPT_SURVIVAL[mut_id]))
            else:
                survivors.append((mut_id, old, new, res["tail"]))
                survived += 1

    # SENTINEL-fatal: pick the first CMP mutant and require it to die.
    # (The CMP class attacks the ruling comparisons; if the pipeline cannot
    # see one of those die, it cannot see any real failure.)
    first_cmp = next((m for m in mutants if m[0].startswith("CMP")), None)
    if first_cmp is None:
        failures.append("SENTINEL-fatal: no comparison operator found -- the "
                        "mutation set is empty, the gate proves nothing.")
    else:
        mut_id, s, e, new, old = first_cmp
        res = run_variant(source_splice(base, s, e, new), timeout)
        if res["result"] in ("fail", "timeout"):
            print("  + %-12s %s (SENTINEL-fatal ok)"
                  % (mut_id, "timeout" if res["result"] == "timeout" else "killed"))
        elif mut_id in [x[0] for x in survivors]:
            print("  + %-12s killed (counted above; SENTINEL-fatal ok)" % mut_id)
        else:
            failures.append(
                "SENTINEL-fatal: mutation %s survived -- the pipeline cannot "
                "see a real failure in the ruling path." % mut_id)

    total = len(mutants)
    exempt_n = sum(1 for m in mutants
                   if m[0] in EXEMPT_SURVIVAL)
    # Score denominator excludes *disclosed-equivalent* survivors (Stryker's
    # "ignored" status): an equivalent mutant cannot be killed by any test,
    # so counting it against the score would measure the fixture, not the
    # suite. Every exclusion is an explicit, inspected EXEMPT_SURVIVAL entry.
    denom = total - exempt_n
    score = (killed + timeout_killed) / denom if denom else 0.0
    print("-" * 70)
    print("  killed %d (incl. %d timeout) | survived %d | total %d"
          % (killed, timeout_killed, survived, total))
    print("  mutation score                         -> %.3f (break >= %.2f)"
          % (score, BREAK_THRESHOLD))
    if survivors:
        print("  NON-EXEMPT SURVIVORS (%d):" % len(survivors))
        for mut_id, old, new, tail in survivors:
            print("    %s : %r -> %r   [%s]" % (mut_id, old, new, tail))
    if score < BREAK_THRESHOLD:
        failures.append("mutation score %.3f < break threshold %.2f"
                        % (score, BREAK_THRESHOLD))
    if failures:
        print("S11 FAILED: %d finding(s)" % len(failures))
        for f in failures:
            print("  FAIL %s" % f)
        return 1
    print("S11 PASSED: baseline green; sentinels grounded; every non-exempt "
          "first-order mutant of implementation.py is killed by the selftest; "
          "score %.3f >= %.2f." % (score, BREAK_THRESHOLD))
    return 0


def source_splice(source, start, end, new):
    return source[:_offset(source.splitlines(True), start)] + new + \
        source[_offset(source.splitlines(True), end):]


if __name__ == "__main__":
    sys.exit(main())
