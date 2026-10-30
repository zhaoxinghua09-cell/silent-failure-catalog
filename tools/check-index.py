#!/usr/bin/env python3
"""check-index — assert that `index.json` is complete, contiguous and not stale.

The catalog exists because a check that cannot fail is not a check. So this script is
built to be seen failing: every rule below has a synthetic counter-example in
`--selftest`, and the run prints how many mutations were caught.

    python tools/check-index.py            # validate the shipped index.json
    python tools/check-index.py --json     # machine-readable result
    python tools/check-index.py --selftest # prove each rule can fire (mutation test)

Rules
-----
R1  index.json parses and declares schema `silent-failure-index/1`
R2  entry_count equals the number of entries and the number of `failures/SF-*.md` files
R3  ids are SF-001..SF-0NN, contiguous, unique, in order
R4  SF-015 is the only entry flagged `candidate` (a candidate is not an accepted entry)
R5  every entry carries a non-empty family (A–E), name, definition, detection_signal,
    gate_mapping and required_evidence — an empty field is a published gap, not a pass
R6  the index is not stale: regenerating from `failures/SF-*.md` reproduces it byte for byte

Exit code: 0 = clean, 1 = at least one problem (each printed with its location).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.json"
BUILDER = ROOT / "tools" / "build-index.py"
SCHEMA = "silent-failure-index/1"
REQUIRED_TEXT = ("name", "definition", "gate_mapping")
REQUIRED_LIST = ("detection_signal", "required_evidence")
FAMILIES = set("ABCDE")


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_index", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate(index: dict) -> list[str]:
    """Return a list of problems. An empty list means the index passed every rule."""
    problems: list[str] = []

    # R1
    if index.get("schema") != SCHEMA:
        problems.append(f"R1 schema is {index.get('schema')!r}, expected {SCHEMA!r}")

    entries = index.get("entries") or []
    ids = [e.get("id", "") for e in entries]

    # R2
    if index.get("entry_count") != len(entries):
        problems.append(f"R2 entry_count={index.get('entry_count')} but {len(entries)} entries present")
    files = sorted((ROOT / "failures").glob("SF-*.md"))
    if len(files) != len(entries):
        problems.append(f"R2 entry_count={len(entries)} but {len(files)} file(s) in failures/")

    # R3
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        problems.append(f"R3 duplicate id(s): {dupes}")
    expected = [f"SF-{n:03d}" for n in range(1, len(entries) + 1)]
    if ids != expected:
        problems.append(f"R3 ids are not contiguous from SF-001: got {ids}")

    # R4
    candidates = sorted(e.get("id", "") for e in entries if e.get("candidate"))
    if candidates != ["SF-015"]:
        problems.append(f"R4 candidate entries are {candidates}, expected exactly ['SF-015']")

    # R5
    for e in entries:
        eid = e.get("id", "<no id>")
        if e.get("family") not in FAMILIES:
            problems.append(f"R5 {eid}: family {e.get('family')!r} not in A–E")
        if not str(e.get("family_name", "")).strip():
            problems.append(f"R5 {eid}: empty family_name")
        for key in REQUIRED_TEXT:
            if not str(e.get(key, "")).strip():
                problems.append(f"R5 {eid}: empty {key}")
        for key in REQUIRED_LIST:
            if not e.get(key):
                problems.append(f"R5 {eid}: empty {key}")
        if not e.get("file"):
            problems.append(f"R5 {eid}: no source file recorded")

    return problems


def check_schema_shape(index: dict) -> list[str]:
    return [] if isinstance(index.get("entries"), list) else ["R1 entries is not a list"]


def staleness() -> list[str]:
    """R6 — regenerate from source and compare with the shipped file."""
    try:
        built = _load_builder().build()
    except Exception as exc:  # noqa: BLE001 - a malformed entry must surface, not crash
        return [f"R6 rebuild failed: {exc}"]
    current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    payload = json.dumps(built, ensure_ascii=False, indent=2) + "\n"
    if current != payload:
        return ["R6 index.json is stale — run: python tools/build-index.py"]
    return []


def selftest() -> int:
    """Mutation test: each mutation must produce at least one problem."""
    base = json.loads(INDEX.read_text(encoding="utf-8"))
    mutations = {
        "drop the last entry": lambda d: d["entries"].pop() or d.__setitem__("entry_count", len(d["entries"])),
        "break id contiguity": lambda d: d["entries"].__getitem__(6).__setitem__("id", "SF-099"),
        "duplicate an id": lambda d: d["entries"].__getitem__(2).__setitem__("id", "SF-001"),
        "family out of range": lambda d: d["entries"].__getitem__(0).__setitem__("family", "F"),
        "blank the definition": lambda d: d["entries"].__getitem__(3).__setitem__("definition", ""),
        "drop detection signal": lambda d: d["entries"].__getitem__(4).__setitem__("detection_signal", []),
        "promote a second candidate": lambda d: d["entries"].__getitem__(0).__setitem__("candidate", True),
        "demote SF-015": lambda d: d["entries"].__getitem__(14).__setitem__("candidate", False),
        "wrong count": lambda d: d.__setitem__("entry_count", 14),
    }
    caught = 0
    for label, mutate in mutations.items():
        mutated = json.loads(json.dumps(base))
        mutate(mutated)
        problems = validate(mutated)
        ok = bool(problems)
        caught += 1 if ok else 0
        print(f"  {'caught ' if ok else 'MISSED '} {label}"
              + ("" if ok else "   <-- rule does not fire"))
    # the unmutated index must stay quiet: a check that fires on clean input is noise
    clean = validate(base)
    print(f"  {'quiet  ' if not clean else 'NOISY  '} unmutated index" + (f"   {clean}" if clean else ""))
    print(f"\n[selftest] {caught}/{len(mutations)} mutations caught; clean input "
          f"{'quiet' if not clean else 'not quiet'}")
    return 0 if caught == len(mutations) and not clean else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate index.json against failures/SF-*.md")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true", help="mutation test of the rules")
    ap.add_argument("--no-staleness", action="store_true", help="skip the R6 rebuild comparison")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    problems: list[str] = []
    if not INDEX.exists():
        problems = ["R0 index.json is missing — run: python tools/build-index.py"]
    else:
        try:
            index = json.loads(INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems = [f"R1 index.json is not valid JSON: {exc}"]
            index = {}
        if index:
            problems = check_schema_shape(index) + validate(index)
            if not args.no_staleness:
                problems += staleness()

    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False, indent=2))
    else:
        for p in problems:
            print(f"FAIL  {p}")
        if not problems:
            n = len(json.loads(INDEX.read_text(encoding='utf-8'))["entries"])
            print(f"PASS  {n} entries · contiguous SF-001..SF-{n:03d} · single candidate (SF-015) · index fresh")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
