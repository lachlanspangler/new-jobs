"""Job categories: what each keeps and drops, how ties between categories resolve, and that every exported job is tagged."""
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_jobs as fj  # noqa: E402

RE = ("realestate",)


def cat(title, tags=()):
    return fj.category_of(title, tags)


class Software(unittest.TestCase):
    def test_kept(self):
        for t in ["Software Engineer", "Senior Backend Engineer", "C++ Developer", "Python Engineer", "Site Reliability Engineer",
                  "Machine Learning Engineer", "Full Stack Developer", "New Grad Software Engineer", "Software Development Engineer",
                  "Software Engineer, Real Estate Platform", "Associate Software Engineer, Investment Platform"]:
            self.assertEqual(cat(t), "software", t)
        self.assertEqual(cat("Software Development Engineer", RE), "software")  # a real estate company's SWE is still SWE

    def test_dropped(self):
        for t in ["Sales Engineer", "Solutions Engineer", "Mechanical Engineer", "Hardware Engineer", "Product Manager",
                  "Recruiter", "Customer Success Engineer"]:
            self.assertIsNone(cat(t), t)


class Quant(unittest.TestCase):
    def test_kept(self):
        for t in ["Quantitative Researcher", "Quant Developer", "Quant Trader", "Quantitative Analyst", "Trading Analyst",
                  "Trade Desk Operations Associate", "Junior Trader"]:
            self.assertEqual(cat(t), "quant", t)

    def test_sales_and_trading_is_finance_not_quant(self):
        self.assertEqual(cat("Sales & Trading Analyst"), "finance")
        self.assertEqual(cat("Sales and Trading Summer Analyst"), "finance")


class RealEstate(unittest.TestCase):
    def test_kept_at_real_estate_companies(self):
        for t in ["Acquisitions Analyst", "Acquisitions Associate", "Asset Management Analyst", "Asset Management Associate",
                  "Investment Analyst", "Capital Markets Analyst", "Underwriting Analyst", "Brokerage Analyst",
                  "Research Analyst", "Debt & Equity Associate", "Transactions Analyst", "Valuation Analyst",
                  "Summer Analyst, Investments", "Leasing Analyst"]:
            self.assertEqual(cat(t, RE), "realestate", t)

    def test_kept_anywhere_when_the_title_names_real_estate(self):
        for t in ["Real Estate Private Equity Associate", "Real Estate Analyst", "REIT Equity Research Associate",
                  "Real Estate Financial Analyst", "Multifamily Acquisitions Analyst", "Land Acquisition Analyst",
                  "Commercial Real Estate Credit Analyst"]:
            self.assertEqual(cat(t), "realestate", t)

    def test_dropped(self):
        for t in ["Entry-Level Commercial Real Estate Agent", "Associate - Real Estate Broker",
                  "CAM Analyst II - Foreclosure, Bankruptcy and Property Preservation",
                  "Leasing Agent", "Property Manager", "Construction Project Manager", "Maintenance Technician",
                  "Leasing Consultant", "Business Development Associate", "Sales Associate", "Marketing Analyst"]:
            self.assertIsNone(cat(t, RE), t)

    def test_same_title_elsewhere_is_finance(self):
        for t in ["Acquisitions Analyst", "Investment Analyst", "Capital Markets Analyst"]:
            self.assertEqual(cat(t), "finance", t)
        # FP&A stays finance even at a real estate company, unless the title names real estate
        self.assertEqual(cat("Financial Analyst", RE), "finance")
        self.assertEqual(cat("FP&A Analyst", RE), "finance")


class Development(unittest.TestCase):
    def test_kept(self):
        for t in ["Development Analyst", "Development Associate", "Real Estate Development Associate",
                  "Development Summer Analyst", "Junior Development Associate"]:
            self.assertEqual(cat(t, RE), "development", t)
        self.assertEqual(cat("Real Estate Development Analyst"), "development")
        self.assertEqual(cat("Multifamily Development Associate"), "development")

    def test_dropped(self):
        self.assertIsNone(cat("Development Analyst"))  # no real estate context: could be fund/product development
        for t in ["Business Development Associate", "Product Development Analyst", "Fund Development Associate",
                  "Leadership Development Associate", "Development Manager"]:
            self.assertIsNone(cat(t, RE), t)
        self.assertEqual(cat("Software Development Engineer", RE), "software")
        self.assertNotEqual(cat("Web Development Intern", RE), "development")


