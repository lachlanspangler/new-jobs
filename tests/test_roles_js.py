"""docs/roles.js must agree with fetch_jobs.py on what a finance role is, and classify roles/entry level sensibly.
Runs the real roles.js in node (skipped if node isn't installed)."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_jobs as fj  # noqa: E402

TITLES = ["Financial Analyst", "Senior Financial Analyst, FP&A", "Investment Banking Analyst", "Equity Research Associate",
          "2027 Summer Analyst - Investment Banking", "Sales & Trading Analyst", "Credit Analyst", "Treasury Analyst",
          "Fund Accounting Analyst", "Economist", "Wealth Management Associate", "Data Analyst", "Security Analyst",
          "VP, Investment Banking", "Finance Manager", "Software Engineer", "Quant Researcher", "Business Analyst",
          "Software Engineer I", "New Grad Software Engineer", "Software Engineer II", "Senior Software Engineer",
          "Associate Director, Finance", "Junior Quant Developer", "Analyst, Investment Banking", "Staff Engineer",
          "Software Engineering Intern", "Associate Product Manager", "Analyst II, Credit Risk", "Engineering Manager"]

SCRIPT = """
global.window = global;
require(%r);
const titles = JSON.parse(process.argv[1]);
console.log(JSON.stringify(titles.map((t) => [ROLES.isFinance(t), ROLES.roleOf(t), ROLES.isEntry(t)])));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RolesJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(["node", "-e", SCRIPT % str(ROOT / "docs" / "roles.js"), json.dumps(TITLES)],
                             capture_output=True, text=True, check=True).stdout
        cls.js = dict(zip(TITLES, json.loads(out)))

    def test_finance_matches_the_fetcher(self):
        for t in TITLES:
            py = bool(fj.FIN_FIELD_RE.search(t) and fj.FIN_ROLE_RE.search(t))  # roles.js has no exclude list:
            self.assertEqual(self.js[t][0], py, t)                            # the fetcher already applied it

    def test_role_categories(self):
        role = {t: v[1] for t, v in self.js.items()}
        self.assertEqual(role["Investment Banking Analyst"], "Finance")
        self.assertEqual(role["Financial Analyst"], "Finance")
        self.assertEqual(role["Quant Researcher"], "Quant Researcher")
        self.assertEqual(role["Software Engineer"], "Software Engineer")
        self.assertEqual(role["Business Analyst"], "Other")

    def test_entry_level(self):
        entry = {t for t, v in self.js.items() if v[2]}
        for t in ["Investment Banking Analyst", "2027 Summer Analyst - Investment Banking", "Software Engineer I",
                  "New Grad Software Engineer", "Junior Quant Developer", "Analyst, Investment Banking",
                  "Software Engineering Intern", "Credit Analyst"]:
            self.assertIn(t, entry)
        for t in ["Software Engineer", "Software Engineer II", "Senior Software Engineer", "Associate Director, Finance",
                  "VP, Investment Banking", "Staff Engineer", "Associate Product Manager", "Analyst II, Credit Risk",
                  "Engineering Manager", "Senior Financial Analyst, FP&A"]:
            self.assertNotIn(t, entry)


if __name__ == "__main__":
    unittest.main()
