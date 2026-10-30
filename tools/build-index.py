#!/usr/bin/env python3
"""build-index — emit `index.json` (machine-readable entry index) from `failures/SF-*.md`.

The catalog's human-readable argument lives in the entries; this script publishes the
same facts in a shape a program can consume without scraping Markdown. Nothing here
invents content: every field is lifted from the entry file, and the field is left empty
when the entry does not carry it — an empty field is a visible gap, a guessed field is a
silent lie (SF-006).

    python tools/build-index.py            # write index.json
    python tools/build-index.py --check    # exit 1 if index.json is stale
    python tools/build-index.py --stdout   # print, do not write

Fields per entry
----------------
    id                 SF-0NN, must match the filename prefix
    family             A–E
    family_name        family title as written in the entry
    name               entry title after the middle dot
    definition         the `> **One line.**` sentence(s)
    detection_signal   `## Self-check` steps, verbatim, as a list
    gate_mapping       `## Fix` first prose paragraph (the gate this class needs)
    required_evidence  negative-control rows from `## Fix` (control → expected result)
    status / confidence / as_of / file

Exit code: 0 on success, 1 when a source entry is malformed (missing header, unparsable id).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES = ROOT / "failures"
OUT = ROOT / "index.json"

SCHEMA = "silent-failure-index/1"
ID_RE = re.compile(r"^SF-(\d{3})$")
STATUS_RE = re.compile(r"\*\*Status\*\*:\s*(?P<status>[^｜]+)｜\s*\*\*Family\*\*:\s*(?P<fam>[A-E])\s*·\s*(?P<famname>[^｜]+)｜\s*\*\*Confidence\*\*:\s*(?P<conf>[^｜]+)｜\s*\*\*as of\*\*\s*(?P<asof>[0-9]{4}-[0-9]{2}-[0-9]{2})")


def _clean(text: str) -> str:
    # strip emphasis markers only; underscores inside identifiers (-k "zzz_no_match") are content
    text = re.sub(r"[`*]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _section(lines: list[str], heading: str) -> list[str]:
    """Return the body lines of `## heading`, up to the next `## ` heading."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            continue
        if start is not None and line.startswith("## "):
            return lines[start:i]
    return lines[start:] if start is not None else []


def _prose_paragraph(body: list[str]) -> str:
    """First paragraph that is neither a code fence, a table row, nor a bullet."""
    buf: list[str] = []
    in_fence = False
    for line in body:
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not s or s.startswith("|") or s.startswith("- ") or s.startswith("* ") or s.startswith("#"):
            if buf:
                break
            continue
        buf.append(s)
    return _clean(" ".join(buf))


def _negctl_rows(body: list[str]) -> list[dict]:
    """Rows of the `| Negative control | Expected result |` table, if present."""
    rows: list[dict] = []
    header_seen = False
    for line in body:
        s = line.strip()
        if not s.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if not header_seen:
            if "negative control" in cells[0].lower():
                header_seen = True
            continue
        if set(cells[0]) <= set("-: "):
            continue
        rows.append({"control": _clean(cells[0]), "expected": _clean(cells[1])})
    return rows


def _selfcheck_steps(body: list[str]) -> list[str]:
    """Numbered/bulleted steps when the entry uses them, else its prose paragraphs.

    Three entries (SF-005, SF-007, SF-008) express the self-check as prose plus a code
    block or table; returning an empty list for those would publish "no detection
    signal" for a signal that exists — an uncounted absence (SF-005 itself).
    """
    steps: list[str] = []
    prose: list[str] = []
    buf: list[str] = []
    in_fence = False
    for line in body:
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(?:\d+\.|[-*])\s+(.*)$", s)
        if m:
            steps.append(_clean(m.group(1)))
            continue
        if not s or s.startswith("|") or s.startswith("#"):
            if buf:
                prose.append(_clean(" ".join(buf)))
                buf = []
            continue
        buf.append(s)
    if buf:
        prose.append(_clean(" ".join(buf)))
    if steps:
        return steps
    # drop one-word connectives left over from the code block ("Then:", "For the package case:")
    return [p for p in prose if len(p.split()) >= 5][:4]


def parse_entry(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 5:
        raise ValueError(f"{path.name}: too short to be an entry")

    m = ID_RE.match(path.name.split("-", 2)[0] + "-" + path.name.split("-", 2)[1]) if False else None
    stem_id = "-".join(path.name.split("-")[:2])
    if not ID_RE.match(stem_id):
        raise ValueError(f"{path.name}: filename does not start with SF-0NN")

    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if "·" in title:
        tid, name = title.split("·", 1)
        if tid.strip() != stem_id:
            raise ValueError(f"{path.name}: title id {tid.strip()} != filename id {stem_id}")
        name = name.strip()
    else:
        name = title.strip()

    header = next((l for l in lines if l.startswith("**Status**")), "")
    hm = STATUS_RE.search(header)
    if not hm:
        raise ValueError(f"{path.name}: unparsable Status/Family header")

    definition = ""
    for i, line in enumerate(lines):
        if "**One line.**" in line:
            parts = [line.split("**One line.**", 1)[1].strip()]
            for nxt in lines[i + 1 :]:
                if not nxt.strip():          # a blank line ends the One-line blockquote
                    break
                if nxt.strip().startswith(">"):
                    body_line = nxt.strip().lstrip(">").strip()
                    if body_line.startswith("**"):   # a changelog/nested bold block is not the definition
                        break
                    parts.append(body_line)
                else:
                    break
            definition = _clean(" ".join(p for p in parts if p))
            break

    fix_body = _section(lines, "## Fix")
    status = hm.group("status").strip()

    return {
        "id": stem_id,
        "family": hm.group("fam"),
        "family_name": _clean(hm.group("famname")),
        "name": _clean(name),
        "status": _clean(status),
        "candidate": "candidate" in status.lower(),
        "confidence": _clean(hm.group("conf")),
        "as_of": hm.group("asof"),
        "definition": definition,
        "detection_signal": _selfcheck_steps(_section(lines, "## Self-check")),
        "gate_mapping": _prose_paragraph(fix_body),
        "required_evidence": _negctl_rows(fix_body),
        "file": f"failures/{path.name}",
    }


def build() -> dict:
    entries = [parse_entry(p) for p in sorted(FAILURES.glob("SF-*.md"))]
    entries.sort(key=lambda e: e["id"])
    return {
        "schema": SCHEMA,
        "generated_from": "failures/SF-*.md",
        "regenerate_with": "python tools/build-index.py",
        "entry_count": len(entries),
        "ids": [e["id"] for e in entries],
        "candidate_ids": [e["id"] for e in entries if e["candidate"]],
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build index.json from failures/SF-*.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if index.json is stale")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = ap.parse_args(argv)

    try:
        index = build()
    except ValueError as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        sys.stdout.write(payload)
        return 0
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print("FAIL  index.json is stale — run: python tools/build-index.py", file=sys.stderr)
            return 1
        print(f"OK    index.json matches {index['entry_count']} entries")
        return 0
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  entries={index['entry_count']}  candidates={index['candidate_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
