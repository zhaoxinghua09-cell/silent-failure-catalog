"""Sample (good): a gate that can actually fail.

Deliberately structured to avoid every shape gate-lint looks for:

* an explicit failure path driven by a counter (SFL-001, SFL-004)
* no exception is discarded (SFL-002)
* the empty case is a failure, not a fall-through (SFL-003)
* the test runner's collection is asserted (SFL-005)
* a negative-control sample exists elsewhere in the tree (SFL-006)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MIN_RECORDS = 1
REQUIRED_FIELDS = ("id", "title", "url")


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_suite() -> int:
    proc = subprocess.run(
        ["pytest", "-q", "--strict-markers"],
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    if "collected" not in output:
        raise RuntimeError("test runner printed no collection line — refusing to trust it")
    return proc.returncode


def check_records(records) -> list:
    problems = []
    if not records:
        problems.append("0 records loaded — refusing to report success")
        return problems
    for rec in records:
        for field in REQUIRED_FIELDS:
            if not rec.get(field):
                problems.append("%s: required field empty: %s" % (rec.get("id", "?"), field))
    return problems


def main() -> int:
    records = load("records.json")
    problems = check_records(records)

    rc = run_suite()
    if rc != 0:
        problems.append("test suite failed (rc=%d)" % rc)

    if len(records) < MIN_RECORDS:
        problems.append("only %d records, need >= %d" % (len(records), MIN_RECORDS))

    if problems:
        for p in problems:
            print("FAIL: %s" % p)
        return 1

    print("PASS: %d records, all required fields present" % len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
