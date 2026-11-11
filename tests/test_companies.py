"""companies.json must stay well-formed: a bad entry should fail make check, not a production run."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAGS = {"ai", "quant", "hedge", "tech", "finance"}


class Companies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.companies = json.loads((ROOT / "companies.json").read_text())["companies"]

    def test_every_entry_is_complete(self):
        for c in self.companies:
            with self.subTest(c.get("name")):
                self.assertTrue(c.get("name") and c.get("token"))
                self.assertIn(c["ats"], {"greenhouse", "ashby", "lever", "workday"})
                self.assertTrue(set(c.get("tags", [])) <= TAGS, c.get("tags"))
                self.assertTrue(c.get("tags"))
                if c["ats"] == "workday":
                    self.assertRegex(c.get("host", ""), r"^wd\d+$")
                    self.assertTrue(c.get("site"))
                    t = c.get("terms")
                    self.assertTrue(t is None or t == "finance" or (isinstance(t, list) and all(isinstance(x, str) for x in t)))
                else:
                    self.assertNotIn("terms", c)
                if "onlyLocations" in c:
                    re.compile(c["onlyLocations"])

    def test_no_duplicate_boards_or_names(self):
        boards = [(c["ats"], c["token"]) for c in self.companies]
        names = [c["name"].lower() for c in self.companies]
        self.assertEqual(len(boards), len(set(boards)))
        self.assertEqual(len(names), len(set(names)))

    def test_owner_removed_boards_stay_removed(self):
        # removed by the owner on 2026-09-22 ("too many roles"); re-adding them needs the owner's say-so
        self.assertFalse({"Capital One", "Mastercard"} & {c["name"] for c in self.companies})


if __name__ == "__main__":
    unittest.main()
