#!/usr/bin/env python3
"""hook-deps -- the hook must be able to run with nothing but shell builtins.

Why this exists
    On 2026-11-12 this hook could not run on a Windows machine where Git was
    installed and working. It reported all eighteen gates as failed, twice, with
    two different sentences, and in neither case had a gate been executed:

        .githooks/pre-commit: line 118: dirname: command not found
        pre-commit: FAIL -- tools/gate-lint.py is missing. A gate that is not
                    there is not a gate.

    The cause was one word. `cd "$(dirname "$0")/.."` needs a coreutils binary;
    a bare MinGit shell has none, so `dirname` failed, so `cd` stayed in the
    caller's directory, so every relative path missed, so every gate "was
    missing". The reporting path had the same problem one line further on:
    `printf ... | sed 's/^/    /'` needs `sed`, and it is the line that prints
    why another gate failed.

    Both were fixed by using only builtins (`${0%/*}`, a `while read` loop). But
    "we fixed it" is not a property anything can check, and the next `sed` added
    for tidiness would restore the failure silently, on a platform CI does not
    run. This gate makes the property checkable: the hook says which gates to
    run, and this says the hook itself can be started by a shell that has
    nothing else.

What it checks
    Every word in command position in `.githooks/pre-commit` -- after removing
    whole-line comments and the contents of single- and double-quoted strings --
    must not be an external binary from the list below. The list is the set of
    POSIX utilities this repository has no reason to call from a hook, not the
    set of all binaries; `python` is not on it, because running Python is the
    hook's whole job.

What it does not check
    * Whether the hook finds a *working* Python. That was the second defect of
      the same day (the Windows Store `python3` alias, exit 49, no output). It is
      handled inside the hook by a probe, and it cannot be checked from here:
      the answer depends on the machine, not on the file.
    * Whether the hook needs a shell in the first place. It does, and the shell
      it needs is the one git itself supplies; `prepare.py --selftest` covers
      that side by requiring `sh` to *run* before it is trusted.
    * Whether the gate list is right. That is `check-gate-parity.py`.

Why a deny-list and not an allow-list
    An allow-list would have to name every builtin a future edit might use, and
    would fail on a legitimate addition for no reason a reader could act on. A
    deny-list fails only when a name that provably needs an external file is
    introduced, and the failure message can say which line, which word, and what
    to use instead -- which is the whole value of the check.

Exit status: 0 when the hook needs nothing outside the shell, 1 otherwise.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

HOOK = ".githooks/pre-commit"

# Words that are a binary, not a builtin. Each one was either measured or is the
# same shape: a coreutils/other tool that a minimal POSIX shell does not carry.
DENY = {
    "dirname", "basename", "sed", "awk", "grep", "egrep", "fgrep",
    "cut", "tr", "head", "tail", "wc", "sort", "uniq", "xargs",
    "find", "mktemp", "date", "cat", "ln", "mkdir", "rmdir", "cp", "mv",
    "rm", "chmod", "chown", "touch", "expr", "seq", "tee", "sleep",
    "diff", "stat", "du", "df", "realpath", "readlink", "which", "env",
    "tar", "gzip", "gunzip", "unzip", "curl", "wget",
}

# `dirname` and `sed` are called out because they were the two measured on
# 2026-11-12; the message for them names a builtin replacement.
INSTEAD = {
    "dirname": '`${0%/*}` -- parameter expansion finds the hook\'s own directory',
    "basename": '`${0##*/}` -- parameter expansion strips the directory',
    "sed": "a `while IFS= read -r line` loop with `printf`",
    "grep": "a `case` statement, or move the matching into a Python gate",
    "cut": "parameter expansion (`${var#prefix}`, `${var%suffix}`)",
    "tr": "parameter expansion, or a Python gate",
    "awk": "a Python gate -- a gate script is cheaper than an awk program",
    "cat": "`$(<file)` or a `while read` loop",
}

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.+-]*")


def strip_quoted(line: str) -> str:
    """Return the parts of a line that a shell would execute as words.

    Quoted string *text* is dropped, but a command substitution inside double
    quotes is kept: `cd "$(dirname "$0")/.."` executes `dirname`, and that is
    the exact line measured on 2026-11-12. A first version of this function
    dropped everything between double quotes, and the N1 control caught it -- a
    gate whose own negative control passes while the defect it exists for walks
    straight through is the failure shape this repository keeps finding.

    Whole-line comments are dropped by the caller. Inside a comment, `sed` and
    `dirname` are allowed to appear -- the explanation of the defect names them
    -- so a gate that scanned comments would fail on its own rationale.
    """
    out = []
    i, n = 0, len(line)
    in_double = False
    while i < n:
        ch = line[i]
        if in_double:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_double = False
                i += 1
                continue
            if ch == "$" and i + 1 < n and line[i + 1] == "(":
                depth, j, body = 1, i + 2, []
                while j < n and depth > 0:
                    c = line[j]
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                    if depth > 0:
                        body.append(c)
                    j += 1
                out.append(" " + "".join(body) + " ")
                i = j
                continue
            i += 1
            continue
        if ch == "'":
            j = line.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def scan(text: str) -> "list[tuple[int, str, str]]":
    """Return (lineno, word, line) for every external binary in command text."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            continue
        code = strip_quoted(line)
        if line.count("'") % 2 or line.count('"') % 2:
            # Unbalanced quotes: this scanner cannot tell code from message text
            # on this line, so it does not clear it. Fail closed. A parse failure
            # that reads as a pass is the failure shape this repository is named
            # after -- measured while writing this gate: a fixture line with one
            # stray quote put `sed` "inside" a string and the check said OK.
            code = line
        for match in TOKEN.finditer(code):
            word = match.group(0)
            if word in DENY:
                hits.append((lineno, word, line.strip()))
    return hits


