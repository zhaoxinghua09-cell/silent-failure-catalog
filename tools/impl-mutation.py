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

# The child interpreters must not write a bytecode cache.
#
# Why: CPython validates a `.pyc` against (source mtime truncated to *whole
# seconds*, source size). Every mutant below is written back to the same path
# inside the same second, so a mutation that keeps the file size --
# `NUM-001 '0' -> '1'`, `NUM-002 '2' -> '3'`, `CMP-001 '==' -> '!='` -- leaves
# both validation fields unchanged. The child then re-executes the stale .pyc
# built from the *unmutated* source, the selftest passes, and a mutant that
# the suite does watch is scored "survived".
#
# This is not hypothetical. Measured 2026-10-08 at `fc86dc5`, on one machine
# and one interpreter: the gate reported killed 11 / 1.000 with
# PYTHONDONTWRITEBYTECODE exported, and killed 9 / 0.818 -- the reading CI
# reported on both `gates · python 3.9` and `gates · python 3.12` -- once that
# one variable was removed. The harness was silently watching a cached copy of
# the artifact instead of the artifact, which is the exact failure shape this
# repository catalogs. `PYTHONDONTWRITEBYTECODE=1` is `-B` for the subprocess:
# it stops the *writing*. It does not stop *reading* an already-valid cache, so
# the scratch tree is additionally copied with `__pycache__` ignored. Both
# halves are needed; either one alone leaves the window open.
NO_BYTECODE = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

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
            core = tstr[1:] if tstr[:1] in ("+", "-") else tstr
            if core.isdigit():
                kind, new = "NUM", str(int(tstr) + 1)
            # else: float / complex / underscore-grouped / suffixed numeric
            # literals are out of scope for v1 -- skipped explicitly here
            # rather than via an exception handler that would swallow the
            # distinction between "skipped by design" and "crashed".
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


def run_variant(source, timeout, pin_mtime=None):
    """Write *source* as implementation.py in the scratch copy, run selftest.

    ``pin_mtime`` back-dates the scratch file to a whole second. It exists so
    the bytecode-cache control below can reconstruct, deliberately, the exact
    window in which CPython would reuse a stale ``.pyc`` -- a window that the
    default writer hits by accident whenever a same-size mutant lands in the
    same second as the previous run.
    """
    # `newline=""` keeps the scratch artifact byte-identical across platforms --
    # a property this repository states elsewhere, and NOT the fix for the stale
    # cache: with the default newline both the previous and the current variant
    # are inflated the same way, so the (mtime, size) comparison still matches.
    # NO_BYTECODE stops the child from WRITING a .pyc; there is none to read,
    # because the scratch tree is copied with __pycache__ ignored. Both halves
    # are needed -- -B alone still reads an already-valid .pyc.
    path = os.path.join(PKG, "implementation.py")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(source)
    if pin_mtime is not None:
        os.utime(path, (pin_mtime, pin_mtime))
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, "simulation.py", "--selftest"],
                              cwd=PKG, capture_output=True, text=True,
                              timeout=timeout, env=NO_BYTECODE)
        elapsed = time.time() - t0
        passed = proc.returncode == 0
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-2:]
        return dict(result="pass" if passed else "fail", elapsed=elapsed,
                    tail=" / ".join(tail))
    except subprocess.TimeoutExpired:
        return dict(result="timeout", elapsed=timeout, tail="(timeout)")


