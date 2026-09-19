#!/usr/bin/env python3
"""check-catalog — validate the internal consistency of this catalog.

The catalog's whole argument is that a check which only verifies what it can find
will always pass. So this script does the opposite: it asserts that the things
which *must* be present are present, and it fails when they are not.

    python tools/check-catalog.py
    python tools/check-catalog.py --scan-leaks
    python tools/check-catalog.py --json

Checks performed
----------------
1. every `failures/SF-*.md` declares `Status`, `Family`, `Confidence` and an `as of` date
2. every entry contains all six required sections
3. the id in the file matches the filename, and ids are unique
4. every id appears in `failures/README.md` **and** the taxonomy table in `README.md`
5. every id is linked from `llms.txt` and from `docs/start-here.md`
6. every relative Markdown link in the catalog resolves to a file that exists
7. `CHANGELOG.md` documents the current version
8. outbound links to the maintainer's own channels appear **only** on the designated
   entry pages — see `check_promo_links`, and `--selftest` for its sample pair
9. (optional, `--scan-leaks`) heuristic de-identification scan
10. (optional, `--selftest`) the link-discipline rule proves it can fire and can stay quiet

Version note (2026-09-19): the index check originally used `if eid in text`, a
substring test that stayed satisfied even after an entry's link was mangled —
SF-012's disease, in this file. It now asserts that each entry's **filename** is
linked. Found by running a reverse-control test against this script, which is
the only way such a defect is ever found.

Exit code: 0 = clean, 1 = at least one problem (each printed with its location).

This script reports the *absence* of required things as a failure, which is the
one behaviour the catalog exists to advocate. See failures/SF-005 and SF-006.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_SECTIONS = [
    "## Symptom",
    "## Why it is silent",
    "## Minimal reproduction",
    "## Self-check",
    "## Fix",
    "## Related",
]

HEADER_FIELDS = ("Status", "Family", "Confidence", "as of")

ID_IN_TITLE_RE = re.compile(r"^#\s+(SF-\d{3})\s+·", re.M)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# link targets we deliberately do not resolve
LINK_SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "../../", "/")

LEAK_PATTERNS = [
    ("absolute Windows path", re.compile(r"\b[A-Za-z]:[\\/](?:Users|Documents|Projects|Work)[\\/]")),
    ("absolute POSIX home path", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")),
    ("email address", re.compile(r"\b[\w.+-]+@(?!example\.(?:com|org|invalid)\b)[\w-]+\.[A-Za-z]{2,}\b")),
    ("possible credential", re.compile(r"\b(?:ghp_|gho_|github_pat_|sk-|xox[baprs]-|AKIA)[A-Za-z0-9_-]{10,}")),
    ("internal hostname", re.compile(r"\b(?<!example)\.(?:internal|corp|local)\b")),
    ("private IPv4", re.compile(r"\b(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
]

# ---------------------------------------------------------------------------
# Outbound-link discipline.
#
# A project page that links out in eight directions reads as an advertisement,
# and readers grade the repository on it. So links to the maintainer's own
# channels are permitted only in files *designated* as entry pages; anywhere
# else they are a finding.
#
# Why this is a check and not a sentence in CONTRIBUTING.md: a guideline with no
# detector has never been observed failing, and per this catalog's own rule 2
# that makes it not a guideline at all. See --selftest, which carries the sample
# pair — one input the rule must flag, one it must leave alone.
# ---------------------------------------------------------------------------

# Files allowed to carry outbound links to our own channels, on purpose.
ENTRY_PAGES = ("docs/where-to-find-us.md", "docs/start-here.md")

# Links to this repository are structural, not promotional: clone URLs, badge
# URLs, issue links, security-advisory links. They are always allowed, so they
# are scrubbed from each line before the rules below run.
#
# The `(?:\.git)?` is **defensive, and measurably not load-bearing.** This comment
# used to claim it was required, because without it `.../silent-failure-catalog.git`
# would be misread as a sibling repository. Running selftest case 3 against the
# naive regex showed the case passes either way — the scrub already stops before
# the dot, and the leftover `.git` never re-forms a URL. The false claim is
# recorded as defect 10 in docs/building-this-catalog.md rather than quietly
# deleted, because an unverified comment is how a false claim enters a codebase.
CANONICAL_RE = re.compile(
    r"https?://github\.com/zhaoxinghua09-cell/silent-failure-catalog(?:\.git)?(?![\w-])",
    re.I,
)

OWN_CHANNEL_PATTERNS = [
    ("a Q&A / long-form channel of the maintainer",
     re.compile(r"https?://[\w.-]*zhihu\.com/", re.I)),
    ("the maintainer's researcher identity record",
     re.compile(r"https?://[\w.-]*orcid\.org/", re.I)),
    ("a WeChat official-account URL",
     re.compile(r"https?://[\w.-]*weixin\.qq\.com/", re.I)),
    ("a domain-branded project site",
     re.compile(r"https?://[\w.-]*medxpert\.cn/", re.I)),
    ("a platform-hosted service endpoint",
     re.compile(r"https?://[\w.-]*workbuddy\.host/", re.I)),
    ("the account's static-hosting host",
     re.compile(r"https?://zhaoxinghua09-cell\.github\.io/", re.I)),
    ("another repository on the same account",
     re.compile(r"https?://github\.com/zhaoxinghua09-cell/[A-Za-z0-9_.-]*[A-Za-z0-9_-]", re.I)),
]

# Known false negatives of the rule above, stated rather than implied:
#  - a bare domain with no scheme (`zhihu.com/people/x`) is not matched;
#    the rule covers links, and a link without a scheme is not clickable here.
#  - a link shortener, or a URL that redirects to one of our hosts, is not
#    matched. Chasing redirects would put network access in the validator.
# Both are accepted: this is a style rule, and a style rule that reaches for the
# network is a style rule that turns a red build into a mystery.

SELFTEST_CASES = [
    # (name, text, expected number of findings)
    ("relative link only", "See [start here](docs/start-here.md) for the index.", 0),
    ("an own-channel link", "Read more at https://www.zhihu.com/people/some-person", 1),
    ("the canonical clone URL", "git clone https://github.com/zhaoxinghua09-cell/silent-failure-catalog.git", 0),
    ("the canonical issue tracker", "https://github.com/zhaoxinghua09-cell/silent-failure-catalog/issues/12", 0),
    ("a sibling repository", "https://github.com/zhaoxinghua09-cell/agent-skills", 1),
    ("an unrelated external reference", "https://martinfowler.com/articles/mutation-testing.html", 0),
    ("someone else's Pages host", "https://some-other-account.github.io/thing/", 0),
]


def find_promo_links(text: str) -> "list[tuple[int, str, str]]":
    """Return `(line number, label, url)` for each outbound own-channel link."""
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        scrubbed = CANONICAL_RE.sub("", line)
        for label, rx in OWN_CHANNEL_PATTERNS:
            for m in rx.finditer(scrubbed):
                found.append((lineno, label, m.group(0)))
    return found


def check_promo_links(store: Problems, files: "list[Path]"):
    """Own-channel links are allowed on the entry pages and nowhere else."""
    for p in files:
        # positive test, not a `continue` guard: an early exit here would read
        # as a silent pass, which is what this catalog is about
        if rel(p) not in ENTRY_PAGES:
            try:
                text = p.read_text(encoding="utf-8")
            except OSError as e:
                # never swallow: an unreadable file is an unchecked file
                store.add(rel(p), "could not be read for the link-discipline check: %s" % e)
                continue
            for lineno, label, url in find_promo_links(text):
                store.add(rel(p), "line %d: outbound link to %s (%r) — entry pages are %s"
                          % (lineno, label, url, " and ".join(ENTRY_PAGES)))


def selftest() -> int:
    """Prove the link-discipline rule can fire, and can stay quiet.

    Three controls, because two of them are individually satisfiable by a broken
    rule: a rule that fires on everything passes the "must fire" case, and a rule
    that fires on nothing passes the "must stay quiet" case.
    """
    print("check-catalog --selftest")
    print("------------------------")
    bad = 0
    fired = 0

    for name, text, expected in SELFTEST_CASES:
        got = len(find_promo_links(text))
        ok = got == expected
        fired += 1 if got else 0
        print("  %-4s %-32s got=%d  expected=%d" % ("ok" if ok else "FAIL", name, got, expected))
        if not ok:
            bad += 1

    # Negative control. With the rule set emptied, every case must go quiet.
    # Without this, a finding produced by something *other* than the rules would
    # still make the "must fire" case look correct.
    saved = list(OWN_CHANNEL_PATTERNS)
    try:
        OWN_CHANNEL_PATTERNS.clear()
        leaked = [n for n, t, e in SELFTEST_CASES if e and find_promo_links(t)]
    finally:
        OWN_CHANNEL_PATTERNS[:] = saved
    if leaked:
        print("  FAIL negative control: still a finding with no rule loaded → %s" % ", ".join(leaked))
        bad += 1
    else:
        print("  ok   negative control: silent with the rule set emptied")

    # Sample pair, asserted rather than assumed.
    if fired == 0:
        print("  FAIL sample pair: no case fires — the rule cannot fail, so it proves nothing")
        bad += 1
    elif fired == len(SELFTEST_CASES):
        print("  FAIL sample pair: every case fires — a rule that flags everything is noise")
        bad += 1
    else:
        print("  ok   sample pair: %d of %d cases fire" % (fired, len(SELFTEST_CASES)))

    print()
    if bad:
        print("  %d selftest failure(s). The rule is not trustworthy." % bad)
        return 1
    print("  PASS — the rule fires on its bad sample and is silent on its good samples.")
    return 0



class Problems:
    def __init__(self):
        self.items = []

    def add(self, where, what):
        self.items.append({"where": str(where), "what": what})

    def __bool__(self):
        return bool(self.items)


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def check_entries(store: Problems, entries: "list[Path]") -> "set[str]":
    """Per-entry structural checks. Returns the set of ids found."""
    ids = set()
    seen = {}

    for p in entries:
        name = p.name
        text = p.read_text(encoding="utf-8")
        rp = rel(p)

        m = ID_IN_TITLE_RE.search(text)
        if not m:
            store.add(rp, "title does not match '# SF-nnn · <name>'")
            continue
        eid = m.group(1)
        ids.add(eid)

        if not name.startswith(eid):
            store.add(rp, "filename does not start with the declared id %s" % eid)
        if eid in seen:
            store.add(rp, "duplicate id %s (also in %s)" % (eid, seen[eid]))
        seen[eid] = rp

        head = text[: text.find("\n## ")] if "\n## " in text else text
        for field in HEADER_FIELDS:
            if field == "as of":
                # the date is written as `**as of** YYYY-MM-DD` — allow the bold markers
                if not re.search(r"\bas of\b\s*\**\s*\d{4}-\d{2}-\d{2}", text):
                    store.add(rp, "missing 'as of YYYY-MM-DD' date")
            elif "**%s**" % field not in head:
                store.add(rp, "missing **%s** in the header block" % field)

        for sec in REQUIRED_SECTIONS:
            if sec not in text:
                store.add(rp, "missing required section: %s" % sec)

        # a fix must carry a negative control
        if "| Negative control |" not in text:
            store.add(rp, "Fix section has no negative-control table")

    return ids


def check_indexes(store: Problems, ids: "set[str]", entries: "list[Path]"):
    """An index must *link* every entry, not merely mention its id.

    Naive `if eid in text` is a substring test: it stays satisfied when the id
    survives inside a mangled string like `SF-014-REMOVED`. That is the
    substring-collision failure the catalog documents as SF-012 — found here by
    running the reverse-control test on this very file, which is why the check
    now asserts the linked **filename** instead of the bare id.
    """
    index_targets = ("README.md", "failures/README.md", "llms.txt", "docs/start-here.md")
    for target in index_targets:
        p = ROOT / target
        if not p.is_file():
            store.add(target, "file missing")
            continue
        text = p.read_text(encoding="utf-8")
        for entry in entries:
            if entry.name not in text:
                store.add(target, "does not link the entry file %s (id mention alone is "
                                   "not enough — see tools/check-catalog.py docstring)" % entry.name)
        # additionally: the id must appear and must not be the only trace
        for eid in sorted(ids):
            if not re.search(r"\b%s\b(?!-)" % re.escape(eid), text):
                store.add(target, "does not list %s" % eid)


def check_links(store: Problems, files: "list[Path]"):
    for p in files:
        text = p.read_text(encoding="utf-8")
        for raw in MD_LINK_RE.findall(text):
            target = raw.strip().split("#", 1)[0].strip()
            # positive test rather than a chain of early-continues: a `continue`
            # guard reads as a silent pass and is flagged by gate-lint (SFL-002)
            if target and not target.startswith(LINK_SKIP_PREFIXES):
                resolved = (p.parent / target).resolve()
                if not resolved.exists():
                    store.add(rel(p), "broken link: %s" % raw)


def check_changelog(store: Problems):
    p = ROOT / "CHANGELOG.md"
    if not p.is_file():
        store.add("CHANGELOG.md", "file missing")
        return
    text = p.read_text(encoding="utf-8")
    if not re.search(r"\d+\.\d+\.\d+", text):
        store.add("CHANGELOG.md", "no semantic version found")


def check_required_files(store: Problems):
    required = [
        "README.md", "AGENTS.md", "llms.txt", "CITATION.cff",
        "LICENSE", "LICENSE-CONTENT", "CONTRIBUTING.md", "CHANGELOG.md",
        ".gitattributes", ".zenodo.json",
        "SUPPORT.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
        "docs/taxonomy.md", "docs/question-map.md", "docs/building-this-catalog.md",
        "docs/start-here.md", "docs/where-to-find-us.md", "docs/take-the-challenge.md",
        "failures/README.md", "failures/TEMPLATE.md",
        "tools/gate-lint.py", "tools/check-catalog.py", "tools/make-manifest.py",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/new-failure-mode.yml",
        ".github/ISSUE_TEMPLATE/false-positive.yml",
        "INTEGRITY.md", "manifest.sha256",
    ]
    for r in required:
        if not (ROOT / r).exists():
            store.add(r, "required file is absent (SF-006: undeclared means unchecked)")

    # The entry pages are declared above; assert the declaration matches reality.
    # Otherwise renaming the landing page would silently switch the whole
    # link-discipline rule off — a check that cannot notice its own target going
    # missing is the failure this catalog documents.
    for entry in ENTRY_PAGES:
        if not (ROOT / entry).is_file():
            store.add(entry, "declared as an entry page in ENTRY_PAGES but is not a file")


# inline suppression for the leak scan. Deliberately *reported*, never silent:
# a suppression that leaves no trace is the failure mode this catalog documents.
LEAK_ALLOW_RE = re.compile(r"leak-scan:\s*allow", re.I)

SUPPRESSIONS = {"count": 0, "where": []}


def scan_leaks(store: Problems, files: "list[Path]"):
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            # never swallow: an unreadable file is an unchecked file
            store.add(rel(p), "could not be read for the leak scan: %s" % e)
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            context = lines[lineno - 2] if lineno >= 2 else ""
            if LEAK_ALLOW_RE.search(line) or LEAK_ALLOW_RE.search(context):
                if any(rx.search(line) for _, rx in LEAK_PATTERNS):
                    SUPPRESSIONS["count"] += 1
                    SUPPRESSIONS["where"].append("%s:%d" % (rel(p), lineno))
                continue
            for label, rx in LEAK_PATTERNS:
                m = rx.search(line)
                if m:
                    store.add(rel(p), "line %d: possible %s → %r" % (lineno, label, m.group(0)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="check-catalog")
    ap.add_argument("--scan-leaks", action="store_true",
                    help="also run the heuristic de-identification scan")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the link-discipline rule can fire and can stay quiet")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    store = Problems()

    entries = sorted(ROOT.glob("failures/SF-*.md"))
    if not entries:
        store.add("failures/", "no entries found — an empty catalog is a silent pass")

    ids = check_entries(store, entries)
    check_indexes(store, ids, entries)
    check_required_files(store)
    check_changelog(store)

    md_files = [
        p for p in ROOT.rglob("*.md")
        if ".git" not in p.parts and "TEMPLATE.md" not in p.name
    ]
    check_links(store, md_files + [ROOT / "llms.txt"])
    check_promo_links(store, md_files + [ROOT / "llms.txt"])

    if args.scan_leaks:
        targets = md_files + [ROOT / "llms.txt"] + list(ROOT.glob("tools/*.py"))
        scan_leaks(store, targets)

    if args.json:
        print(json.dumps(
            {"entries": len(entries), "ids": sorted(ids), "problems": store.items},
            indent=2, ensure_ascii=False,
        ))
    else:
        print("check-catalog")
        print("-------------")
        print("  entries: %d" % len(entries))
        print("  ids    : %s" % ", ".join(sorted(ids)))
        print("  entry pages (the only files allowed outbound self-links): %s"
              % ", ".join(ENTRY_PAGES))
        if args.scan_leaks:
            print("  leak scan: ENABLED (heuristic)")
            if SUPPRESSIONS["count"]:
                print("  suppressed: %d line(s) via 'leak-scan: allow' → %s"
                      % (SUPPRESSIONS["count"], ", ".join(SUPPRESSIONS["where"])))
        print()
        if store:
            print("  %d problem(s):" % len(store.items))
            for it in store.items:
                print("    🔴 %-28s %s" % (it["where"], it["what"]))
            print()
            print("FAIL — a required item is absent or inconsistent.")
            return 1
        print("PASS — every required section present, every id indexed, every link resolves.")
    return 1 if store else 0


if __name__ == "__main__":
    sys.exit(main())
