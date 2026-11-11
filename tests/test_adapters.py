"""Adapters for Oracle Cloud HCM, SmartRecruiters and iCIMS, parsing real sample responses saved in tests/fixtures/
(fetched once from the live public endpoints, trimmed to a few postings, otherwise as received)."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_jobs as fj  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
ORACLE = json.loads((FIX / "oracle-jpmc.json").read_text())
SR = json.loads((FIX / "smartrecruiters-servicenow.json").read_text())
ICIMS_HTML = (FIX / "icims-msci.html").read_text()

JPM = {"name": "JPMorgan Chase", "ats": "oracle", "token": "jpmc", "host": "jpmc.fa.oraclecloud.com", "site": "CX_1001",
       "tags": ["finance"], "terms": ["analyst"]}
SN = {"name": "ServiceNow", "ats": "smartrecruiters", "token": "ServiceNow", "tags": ["tech"]}
MSCI = {"name": "MSCI", "ats": "icims", "token": "uscareers-msci", "tags": ["finance"]}


def quiet():
    return mock.patch.object(fj.time, "sleep")


class Oracle(unittest.TestCase):
    def test_parses_a_real_response(self):
        with mock.patch.object(fj, "fetch", return_value=ORACLE) as f, quiet():
            rows = fj.norm_oracle(JPM)
        url = f.call_args[0][0]
        self.assertIn("jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions", url)
        self.assertIn("siteNumber=CX_1001,keyword=analyst,limit=25,offset=0", url)
        first = ORACLE["items"][0]["requisitionList"][0]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["key"], f"oracle:jpmc:{first['Id']}")
        self.assertEqual(rows[0]["title"], first["Title"])
        self.assertEqual(rows[0]["location"], first["PrimaryLocation"])
        self.assertEqual(rows[0]["posted"], first["PostedDate"])
        self.assertEqual(rows[0]["url"], f"https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/{first['Id']}")

    def test_pages_until_the_total_and_dedups_across_terms(self):
        page1 = copy.deepcopy(ORACLE)
        page1["items"][0]["TotalJobsCount"] = 30
        page1["items"][0]["requisitionList"] = [dict(r, Id=str(i)) for i, r in enumerate(ORACLE["items"][0]["requisitionList"] * 7)][:25]
        page2 = copy.deepcopy(ORACLE)
        page2["items"][0]["TotalJobsCount"] = 30
        page2["items"][0]["requisitionList"] = [dict(r, Id=str(100 + i)) for i, r in enumerate(ORACLE["items"][0]["requisitionList"])]
        again = copy.deepcopy(page1)
        again["items"][0]["TotalJobsCount"] = 25
        with mock.patch.object(fj, "fetch", side_effect=[page1, page2, again]) as f, quiet():
            rows = fj.norm_oracle({**JPM, "terms": ["analyst", "associate"]})
        self.assertEqual(f.call_count, 3)  # 2 pages for "analyst" (30 total), then "associate" stops at its total
        self.assertEqual(len(rows), 29)    # the "associate" page repeats ids already seen: kept once

    def test_finance_preset_and_empty_response(self):
        with mock.patch.object(fj, "fetch", return_value=ORACLE) as f, quiet():
            fj.norm_oracle({**JPM, "terms": "finance"})
        self.assertEqual(f.call_count, len(fj.FINANCE_WORKDAY_TERMS))
        with mock.patch.object(fj, "fetch", return_value={"items": []}), self.assertRaises(ValueError):
            fj.norm_oracle(JPM)


class SmartRecruiters(unittest.TestCase):
    def test_parses_a_real_response(self):
        with mock.patch.object(fj, "fetch", return_value=SR) as f, quiet():
            rows = fj.norm_smartrecruiters(SN)
        self.assertIn("api.smartrecruiters.com/v1/companies/ServiceNow/postings?limit=100&offset=0", f.call_args[0][0])
        p = SR["content"][0]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["key"], f"smartrecruiters:ServiceNow:{p['id']}")
        self.assertEqual(rows[0]["title"], p["name"].strip())  # the real sample has a trailing space
        self.assertEqual(rows[0]["posted"], p["releasedDate"])
        self.assertEqual(rows[0]["url"], f"https://jobs.smartrecruiters.com/ServiceNow/{p['id']}")
        self.assertTrue(rows[0]["location"].startswith(p["location"]["city"]))

    def test_remote_and_paging(self):
        page1 = copy.deepcopy(SR)
        page1["totalFound"] = 150
        page1["content"] = [dict(p, id=str(i)) for i, p in enumerate(SR["content"] * 25)][:100]
        page2 = copy.deepcopy(SR)
        page2["content"] = [dict(SR["content"][0], id="x", location={"city": "Austin", "region": "TX", "country": "us", "remote": True})]
        with mock.patch.object(fj, "fetch", side_effect=[page1, page2]) as f, quiet():
            rows = fj.norm_smartrecruiters(SN)
        self.assertEqual(f.call_count, 2)
        self.assertEqual(len(rows), 101)
        self.assertEqual(rows[-1]["location"], "Remote - Austin, TX, US")
        self.assertIn("offset=100", f.call_args[0][0])

    def test_an_empty_or_odd_board_is_a_failure(self):
        for payload in ({"totalFound": 0, "content": []}, {"message": "not found"}):
            with mock.patch.object(fj, "fetch", return_value=payload), self.assertRaises(ValueError):
                fj.norm_smartrecruiters(SN)


class ICIMS(unittest.TestCase):
    def test_parses_a_real_page(self):
        rows, pages = fj.parse_icims(ICIMS_HTML)
        self.assertEqual(pages, (1, 1))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["id"], "6233")
        self.assertEqual(rows[0]["title"], "Program Manager for the Employee Productivity Program")
        self.assertEqual(rows[0]["posted"], "2026-11-10")
        self.assertEqual(rows[0]["location"], "San Francisco, CA, US")
        self.assertEqual(rows[0]["url"], "https://uscareers-msci.icims.com/jobs/6233/program-manager-for-the-employee-productivity-program/job")
        self.assertEqual(rows[1]["title"], "Intern – Data Transformation")  # HTML entities decoded

    def test_adapter_rows_paging_and_honest_user_agent(self):
        page = ICIMS_HTML.replace("Page 1 of 1", "Page 1 of 2")
        page2 = ICIMS_HTML.replace("Page 1 of 1", "Page 2 of 2").replace("/jobs/6233/", "/jobs/9999/")
        calls = []

        def fetch_html(url, ua=None):
            calls.append((url, ua))
            return page if len(calls) == 1 else page2

        with mock.patch.object(fj, "fetch_html", fetch_html), quiet():
            rows = fj.norm_icims(MSCI)
        self.assertEqual([u for u, _ in calls], ["https://uscareers-msci.icims.com/jobs/search?ss=1&in_iframe=1&pr=0",
                                                 "https://uscareers-msci.icims.com/jobs/search?ss=1&in_iframe=1&pr=1"])
        self.assertTrue(all(ua == fj.UA for _, ua in calls))
        self.assertEqual(len(rows), 4)  # 3 + the one new id on page 2
        self.assertEqual(rows[0]["key"], "icims:uscareers-msci:6233")

    def test_a_page_without_cards_is_a_failure(self):
        with mock.patch.object(fj, "fetch_html", return_value="<html>maintenance</html>"), self.assertRaises(ValueError):
            fj.norm_icims(MSCI)

    def test_locations(self):
        self.assertEqual(fj.icims_location("US-NY-New York"), "New York, NY, US")
        self.assertEqual(fj.icims_location("US-CA-San Francisco"), "San Francisco, CA, US")
        self.assertEqual(fj.icims_location("Remote"), "Remote")
        self.assertEqual(fj.icims_location("UK-London"), "UK-London")


class MoreRealSamples(unittest.TestCase):
    """The same parsers on other employers' real responses (saved by the research agents)."""

    def test_icims_header_location_variant(self):
        for name, first, loc, pages in [("icims-careers-kbhome.html", "Design Studio Consultant", "Meridian, ID, US", (1, 1)),
                                        ("icims-careers-stifel.html", "Bank Fraud Investigations Specialist", "Saint Louis, MO, US", (1, 3))]:
            rows, p = fj.parse_icims((FIX / name).read_text())
            self.assertEqual(p, pages, name)
            self.assertEqual(len(rows), 5, name)
            self.assertEqual((rows[0]["title"], rows[0]["location"]), (first, loc), name)

    def test_oracle_home_depot(self):
        data = json.loads((FIX / "oracle-hdep-CX.json").read_text())
        hd = {"name": "Home Depot", "ats": "oracle", "token": "hdep", "host": "hdep.fa.us2.oraclecloud.com", "site": "CX",
              "tags": ["finance"], "terms": ["analyst"]}
        with mock.patch.object(fj, "fetch", return_value=data), quiet():
            rows = fj.norm_oracle(hd)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["title"], "Portfolio Analyst")
        self.assertTrue(rows[0]["url"].startswith("https://hdep.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/"))

    def test_smartrecruiters_iqeq_and_public_storage(self):
        for name, token, first in [("smartrecruiters-IQEQ.json", "IQEQ", "Accountant 2, Fund Accounting"),
                                   ("smartrecruiters-PublicStorage.json", "PublicStorage", "Tax Senior Analyst")]:
            data = json.loads((FIX / name).read_text())
            with mock.patch.object(fj, "fetch", return_value=data), quiet():
                rows = fj.norm_smartrecruiters({"name": token, "ats": "smartrecruiters", "token": token, "tags": ["finance"]})
            self.assertEqual(len(rows), 5, name)
            self.assertEqual(rows[0]["title"], first, name)