class Finance(unittest.TestCase):
    def test_kept(self):
        for t in ["Financial Analyst", "Financial Analyst II", "FP&A Analyst", "Investment Banking Analyst",
                  "2027 Summer Analyst - Investment Banking", "Equity Research Associate", "Corporate Finance Analyst",
                  "Private Equity Associate", "Credit Analyst", "Treasury Analyst", "M&A Analyst", "Valuation Analyst"]:
            self.assertEqual(cat(t), "finance", t)

    def test_dropped(self):
        for t in ["Data Analyst", "Business Analyst", "VP, Investment Banking", "Finance Manager", "Investment Sales Associate",
                  "Recruiting Associate, Finance", "Accounts Payable Specialist",
                  # back-office titles seen in the first real run (2026-11-10)
                  "Junior Accounts Payable Specialist (Product & Investment)", "Analyst, Banking Operations (Domestic)",
                  "Banking Services Operations Associate III - Non Real Estate Collateral", "Payroll Analyst",
                  "Loan Servicing Associate", "Wealth Client Service Associate", "Financial Data Analyst"]:
            self.assertIsNone(cat(t), t)
        self.assertNotIn(cat("Capital Markets Business Systems Analyst- Real Estate"), {"finance", "realestate"})


class Levels(unittest.TestCase):
    """Real estate, development and finance analyst: entry and mid level only. Software and quant keep every level."""

    def test_senior_and_staff_titles_are_dropped_for_the_new_categories(self):
        for t, tags in [("Senior Financial Analyst, FP&A", ()), ("Lead Credit Analyst", ()), ("VP, Equity Research Associate", ()),
                        ("Senior Associate, Acquisitions", RE), ("Senior Development Associate", RE),
                        ("Associate Director, Asset Management", RE), ("Principal, Investments Associate", RE),
                        ("Managing Director, Investment Banking Analyst Program", ()), ("Staff Accountant Analyst", ()),
                        ("Executive Director, Capital Markets Associate", RE), ("Sr. Real Estate Analyst", ())]:
            self.assertIsNone(cat(t, tags), t)

    def test_entry_and_mid_levels_are_kept(self):
        for t, tags, c in [("Financial Analyst", (), "finance"), ("Financial Analyst II", (), "finance"),
                           ("Investment Banking Associate", (), "finance"), ("Acquisitions Associate", RE, "realestate"),
                           ("Asset Management Analyst III", RE, "realestate"), ("Development Associate", RE, "development"),
                           ("2027 Summer Analyst - Investment Banking", (), "finance"), ("Junior Development Analyst", RE, "development")]:
            self.assertEqual(cat(t, tags), c, t)

    def test_software_and_quant_keep_every_level(self):
        self.assertEqual(cat("Senior Software Engineer"), "software")
        self.assertEqual(cat("Staff Software Engineer"), "software")
        self.assertEqual(cat("Principal Quant Researcher"), "quant")


class Tagging(unittest.TestCase):
    def test_every_exported_job_has_one_category_and_the_payload_counts_them(self):
        live = [
            {"company": "Acme", "tags": ["tech"], "source": "greenhouse", "key": "greenhouse:acme:1", "title": "Software Engineer",
             "location": "New York, NY", "url": "u", "posted": "2026-11-01", "salary": ""},
            {"company": "Hines", "tags": ["realestate"], "source": "workday", "key": "workday:hines:/j/2",
             "title": "Development Associate", "location": "Houston, TX", "url": "u", "posted": "2026-11-01", "salary": ""},
            {"company": "Hines", "tags": ["realestate"], "source": "workday", "key": "workday:hines:/j/3",
             "title": "Acquisitions Analyst", "location": "Chicago, IL", "url": "u", "posted": "2026-11-01", "salary": ""},
            {"company": "Bank", "tags": ["finance"], "source": "workday", "key": "workday:bank:/j/4",
             "title": "Investment Banking Analyst", "location": "San Francisco, CA", "url": "u", "posted": "2026-11-01", "salary": ""},
            {"company": "Bank", "tags": ["finance"], "source": "workday", "key": "workday:bank:/j/5",
             "title": "Leasing Agent", "location": "Austin, TX", "url": "u", "posted": "2026-11-01", "salary": ""},
        ]
        curated = [{"company": "Q", "tags": ["quant"], "source": "openquant", "key": "openquant:9", "title": "QR",
                    "location": "London", "url": "u", "posted": "2026-11-01", "salary": ""}]
        with tempfile.TemporaryDirectory() as t:
            a = Namespace(tag=[], no_openquant=True, no_builtin=True, seen=f"{t}/seen.json", out=f"{t}/jobs.json",
                          previous=None, prune_days=30, today=None, allow_drop=False)
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                payload, _s, _r = fj.build([], a, "2026-11-10", (live, curated, set(), [], 1))
        by_key = {j["key"]: j["category"] for j in payload["jobs"]}
        self.assertEqual(by_key, {"greenhouse:acme:1": "software", "workday:hines:/j/2": "development",
                                  "workday:hines:/j/3": "realestate", "workday:bank:/j/4": "finance",
                                  "openquant:9": "quant"})
        self.assertEqual(payload["categories"], {"software": 1, "quant": 1, "realestate": 1, "development": 1, "finance": 1})
        self.assertTrue(all(j["category"] in fj.CATEGORIES for j in payload["jobs"]))
        # the priority boost still works alongside categories: SF/CHI/NYC first
        self.assertEqual([j["priority"] for j in payload["jobs"]][:4], [True, True, True, False])
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