def bytecode_cache_control(base, timeout):
    """Grounding: the runner must be watching the artifact, not a cached copy.

    Takes the first same-size mutant, writes it into the scratch package and
    back-dates the file to the whole second it already carries -- the exact
    state in which CPython validates a `.pyc` as current and executes the
    *unmutated* module. The mutant is one the suite watches, so the child must
    FAIL. If it passes, the runner is reading a bytecode cache and every
    "survived" verdict above it is untrustworthy.

    Measured on 2026-10-08, at commit `fc86dc5`, on one machine and one
    interpreter (CPython 3.13.12 on Windows): with PYTHONDONTWRITEBYTECODE
    exported the gate reported killed 11 / score 1.000; with that single
    variable removed -- same commit, same platform, same interpreter -- it
    reported killed 9 / score 0.818, which is the reading CI produced. The
    interpreter's bytecode cache, not the operating system, is the variable:
    with the cache enabled the child writes `implementation.cpython-*.pyc`
    into the scratch tree, and a same-size mutant written in the same whole
    second reuses it. CI does not disable the cache, so the gate was red there
    by default and looked green only in the shell it was developed in.
    Deliberately reconstructing the window makes that class a checked property
    instead of an accident of the shell.
    """
    for mut_id, s, e, new, _old in candidate_mutations(base)[0]:
        mutated = source_splice(base, s, e, new)
        if len(mutated) == len(base):
            break
    else:
        return ["bytecode-cache control: no same-size mutant available -- the "
                "control cannot reconstruct the stale-cache window"]
    sec = int(os.stat(os.path.join(PKG, "implementation.py")).st_mtime)
    res = run_variant(mutated, timeout, pin_mtime=sec)
    if res["result"] == "pass":
        return ["bytecode-cache control: a same-size mutant %s pinned to the "
                "scratch file's own whole second was reported SURVIVED -- the "
                "runner executed a stale .pyc, so it was watching a cached "
                "copy of the artifact rather than the artifact" % mut_id]
    return []


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
    print("  (count includes grounding sentinels; see 'real mutants' below)")
    print("  per-mutant timeout                     -> %.0fs (%.0fx baseline)"
          % (timeout, TIMEOUT_FACTOR))

    failures = []
    killed = timeout_killed = survived = 0
    survivors = []
    survived_ids = set()   # v1.1: ids actually observed to survive

    # Grounding, alongside SENTINEL-noop / SENTINEL-fatal: the runner must be
    # watching the artifact rather than a cached copy of it. Run first, so a
    # cached-copy runner is named instead of quietly inflating the survivor
    # list with mutants that were never actually executed.
    cache_failures = bytecode_cache_control(base, timeout)
    print("  bytecode-cache control                 -> %s"
          % ("FAILED" if cache_failures else "ok (runner sees the artifact)"))
    failures.extend(cache_failures)

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
            survived += 1
            survived_ids.add(mut_id)
            if mut_id in EXEMPT_SURVIVAL:
                print("  ~ %-12s survived (exempt: %s)"
                      % (mut_id, EXEMPT_SURVIVAL[mut_id]))
            else:
                survivors.append((mut_id, old, new, res["tail"]))

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
            # v1.1: this used to print "killed (counted above)" -- i.e. it
            # claimed the sentinel died while the same id sat in the survivor
            # list. Two contradictory readings of one mutant cannot both be
            # true, and the old branch swallowed the contradiction into a
            # success line. Reported by T-n-Nelson, use-cases#21 (2026-10-08).
            failures.append(
                "SENTINEL-fatal: mutation %s survived the main sweep yet the "
                "sentinel branch reported it killed -- the gate is printing a "
                "verdict it did not observe." % mut_id)
        else:
            failures.append(
                "SENTINEL-fatal: mutation %s survived -- the pipeline cannot "
                "see a real failure in the ruling path." % mut_id)

    # Accounting: grounding sentinels are NOT mutants. SENTINEL-noop (new ==
    # old) exists to prove the pipeline does not fabricate kills; counting it
    # in the total would inflate the denominator and misstate the score.
    noop_count = sum(1 for m in mutants if m[3] == m[4])
    real_mutants = len(mutants) - noop_count
    print("  real mutants (sentinels excluded)      -> %d (+%d grounding "
          "sentinel)" % (real_mutants, noop_count))
    # Score denominator excludes *disclosed-equivalent* survivors (Stryker's
    # "ignored" status): an equivalent mutant cannot be killed by any test,
    # so counting it against the score would measure the fixture, not the
    # suite. Every exclusion is an explicit, inspected EXEMPT_SURVIVAL entry.
    # v1.1: an exemption may only shrink the denominator when that mutant was
    # actually observed to survive. Previously any id listed in
    # EXEMPT_SURVIVAL was subtracted unconditionally, so a stale entry kept
    # shrinking the denominator (and raising the score) even when its mutant
    # was killed. Reported by T-n-Nelson, use-cases#21 (2026-10-08).
    exempt_n = sum(1 for m in mutants
                   if m[0] in EXEMPT_SURVIVAL and m[3] != m[4]
                   and m[0] in survived_ids)
    denom = real_mutants - exempt_n
    # v1.1: `killed` already counts timeout kills -- they are a subset, not a
    # second population. Adding T to K again counted every timeout twice and
    # could print a score above 1.000 (K=11, T=1, denom=11 gave 1.091).
    score = killed / denom if denom else 0.0
    print("-" * 70)
    print("  killed %d (incl. %d timeout) | disclosed-equivalent survivor %d "
          "| real mutants %d"
          % (killed, timeout_killed, survived, real_mutants))
    print("  mutation score (equivalents excluded)  -> %.3f (break >= %.2f)"
          % (score, BREAK_THRESHOLD))
    raw = killed / real_mutants if real_mutants else 0.0
    print("  raw kill ratio (all real mutants)      -> %d/%d = %.3f"
          % (killed, real_mutants, raw))
    if survivors:
        print("  NON-EXEMPT SURVIVORS (%d):" % len(survivors))
        for mut_id, old, new, tail in survivors:
            print("    %s : %r -> %r   [%s]" % (mut_id, old, new, tail))
    # v1.1: the gate's own verdict says every non-exempt mutant must be killed.
    # Printing survivors while deciding purely on the score threshold let the
    # gate pass with a live survivor in hand (e.g. K=10, T=0, denom=11 gives
    # 0.909 >= 0.90 alongside one survivor). A listed survivor is now itself a
    # failure, independently of the score. Reported by T-n-Nelson, #21.
    if survivors:
        failures.append(
            "NON-EXEMPT SURVIVORS (%d): %s -- the gate requires every "
            "non-exempt mutant to be killed; a survivor is a failure on its "
            "own, not a line of commentary."
            % (len(survivors), ", ".join(m for m, _o, _n, _t in survivors)))
    # v1.1: a kill ratio cannot exceed 1. A score above it means the numerator
    # and denominator are counted on different terms.
    if score > 1.0 + 1e-9:
        failures.append(
            "mutation score %.3f > 1.000 -- impossible for a ratio of kills to "
            "mutants; the numerator and denominator are no longer counted on "
            "the same terms." % score)
    if score < BREAK_THRESHOLD:
        failures.append("mutation score %.3f < break threshold %.2f"
                        % (score, BREAK_THRESHOLD))
    if failures:
        print("S11 FAILED: %d finding(s)" % len(failures))
        for f in failures:
            print("  FAIL %s" % f)
        return 1
    print("S11 PASSED: baseline green; sentinels grounded; non-exempt "
          "survivors 0; score %.3f >= %.2f." % (score, BREAK_THRESHOLD))
    return 0


def source_splice(source, start, end, new):
    return source[:_offset(source.splitlines(True), start)] + new + \
        source[_offset(source.splitlines(True), end):]


if __name__ == "__main__":
    sys.exit(main())
