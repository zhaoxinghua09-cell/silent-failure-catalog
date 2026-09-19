#!/usr/bin/env python3
"""gate-lint — find silent-pass patterns in a gate, validator, or audit script.

A gate that cannot fail is not a gate. This linter looks for the specific code
shapes that make a check incapable of reporting a problem, drawn from the
Silent Failure Catalog (see ../failures/).

    python gate-lint.py path/to/your_gate.py
    python gate-lint.py --explain path/to/your_gate.py
    python gate-lint.py --tree .            # also check for negative-control samples
    python gate-lint.py --selftest          # prove this linter itself works

Stdlib only. Python 3.9+.

Honesty notes, because a linter for silent passes has an obvious obligation not
to be one itself:

* Every rule declares its confidence and its known false positives. Run
  ``--explain`` to see them.
* Every rule ships a sample pair under ``samples/`` (one file it must flag, one
  it must not). ``--selftest`` runs both. A rule whose samples do not behave is
  reported as a failure of the linter, not of the sample.
* These are heuristics on source text, not proofs. A clean run means "no known
  silent-pass shape found"; it does not mean "this gate works". The only proof
  of that is a negative control: break the guarded thing and watch it fail.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

# --------------------------------------------------------------------------- #
# Rule registry
# --------------------------------------------------------------------------- #

RULES: "dict[str, dict]" = {}

SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def rule(rid, title, severity, confidence, summary, fix, false_positives):
    def deco(fn):
        RULES[rid] = {
            "id": rid,
            "title": title,
            "severity": severity,
            "confidence": confidence,
            "summary": summary,
            "fix": fix,
            "false_positives": false_positives,
            "fn": fn,
        }
        return fn

    return deco


class Finding:
    __slots__ = ("rid", "lineno", "detail")

    def __init__(self, rid, lineno, detail):
        self.rid = rid
        self.lineno = lineno
        self.detail = detail

    def as_dict(self):
        meta = RULES.get(self.rid, {})
        return {
            "rule": self.rid,
            "title": meta.get("title", ""),
            "severity": meta.get("severity", "low"),
            "confidence": meta.get("confidence", "low"),
            "line": self.lineno,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- #
# AST helpers
# --------------------------------------------------------------------------- #

SCRIPT_NAME_RE = re.compile(r"(gate|check|valid|audit|verify|lint|scan|doctor)", re.I)
SCRIPT_HINT_RE = re.compile(r"__main__")

# Scope filter for SFL-003 — see the rule's false-positives note.
FUNC_SCOPE_RE = re.compile(
    r"(check|audit|valid|verify|gate|main|run|inspect|scan|ensure|assert)", re.I
)

COUNTER_NAME_RE = re.compile(
    r"^(fail|errors?|problems?|violations?|missing|issues?|bad)\w*$", re.I
)

RECORD_CALL_RE = re.compile(
    r"(record|append|fail|error|count|incr|log|warn|mark|add)", re.I
)

EXIT_FUNC_NAMES = {"exit", "quit", "_exit"}

def _has_collection_guard(tree) -> bool:
    """Is there a *guard construct* over a collection line, not merely a mention?

    Text search is not enough: a docstring that says "without checking that it
    collected anything" contains the word and is not a guard. gate-lint's own
    selftest caught exactly that false negative, which is why this rule looks at
    comparison nodes rather than at raw source. See CHANGELOG 0.1.0.
    """
    guard_strings = GUARD_RE

    for n in ast.walk(tree):
        # `if "collected" not in output:` / `if count == 0:` style comparisons
        if isinstance(n, ast.Compare):
            for side in [n.left] + list(n.comparators):
                for sub in ast.walk(side):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        if guard_strings.search(sub.value):
                            return True
        # `re.search(r"collected", output)` / `re.match(...)`
        if isinstance(n, ast.Call) and _func_name(n) in ("search", "match", "findall", "finditer"):
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    if guard_strings.search(a.value):
                        return True
        # a strict flag handed to the runner is a runner-level guard
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if n.value in ("--strict-markers", "--strict", "-p no:cacheprovider"):
                return True
    return False


RUNNER_RE = re.compile(r"\b(pytest|unittest|nose|jest|vitest|mocha|cargo\s+test|go\s+test)\b")
GUARD_RE = re.compile(
    r"collected|no tests ran|min_?tests?|strict[-_]markers|min_?collected", re.I
)


NEG_CONTROL_RE = re.compile(
    r"(negative|mutant|mutation|broken|regression|golden|bad|fail_?case)", re.I
)

# Inline suppression. This is documented in SFL-001's false-positives note, so it
# has to actually exist — a documented safeguard that was never implemented is
# itself an instance of the failure this project catalogues.
IGNORE_RE = re.compile(r"#\s*gate-lint:\s*ignore\s+(SFL-\d{3})", re.I)


def _inline_ignores(src):
    """Collect suppressed rule ids from real comments only.

    A plain text scan is wrong here, and self-evidently so: gate-lint's own
    docstrings quote the directive while *documenting* it, which would suppress
    the rule across the whole file — the linter would then never check itself for
    that rule. So the directive is honoured only inside a `tokenize.COMMENT`
    token. If the source cannot be tokenised, suppressions are ignored rather
    than guessed: failing toward "checked" is the only safe direction.

    Returns (ids, parsed_ok).
    """
    allowed = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                for m in IGNORE_RE.finditer(tok.string):
                    allowed.add(m.group(1).upper())
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return [], False
    return sorted(allowed), True


def _apply_suppressions(findings, src):
    """Drop findings whose rule id is suppressed inline. Returns (kept, allowed)."""
    allowed, _ok = _inline_ignores(src)
    if not allowed:
        return findings, []
    kept = [f for f in findings if f.rid.upper() not in allowed]
    return kept, allowed


def _enclosing_func_name(node) -> str:
    """Name of the innermost enclosing function, or '' at module level."""
    parents = getattr(node, "_parents", None) or {}
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur.name
        cur = parents.get(cur)
    return ""


def _names(node) -> "set[str]":
    """All Name ids appearing anywhere under *node*."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
    return out


