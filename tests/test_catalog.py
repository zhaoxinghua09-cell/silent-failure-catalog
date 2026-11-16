"""Positive tests: the catalog, as it stands, satisfies the checker.

Run: python -m unittest discover -s tests   (standard library only, like the tools)
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "check-catalog.py"


def load_checker():
    """Import tools/check-catalog.py, whose filename is not a valid module name."""
    spec = importlib.util.spec_from_file_location("check_catalog", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CatalogIsClean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = load_checker()
        cls.entries = sorted((ROOT / "failures").glob("SF-*.md"))

    def test_entries_exist(self):
        self.assertGreater(len(self.entries), 0, "no entries found — the catalog is empty")

    def test_cli_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, "checker failed:\n%s\n%s" % (proc.stdout, proc.stderr))
        self.assertIn("PASS", proc.stdout)

    def test_selftest_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--selftest"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, "selftest failed:\n%s\n%s" % (proc.stdout, proc.stderr))

    def test_every_entry_passes_structural_checks(self):
        store = self.cc.Problems()
        ids = self.cc.check_entries(store, self.entries)
        self.assertGreater(len(ids), 0)
        self.assertFalse(store, "structural findings:\n" + "\n".join(
            "%s: %s" % (p["where"], p["what"]) for p in store.items))


if __name__ == "__main__":
    # An explicit exit path, and a guard against the catalog's own SF-001: a run
    # that collects nothing must not exit 0.
    result = unittest.main(exit=False, verbosity=2)
    ran = result.result.testsRun
    if ran == 0:
        raise SystemExit("no tests collected — a green run here would be a silent pass")
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
