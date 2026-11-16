"""Negative controls: each rule is shown to fire on a bad input, and to fall silent
when its own rule set is removed or when a required thing is deleted from an entry.

A positive test alone is satisfied by a rule that fires on everything; this file
exists so that claim cannot be made here.

Run: python -m unittest discover -s tests   (standard library only, like the tools)
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "check-catalog.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_catalog", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENTRY_SKELETON = """# SF-999 · Negative-control fixture

**Status**: `draft` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: low ｜ **as of** 2026-11-17

## Symptom

fixture

## Why it is silent

fixture

## Minimal reproduction

fixture

## Self-check

fixture

## Fix

| Negative control | What it must catch |
|---|---|
| fixture | fixture |

## Related

fixture
"""

FIX_BLOCK = "## Fix\n\n| Negative control | What it must catch |\n|---|---|\n| fixture | fixture |\n\n"


class LinkRuleHasTwoControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = load_checker()

    def test_rule_fires_on_the_bad_sample(self):
        bad = [c for c in self.cc.SELFTEST_CASES if c[2] == 1]
        self.assertTrue(bad, "no firing sample in SELFTEST_CASES — the pair is incomplete")
        for name, text, expected in bad:
            with self.subTest(case=name):
                self.assertEqual(len(self.cc.find_promo_links(text)), expected)

    def test_rule_stays_quiet_on_the_good_samples(self):
        good = [c for c in self.cc.SELFTEST_CASES if c[2] == 0]
        self.assertTrue(good, "no quiet sample in SELFTEST_CASES — the pair is incomplete")
        for name, text, expected in good:
            with self.subTest(case=name):
                self.assertEqual(len(self.cc.find_promo_links(text)), 0)

    def test_rule_goes_silent_when_its_own_rules_are_emptied(self):
        """The negative control: nothing fires when no rule is loaded.

        Without this, a finding produced by something other than the rule would
        still make the "must fire" case look correct.
        """
        firing = [c for c in self.cc.SELFTEST_CASES if c[2] == 1]
        self.assertTrue(firing)
        original = self.cc.OWN_CHANNEL_PATTERNS
        try:
            self.cc.OWN_CHANNEL_PATTERNS = []
            for name, text, _ in firing:
                with self.subTest(case=name):
                    self.assertEqual(self.cc.find_promo_links(text), [],
                                     "still a finding with no rule loaded: %s" % name)
        finally:
            self.cc.OWN_CHANNEL_PATTERNS = original


class RequiredThingsCountAsFindings(unittest.TestCase):
    """Absence must be reported. These fixtures each remove one required thing."""

    @classmethod
    def setUpClass(cls):
        cls.cc = load_checker()

    def _check(self, text):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "SF-999-negative-control-fixture.md"
            p.write_text(text, encoding="utf-8")
            store = self.cc.Problems()
            self.cc.check_entries(store, [p])
            return [item["what"] for item in store.items]

    def test_complete_skeleton_is_not_flagged(self):
        self.assertEqual(self._check(ENTRY_SKELETON), [])

    def test_removed_section_is_flagged(self):
        found = self._check(ENTRY_SKELETON.replace(FIX_BLOCK, ""))
        self.assertIn("missing required section: ## Fix", found)

    def test_removed_negative_control_table_is_flagged(self):
        text = ENTRY_SKELETON.replace(
            "| Negative control | What it must catch |\n|---|---|\n| fixture | fixture |", "")
        self.assertIn("Fix section has no negative-control table", self._check(text))

    def test_title_without_id_is_flagged(self):
        text = ENTRY_SKELETON.replace(
            "# SF-999 · Negative-control fixture", "# A fixture with no id")
        self.assertIn("title does not match '# SF-nnn · <name>'", self._check(text))


if __name__ == "__main__":
    # An explicit exit path, and a guard against SF-001: negative controls that
    # collect nothing must not report success.
    result = unittest.main(exit=False, verbosity=2)
    ran = result.result.testsRun
    if ran == 0:
        raise SystemExit("no negative controls collected — a green run here would be a silent pass")
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