def check(path: pathlib.Path) -> "tuple[int, list[str]]":
    if not path.exists():
        # A check that cannot find its subject has not passed it.
        return 1, ["%s is missing -- the hook this gate describes is not there" % path]
    hits = scan(path.read_text(encoding="utf-8", errors="replace"))
    if not hits:
        return 0, []
    problems = ["the hook calls %d external binary/binaries; a shell with nothing "
                "but builtins cannot start it:" % len(hits)]
    for lineno, word, line in hits:
        hint = INSTEAD.get(word)
        problems.append("  line %d: %s   (%s)" % (lineno, word, line))
        if hint:
            problems.append("           use %s" % hint)
    problems.append("")
    problems.append("Why this matters: a missing binary does not stop the hook, it "
                    "makes the hook report every gate as failed. Measured on "
                    "2026-11-12 -- 18 gates 'missing', 0 gates run.")
    return 1, problems


# --------------------------------------------------------------------------- #
# --selftest: the gate must be able to fail before it can be trusted to pass
# --------------------------------------------------------------------------- #

BUILTIN_ONLY = """#!/bin/sh
case "$0" in
    */*) hook_dir="${0%/*}" ;;
    *)   hook_dir="." ;;
esac
cd "$hook_dir/.." || exit 1
if ! out=$("$py" "tools/gate-lint.py" 2>&1); then
    printf '%s\\n' "$out" | while IFS= read -r line; do printf '    %s\\n' "$line" >&2; done
fi
"""

WITH_DIRNAME = """#!/bin/sh
cd "$(dirname "$0")/.." || exit 1
"""

WITH_SED = """#!/bin/sh
printf '%s\\n' "$out" | sed 's/^/    /' >&2
"""

COMMENTS_MENTION_BOTH = """#!/bin/sh
# 2026-11-12: this used to be `cd "$(dirname "$0")/.."` and the report used
# `printf '%s\\n' "$out" | sed 's/^/    /'`. Both needed a binary a bare
# MinGit shell does not have; both were replaced. The comment is allowed to
# name them, the code is not.
cd "${0%/*}/.." || exit 1
"""

QUOTED_MESSAGE_WORD = """#!/bin/sh
printf 'the sort order is not part of this gate\\n' >&2
echo "no cat, no grep, no sed in this line"
"""

UNBALANCED = """#!/bin/sh
printf 'x' | sed "s/x/y/  # unterminated double quote
"""


def selftest() -> int:
    results = []

    def control(name, text, want_fail):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "pre-commit"
            path.write_text(text, encoding="utf-8")
            rc, problems = check(path)
        got_fail = rc != 0
        ok = got_fail == want_fail
        results.append((ok, name, "exit=%d want=%s" % (rc, "1" if want_fail else "0")))
        if not ok:
            for line in problems:
                print("    " + line)

    control("P1 builtin-only hook passes", BUILTIN_ONLY, False)
    control("N1 dirname is rejected", WITH_DIRNAME, True)
    control("N2 sed is rejected", WITH_SED, True)
    control("N3 comments may name both (not scanned)", COMMENTS_MENTION_BOTH, False)
    control("N4 quoted message text is not scanned", QUOTED_MESSAGE_WORD, False)

    # N5 needs a path that does not exist, which control() cannot express.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        rc, problems = check(pathlib.Path(tmp) / "does-not-exist")
    results.append((rc != 0 and "missing" in " ".join(problems),
                    "N5 a missing hook is a failure, not a pass", "exit=%d" % rc))

    control("N6 unbalanced quotes fail closed, not open", UNBALANCED, True)

    print("-" * 78)
    green = sum(1 for ok, _, _ in results if ok)
    red = len(results) - green
    for ok, name, detail in results:
        print("  %-4s %-46s %s" % ("OK" if ok else "FAIL", name, detail))
    print("-" * 78)
    print("  %d controls: %d green, %d red -> %s"
          % (len(results), green, red, "SELFTEST PASS" if red == 0 else "SELFTEST FAIL"))
    return 0 if red == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the hook must run on builtins alone")
    parser.add_argument("--file", default=HOOK, help="the hook to scan")
    parser.add_argument("--selftest", action="store_true", help="run the controls")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    rc, problems = check(pathlib.Path(args.file))
    if rc == 0:
        print("OK: %s needs nothing outside the shell to start and to report"
              % args.file)
        return 0
    print("FAIL: %s" % args.file, file=sys.stderr)
    for line in problems:
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