def _is_zeroish(node) -> bool:
    """True if the node is a literal that cannot express 'failure'."""
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return node.value in (0, None, False, "", "0")
    if isinstance(node, ast.Name):
        return node.id in ("None", "False")
    return False


def _func_name(node) -> str:
    f = getattr(node, "func", None)
    if f is None:
        return ""
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _looks_like_script(src: str, path: Path) -> bool:
    if SCRIPT_NAME_RE.search(path.stem):
        return True
    if SCRIPT_HINT_RE.search(src):
        return True
    # a bare top-level call (e.g. `main()`) is a strong script signal
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for st in tree.body:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            return True
    return False


def _has_failure_path(tree) -> bool:
    """Any construct that can plausibly produce a non-zero exit."""
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assert, ast.Raise)):
            if isinstance(n, ast.Raise) and n.exc is None:
                continue  # bare `raise` re-raise
            return True
        if isinstance(n, ast.Call) and _func_name(n) in EXIT_FUNC_NAMES:
            arg = n.args[0] if n.args else None
            if not _is_zeroish(arg):
                return True
    return False


def _silent_body_kinds(body) -> "list[str]":
    """Describe a handler body **if every statement discards the failure**.

    Returns [] as soon as any statement does something other than discard —
    including recording the failure. The first version of this function only
    accumulated "silent" kinds and returned them if non-empty, so `store.add(...)`
    followed by `continue` was reported as "only does: continue". The docstring
    said "every statement"; the code did not enforce it. Found by running
    gate-lint on its own source, which is the only way that class of defect shows
    up. See CHANGELOG 0.1.0.
    """
    kinds = []
    for st in body:
        if isinstance(st, ast.Pass):
            kinds.append("pass")
        elif isinstance(st, ast.Continue):
            kinds.append("continue")
        elif isinstance(st, ast.Break):
            kinds.append("break")
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            kinds.append("no-op expression")
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            name = _func_name(st.value)
            if RECORD_CALL_RE.search(name):
                return []          # this statement records the failure → not silent
            kinds.append("call '%s' with no counter" % (name or "?"))
        else:
            return []              # something else happens here → not silent
    return kinds