SF_SWISSRE = (FIX / "successfactors-swissre.html").read_text()
SF_NOMURA = (FIX / "successfactors-nomura.html").read_text()
SF_FRASERS = (FIX / "successfactors-frasersproperty.html").read_text()
SWISSRE = {"name": "Swiss Re", "ats": "successfactors", "token": "swissre", "host": "careers.swissre.com", "tags": ["finance"]}


class SuccessFactors(unittest.TestCase):
    def test_table_layout_with_dates(self):
        rows, total = fj.parse_successfactors(SF_SWISSRE)
        self.assertEqual(total, 47)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[1], {"id": "1446545433", "path": "/job/New-York-Investment-Analyst%2C-Corporate-Development-NY-10001/1446545433/",
                                   "title": "Investment Analyst, Corporate Development", "location": "New York, NY, US",
                                   "posted": "2026-11-11"})

    def test_table_layout_without_dates_and_with_a_brand_prefix(self):
        rows, total = fj.parse_successfactors(SF_NOMURA)
        self.assertEqual(total, 135)
        self.assertEqual(rows[1]["title"], "Investment Banking Analyst")
        self.assertEqual(rows[1]["path"], "/Nomura/job/Central-Investment-Banking-Analyst-HK/1388005700/")
        self.assertEqual(rows[1]["posted"], "")
        self.assertTrue(rows[1]["location"].startswith("Central"))

    def test_tile_layout(self):
        rows, total = fj.parse_successfactors(SF_FRASERS)
        self.assertEqual(total, 49)
        self.assertEqual(len(rows), 5)
        self.assertEqual((rows[0]["id"], rows[0]["title"], rows[0]["location"]),
                         ("1456248233", "Financial Controller", "Australia, New South Wales"))

    def test_dates(self):
        self.assertEqual(fj.sf_date("7 Nov 2026"), "2026-11-07")
        self.assertEqual(fj.sf_date("Nov 9, 2026"), "2026-11-09")
        self.assertEqual(fj.sf_date("11 Nov 2026 "), "2026-11-11")
        self.assertEqual(fj.sf_date("yesterday"), "")

    def test_adapter_urls_paging_and_user_agent(self):
        page2 = SF_SWISSRE.replace("1446512633", "99").replace("1446545433", "98")  # same layout, other ids
        calls = []

        def fetch_html(url, ua=None):
            calls.append((url, ua))
            return SF_SWISSRE if len(calls) == 1 else page2

        with mock.patch.object(fj, "fetch_html", fetch_html), quiet():
            rows = fj.norm_successfactors(SWISSRE)
        self.assertTrue(calls[0][0].startswith("https://careers.swissre.com/search/?q=&startrow=0&sortColumn=referencedate"))
        self.assertIn("startrow=5", calls[1][0])  # advanced by the rows actually returned (the site's page size)
        self.assertTrue(all(ua == fj.UA for _, ua in calls))
        self.assertEqual(rows[1]["url"], "https://careers.swissre.com/job/New-York-Investment-Analyst%2C-Corporate-Development-NY-10001/1446545433/")
        self.assertEqual(rows[1]["key"], "successfactors:swissre:1446545433")
        self.assertEqual(len({r["key"] for r in rows}), len(rows))

    def test_terms_and_locale(self):
        calls = []
        with mock.patch.object(fj, "fetch_html", lambda url, ua=None: calls.append(url) or SF_SWISSRE.replace("<b>47</b>", "<b>5</b>")), quiet():
            fj.norm_successfactors({**SWISSRE, "terms": ["analyst", "associate"], "locale": "en_US"})
        self.assertEqual(len(calls), 2)
        self.assertIn("q=analyst", calls[0])
        self.assertIn("q=associate", calls[1])
        self.assertTrue(all("locale=en_US" in u for u in calls))

    def test_a_javascript_rendered_site_is_a_failure(self):
        with mock.patch.object(fj, "fetch_html", return_value="<html><div id='app'></div></html>"), self.assertRaises(ValueError):
            fj.norm_successfactors(SWISSRE)


class Registry(unittest.TestCase):
    def test_every_ats_has_an_adapter(self):
        self.assertEqual(set(fj.FETCHERS), {"greenhouse", "ashby", "lever", "workday", "oracle", "smartrecruiters", "icims",
                                            "successfactors"})


if __name__ == "__main__":
    unittest.main()
