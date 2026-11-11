"""companies.json must stay well-formed: a bad entry should fail make check, not a production run."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_jobs as fj  # noqa: E402
TAGS = {"ai", "quant", "hedge", "tech", "finance", "realestate"}


class Companies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.companies = json.loads((ROOT / "companies.json").read_text())["companies"]

    def test_every_entry_is_complete(self):
        for c in self.companies:
            with self.subTest(c.get("name")):
                self.assertTrue(c.get("name") and c.get("token"))
                self.assertIn(c["ats"], set(fj.FETCHERS))
                self.assertTrue(set(c.get("tags", [])) <= TAGS, c.get("tags"))
                self.assertTrue(c.get("tags"))
                if c["ats"] == "workday":
                    self.assertRegex(c.get("host", ""), r"^wd\d+$")
                if c["ats"] == "oracle":
                    self.assertRegex(c.get("host", ""), r"^[a-z0-9.-]+\.oraclecloud\.com$")
                if c["ats"] == "successfactors":
                    self.assertRegex(c.get("host", ""), r"^[a-z0-9.-]+\.[a-z]{2,}$")
                if c["ats"] in ("workday", "oracle"):
                    self.assertTrue(c.get("site"))
                    t = c.get("terms")
                    self.assertTrue(t is None or t == "finance" or (isinstance(t, list) and all(isinstance(x, str) for x in t)))
                elif c["ats"] != "successfactors":
                    self.assertNotIn("terms", c)
                if "onlyLocations" in c:
                    re.compile(c["onlyLocations"])

    def test_no_duplicate_boards_or_names(self):
        boards = [(c["ats"], c["token"], c.get("site")) for c in self.companies]  # one Workday tenant can have several sites
        names = [c["name"].lower() for c in self.companies]
        self.assertEqual(len(boards), len(set(boards)))
        self.assertEqual(len(names), len(set(names)))

    def test_owner_removed_boards_stay_removed(self):
        # removed by the owner on 2026-09-22 ("too many roles"); re-adding them needs the owner's say-so
        self.assertFalse({"Capital One", "Mastercard"} & {c["name"] for c in self.companies})


if __name__ == "__main__":
    unittest.main()