def _is_emptiness_test(test) -> "str | None":
    """Recognise `if not x:`, `if len(x) == 0:`, `if x == 0:`."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return "not <expr>"
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, op, right = test.left, test.ops[0], test.comparators[0]
        if isinstance(op, ast.Eq):
            if isinstance(left, ast.Constant) and left.value in (0, "", None):
                return "<expr> == empty"
            if isinstance(right, ast.Constant) and right.value in (0, "", None):
                return "<expr> == empty"
            if isinstance(left, ast.Call) and _func_name(left) == "len":
                return "len(<expr>) == 0"
    return None


def _body_has_failure(body) -> bool:
    """Does this branch contain anything that signals failure to the caller?

    A `return` carrying a non-zeroish value counts: `return 1` is a failure
    signal. `return 0` / `return None` / `return []`-style no-op exits do not —
    those are the shapes the rule exists to catch. Known false negative: a
    helper that returns an empty finding list (`return []`) to mean "nothing to
    report" is treated as a failure path, because that is usually true of a
    checker and the alternative is unacceptable noise.
    """
    for n in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(n, (ast.Raise, ast.Assert)):
            return True
        if isinstance(n, ast.Return) and n.value is not None and not _is_zeroish(n.value):
            return True
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            if COUNTER_NAME_RE.match(n.target.id):
                return True
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and COUNTER_NAME_RE.match(t.id):
                    return True
        if isinstance(n, ast.Call):
            name = _func_name(n)
            if name in EXIT_FUNC_NAMES:
                return True
            if RECORD_CALL_RE.search(name):
                return True
    return False


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


@rule(
    "SFL-001",
    "no-nonzero-exit",
    "high",
    "high",
    "No construct in this file can produce a non-zero exit.",
    "Add an explicit failure path and make it reachable: "
    "`raise SystemExit(msg)` or `sys.exit(1)` driven by a recorded failure count. "
    "See failures/SF-005-neutral-marker-not-counted.md.",
    "Library modules legitimately never exit. This rule only applies to files that look "
    "like scripts (name matches gate/check/validate/audit/verify, a __main__ guard, or a "
    "bare top-level call). A script that delegates its exit code to a caller will also "
    "trigger it — add `# gate-lint: ignore SFL-001` with a reason if so.",
)
def r001(tree, src, path):
    if not _looks_like_script(src, path):
        return []
    if _has_failure_path(tree):
        return []
    return [Finding("SFL-001", 0, "cannot fail: no exit()/raise/assert anywhere in this file")]


@rule(
    "SFL-002",
    "swallow-exception",
    "high",
    "high",
    "An `except` block discards the exception, deleting the failure signal.",
    "Re-raise, or record a counted failure: `problems.append((item, repr(e)))` and let "
    "the count drive the exit code. Never leave a handler that only `pass`es. "
    "See failures/SF-003-swallowed-exception.md.",
    "Handlers whose only statement is a log call are flagged as medium-confidence; a "
    "deliberate best-effort cleanup that is genuinely not a verification may be safe to "
    "ignore, but say so in a comment.",
)
def r002(tree, src, path):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler):
            kinds = _silent_body_kinds(n.body)
            if kinds:
                out.append(
                    Finding("SFL-002", n.lineno,
                            "except block only does: %s" % ", ".join(sorted(set(kinds))))
                )
    return out


@rule(
    "SFL-003",
    "unchecked-empty",
    "low",
    "low",
    "An emptiness test (`if not x:`) whose branch has no failure path — an empty "
    "result may be treated as success.",
    "Treat absence as failure for anything required: "
    "`if not items: raise SystemExit(\"0 items collected — refusing to report success\")`. "
    "See failures/SF-001-zero-items-pass.md and SF-007-empty-value-is-silent.md.",
    "The noisiest rule here, and the severity/confidence are set to say so. On a "
    "two-file survey of ordinary tooling it produced three findings and no true "
    "positives, which is why it is `low` rather than `medium`: it no longer affects the "
    "exit code unless you pass --strict. It is scoped to module level and to functions "
    "whose names suggest checking (check/audit/validate/verify/gate/main/run/inspect/"
    "scan/ensure/assert); ordinary 'nothing to do' guards elsewhere are skipped, and so "
    "are genuine cases inside helpers with other names. gate-lint cannot tell 'nothing "
    "to do' from 'the thing that should exist is missing' — that judgement is the whole "
    "point of the entry.",
)
def r003(tree, src, path):
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.If):
            continue
        shape = _is_emptiness_test(n.test)
        if not shape:
            continue
        if _body_has_failure(n.body):
            continue
        fn = _enclosing_func_name(n)
        if fn and not FUNC_SCOPE_RE.search(fn):
            continue
        out.append(
            Finding("SFL-003", n.lineno,
                    "%s branch in %s() has no failure path — empty/false is treated as OK"
                    % (shape, fn or "<module>"))
        )
    return out


@rule(
    "SFL-004",
    "counter-does-not-gate-exit",
    "medium",
    "medium",
    "A failure counter is maintained but never influences the exit code.",
    "Make the exit code a function of the counter: "
    "`raise SystemExit(1 if failures else 0)`. A counter that only gets printed is "
    "decoration. See failures/SF-005-neutral-marker-not-counted.md.",
    "Counters used inside a helper function whose return value the caller checks. "
    "gate-lint is file-local and cannot follow the value across modules.",
)
def r004(tree, src, path):
    counters = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            if COUNTER_NAME_RE.match(n.target.id):
                counters.add(n.target.id)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and COUNTER_NAME_RE.match(t.id):
                    counters.add(t.id)
    if not counters:
        return []

    gating = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            gating |= _names(n.test)
        elif isinstance(n, ast.IfExp):
            gating |= _names(n.body) | _names(n.orelse)
        elif isinstance(n, ast.Call) and _func_name(n) in EXIT_FUNC_NAMES:
            for a in n.args:
                gating |= _names(a)
        elif isinstance(n, ast.Raise) and n.exc is not None:
            gating |= _names(n.exc)

    unused = sorted(counters - gating)
    if not unused:
        return []
    return [
        Finding("SFL-004", 0,
                "counter(s) never influence the exit code: %s" % ", ".join(unused))
    ]


@rule(
    "SFL-005",
    "zero-item-pass",
    "medium",
    "medium",
    "A test runner is invoked but nothing guards against '0 items collected'.",
    "Assert a non-empty collection before trusting the result: "
    "check the runner output for a collection line, or run with a strict flag and "
    "grep for `collected [1-9]`. See failures/SF-001-zero-items-pass.md.",
    "A wrapper that legitimately delegates the count check to CI, or that always runs a "
    "fixed, non-empty target set. The rule requires a guard *construct* — a comparison or "
    "pattern match over the runner's output. A docstring that merely mentions the word "
    "'collected' does not count; gate-lint's own selftest caught exactly that false "
    "negative during development.",
)
def r005(tree, src, path):
    if not RUNNER_RE.search(src):
        return []
    if _has_collection_guard(tree):
        return []
    return [
        Finding("SFL-005", 0,
                "invokes a test runner but never guards against '0 items collected'")
    ]


def check_negative_control(root: "Path | None") -> "list[Finding]":
    """Tree-level: is there anything here that could prove a check can fail?"""
    if root is None or not root.is_dir():
        return []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = p.name
        if rel.startswith(".") or "/.git/" in rel or rel.startswith(".git/"):
            continue
        if NEG_CONTROL_RE.search(rel):
            return []
    return [
        Finding("SFL-006", 0,
                "no negative-control sample found under %s — nothing here demonstrates "
                "that any check in this tree is capable of failing" % root)
    ]


RULES["SFL-006"] = {
    "id": "SFL-006",
    "title": "no-negative-control",
    "severity": "low",
    "confidence": "low",
    "summary": "Nothing in this tree could prove that a check is able to fail.",
    "fix": "Add the input that must make each check fail and run it: break the guarded "
           "thing, confirm the check notices, restore. Keep the sample in the repo so it "
           "is re-run. See ../docs/taxonomy.md, Rule 2.",
    "false_positives": "The sample may live outside this tree, or be named something "
                       "gate-lint does not recognise. This is a low-confidence nudge, not "
                       "a verdict.",
    "fn": None,
}

# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def lint_source(src: str, path: Path, tree_root: "Path | None"):
    findings = []
    try:
        parsed = ast.parse(src)
    except SyntaxError as e:
        return [Finding("PARSE", e.lineno or 0, "could not parse: %s" % e.msg)], []
    # parent map, used by rules that need to know where they are
    parents = {}
    for parent in ast.walk(parsed):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in ast.walk(parsed):
        node._parents = parents
    for meta in RULES.values():
        if meta["fn"] is None:
            continue
        findings.extend(meta["fn"](parsed, src, path))
    tree_findings = []
    if tree_root is not None:
        tree_findings = check_negative_control(tree_root)
    return findings, tree_findings


def iter_targets(targets, skipped=None):
    """Yield Python files to lint.

    Files under a ``samples/`` directory are skipped when walking a directory —
    they are intentional bad/good fixtures and linting them is meaningless. The
    skip is counted and reported rather than silent, because an unreported skip
    is precisely the failure mode this tool exists to find.
    """
    for t in targets:
        p = Path(t)
        if p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if ".git" in f.parts or "__pycache__" in f.parts:
                    continue
                if "samples" in f.parts:
                    if skipped is not None:
                        skipped.append(f)
                    continue
                yield f
        elif p.is_file():
            yield p


def print_findings(path, findings, explain: bool):
    print(path)
    for f in sorted(findings, key=lambda x: (SEV_ORDER[RULES[x.rid]["severity"]], x.lineno)):
        meta = RULES[f.rid]
        print("  %s %-8s %-28s %s" % (SEV_ICON[meta["severity"]], f.rid, meta["title"], f.detail))
        if explain:
            print("      fix: %s" % meta["fix"])
            print("      known false positives: %s" % meta["false_positives"])
            print("      confidence: %s" % meta["confidence"])
    print()


def cmd_selftest() -> int:
    here = Path(__file__).resolve().parent
    samples = here / "samples"
    repo_root = here.parent

    expect = {
        "bad/no_exit.py": {"SFL-001"},
        "bad/swallow.py": {"SFL-002"},
        "bad/unchecked_empty.py": {"SFL-003"},
        "bad/counter_unused.py": {"SFL-004"},
        "bad/zero_items.py": {"SFL-005"},
    }
    clean = ["good/strict_gate.py"]

    failed = 0
    print("gate-lint selftest")
    print("------------------")

    for rel, want in expect.items():
        p = samples / rel
        if not p.is_file():
            print("  🔴 missing sample: %s" % rel)
            failed += 1
            continue
        src = p.read_text(encoding="utf-8")
        found, _ = lint_source(src, p, repo_root)
        got = {f.rid for f in found}
        missing = want - got
        if missing:
            print("  🔴 %-26s expected %s, got %s" % (rel, sorted(want), sorted(got)))
            failed += 1
        else:
            print("  ✅ %-26s fires %s" % (rel, ", ".join(sorted(want))))

    for rel in clean:
        p = samples / rel
        if not p.is_file():
            print("  🔴 missing sample: %s" % rel)
            failed += 1
            continue
        src = p.read_text(encoding="utf-8")
        found, tree_findings = lint_source(src, p, repo_root)
        noisy = [f.rid for f in found] + [f.rid for f in tree_findings]
        if noisy:
            print("  🔴 %-26s should be clean, got %s" % (rel, sorted(set(noisy))))
            failed += 1
        else:
            print("  ✅ %-26s clean" % rel)

    print()
    if failed:
        print("SELFTEST FAILED: %d check(s) failed. A rule whose samples do not behave is "
              "broken — see CONTRIBUTING.md." % failed)
        return 1
    print("SELFTEST PASSED: every rule fires on its bad sample and stays quiet on its good "
          "sample.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gate-lint",
        description="Find silent-pass patterns in a gate, validator, or audit script.",
    )
    ap.add_argument("targets", nargs="*", help="files or directories to lint")
    ap.add_argument("--explain", action="store_true", help="show fix and false positives")
    ap.add_argument("--selftest", action="store_true", help="verify the rules against bundled samples")
    ap.add_argument("--tree", default=".", help="directory to scan for negative-control samples (default: .)")
    ap.add_argument("--no-tree", action="store_true", help="skip the SFL-006 tree scan")
    ap.add_argument("--strict", action="store_true", help="also fail on low-severity findings")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.selftest:
        return cmd_selftest()

    raw_targets = args.targets or ["."]

    # A path that does not exist is a failure, not a no-op. Silently returning 0
    # for a missing target is the exact behaviour this tool exists to find
    # (SF-006: undeclared means unchecked), so it must not do it itself.
    absent = [t for t in raw_targets if not Path(t).exists()]
    if absent:
        for t in absent:
            print("gate-lint: FAIL — target does not exist: %s" % t)
        print("gate-lint: refusing to report success for a target that was not found.")
        return 1

    skipped = []
    targets = list(iter_targets(raw_targets, skipped=skipped))
    tree_root = None if args.no_tree else Path(args.tree)

    if not targets:
        print("gate-lint: no Python files found in %s" % (raw_targets,))
        if skipped:
            print("gate-lint: %d file(s) skipped under samples/ (intentional fixtures)" % len(skipped))
        print("gate-lint: FAIL — nothing was linted, so nothing is verified.")
        return 1

    high = medium = low = 0
    results = {}
    tree_findings = []
    suppressions = []
    unreadable = []
    for p in targets:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            # counted, not swallowed — an unlinted file is an unverified file
            unreadable.append("%s (%s)" % (p, e))
            continue
        found, tf = lint_source(src, p, tree_root)
        found, allowed = _apply_suppressions(found, src)
        if allowed:
            suppressions.append("%s → %s" % (p, ", ".join(allowed)))
        results[str(p)] = found
        tree_findings = tf  # same tree for every file; report once
        for f in found:
            sev = RULES[f.rid]["severity"]
            high += sev == "high"
            medium += sev == "medium"
            low += sev == "low"

    # Tree-level findings must enter the counters too. The first version of this
    # function reported them but never counted them, so `--strict` exited 0 while
    # printing a finding — a silent pass in the linter itself. Found by running the
    # strict path in the reverse-control suite. See CHANGELOG 0.1.0.
    for f in tree_findings:
        sev = RULES[f.rid]["severity"]
        high += sev == "high"
        medium += sev == "medium"
        low += sev == "low"

    if args.json:
        print(json.dumps(
            {
                "files": {k: [f.as_dict() for f in v] for k, v in results.items()},
                "tree": [f.as_dict() for f in tree_findings],
                "counts": {"high": high, "medium": medium, "low": low},
            },
            indent=2, ensure_ascii=False,
        ))
    else:
        for path, found in results.items():
            if found:
                print_findings(path, found, args.explain)
        if tree_findings:
            for f in tree_findings:
                meta = RULES[f.rid]
                print("  %s %-8s %-28s %s" % (SEV_ICON[meta["severity"]], f.rid, meta["title"], f.detail))
            print()
        total = high + medium + low
        if total == 0:
            print("No silent-pass patterns found. Note: this means 'no known shape found', "
                  "not 'this gate works'. Only a negative control proves that.")
        else:
            print("%d finding(s): %d high, %d medium, %d low." % (total, high, medium, low))
            if low and not args.strict:
                # Not silent: say plainly that low-severity findings did NOT affect
                # the exit code. A downgrade the reader cannot see is the failure
                # this project documents.
                print("%d low-severity finding(s) did NOT affect the exit code. "
                      "Pass --strict to make them fail." % low)
            if not args.explain:
                print("Run with --explain for the fix and the known false positives.")
        if skipped:
            print("note: %d file(s) under samples/ skipped (intentional fixtures). "
                  "Reported rather than silent." % len(skipped))
        if suppressions:
            print("note: %d file(s) with inline suppressions (reported, not silent):" % len(suppressions))
            for s in suppressions:
                print("   %s" % s)
        if unreadable:
            print("note: %d file(s) could not be read and were therefore not linted:" % len(unreadable))
            for u in unreadable:
                print("   %s" % u)

    if unreadable:
        # an unlinted file is an unverified file
        return 1
    if high or medium:
        return 1
    if args.strict and low:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
