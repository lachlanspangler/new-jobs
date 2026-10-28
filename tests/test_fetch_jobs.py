"""Unit tests for fetch_jobs.py — no network: every HTTP call is replaced with a fixture.

    python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_jobs as fj  # noqa: E402

GH = {"name": "Acme", "ats": "greenhouse", "token": "acme", "tags": ["tech"]}
ASH = {"name": "Bolt", "ats": "ashby", "token": "bolt", "tags": ["ai"]}
LEV = {"name": "Cog", "ats": "lever", "token": "cog", "tags": ["quant"]}
WD = {"name": "Dyn", "ats": "workday", "token": "dyn", "host": "wd5", "site": "External", "tags": ["tech"]}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def row(key, title="Software Engineer", company="Acme", location="New York, NY", source=None, first=None):
    r = {"company": company, "tags": ["tech"], "source": source or key.split(":")[0], "key": key, "title": title,
         "location": location, "url": "https://x", "posted": "2026-10-01", "salary": ""}
    if first:
        r.update(firstSeen=first, isNew=False, priority=True)
    return r


def args(tmp, **kw):
    a = Namespace(tag=[], no_openquant=True, no_builtin=True, seen=str(Path(tmp) / "seen.json"),
                  out=str(Path(tmp) / "jobs.json"), previous=None, prune_days=30, today=None)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


class Parsers(unittest.TestCase):
    def test_greenhouse(self):
        data = {"jobs": [{"id": 11, "title": " Software Engineer, Infra ", "location": {"name": "New York, NY"},
                          "absolute_url": "https://boards.greenhouse.io/acme/jobs/11",
                          "first_published": "2026-10-20T12:00:00-04:00",
                          "content": "&lt;p&gt;Pay: $150,000 - $200,000&lt;/p&gt;"}]}
        with mock.patch.object(fj, "fetch", return_value=data) as f:
            out = fj.norm_greenhouse(GH)
        self.assertIn("boards/acme/jobs?content=true", f.call_args[0][0])
        self.assertEqual(out[0]["key"], "greenhouse:acme:11")
        self.assertEqual(out[0]["title"], "Software Engineer, Infra")
        self.assertEqual(out[0]["location"], "New York, NY")
        self.assertEqual(out[0]["posted"], "2026-10-20T12:00:00-04:00")
        self.assertEqual(out[0]["salary"], "$150,000 - $200,000")

    def test_ashby_skips_unlisted_and_reads_compensation(self):
        data = {"jobs": [
            {"id": "a1", "title": "ML Engineer", "location": "San Francisco", "jobUrl": "https://jobs.ashbyhq.com/bolt/a1",
             "publishedAt": "2026-10-21", "compensation": {"scrapeableCompensationSalarySummary": "$180K – $240K"}},
            {"id": "a2", "title": "Hidden", "isListed": False},
            {"id": "a3", "title": "Backend Engineer", "isRemote": True, "applyUrl": "https://apply/a3"}]}
        with mock.patch.object(fj, "fetch", return_value=data):
            out = fj.norm_ashby(ASH)
        self.assertEqual([r["key"] for r in out], ["ashby:bolt:a1", "ashby:bolt:a3"])
        self.assertEqual(out[0]["salary"], "$180K – $240K")
        self.assertEqual(out[1]["location"], "Remote")
        self.assertEqual(out[1]["url"], "https://apply/a3")

    def test_lever_dates_and_salary_range(self):
        data = [{"id": "l1", "text": "Quant Developer", "categories": {"location": "Chicago"},
                 "hostedUrl": "https://jobs.lever.co/cog/l1", "createdAt": 1761000000000,
                 "salaryRange": {"min": 150000, "max": 250000, "currency": "USD"}},
                {"id": "l2", "text": "Quant Researcher", "createdAt": None,
                 "salaryRange": {"min": 100000, "max": 120000, "currency": "GBP"}}]
        with mock.patch.object(fj, "fetch", return_value=data):
            out = fj.norm_lever(LEV)
        self.assertEqual(out[0]["salary"], "$150,000 – 250,000")
        self.assertTrue(out[0]["posted"].startswith("2025-10-20T"))
        self.assertEqual(out[1]["posted"], "")
        self.assertEqual(out[1]["salary"], "GBP 100,000 – 120,000")

    def test_lever_non_list_is_empty(self):
        with mock.patch.object(fj, "fetch", return_value={"ok": False}):
            self.assertEqual(fj.norm_lever(LEV), [])

    def test_workday_dedups_across_terms_and_dates(self):
        page = {"total": 2, "jobPostings": [
            {"title": "Software Engineer", "externalPath": "/job/NYC/SWE_1", "locationsText": "New York",
             "postedOn": "Posted Today"},
            {"title": "Quant Developer", "externalPath": "/job/CHI/QD_2", "postedOn": "Posted 3 Days Ago"}]}
        bodies = []

        def urlopen(req, timeout=0):
            bodies.append(json.loads(req.data))
            return FakeResp(json.dumps(page).encode())

        with mock.patch.object(fj.urllib.request, "urlopen", urlopen), mock.patch.object(fj.time, "sleep"):
            out = fj.norm_workday(WD)
        self.assertEqual(len(out), 2)  # the same two postings come back for every term: kept once
        self.assertGreater(len(bodies), 2)
        self.assertEqual(out[0]["key"], "workday:dyn:/job/NYC/SWE_1")
        self.assertEqual(out[0]["url"], "https://dyn.wd5.myworkdayjobs.com/en-US/External/job/NYC/SWE_1")
        self.assertEqual(out[0]["posted"], fj.dt.date.today().isoformat())

    def test_builtin_parses_cards_and_raises_when_board_is_down(self):
        card = ('<div data-id="job-card" track-job-id="555" data-alias="/job/swe/555">'
                '<a data-id="job-card-title" href="#">Senior Software Engineer</a>'
                '<a data-id="company-title"><span>Acme &amp; Co</span></a><span>Posted 2 Days Ago</span></div>')
        with mock.patch.object(fj, "fetch_html", side_effect=[card, ""]), mock.patch.object(fj.time, "sleep"):
            out = fj.norm_builtin("https://www.builtinnyc.com", "New York")
        self.assertEqual(out[0]["key"], "builtin:555")
        self.assertEqual(out[0]["company"], "Acme & Co")
        self.assertEqual(out[0]["url"], "https://www.builtinnyc.com/job/swe/555")
        self.assertEqual(fj.board_of(out[0]), "builtin:New York")
        err = fj.urllib.error.URLError("down")
        with mock.patch.object(fj, "fetch_html", side_effect=err), self.assertRaises(fj.urllib.error.URLError):
            fj.norm_builtin("https://www.builtinnyc.com", "New York")

    def test_openquant_unions_filters(self):
        def page(params):
            return [{"ID": 1, "CompanyName": "Q", "Position": "Quant Trader", "MinSalary": 150000,
                     "MaxSalary": 250000, "Location": "Chicago"}] + ([{"ID": 2, "Position": "QR"}] if params else [])

        with mock.patch.object(fj, "_oq_page", page), mock.patch.object(fj.time, "sleep"):
            out = fj.fetch_openquant()
        self.assertEqual(sorted(r["key"] for r in out), ["openquant:1", "openquant:2"])
        self.assertEqual(next(r for r in out if r["key"] == "openquant:1")["salary"], "$150K - $250K")


class Filters(unittest.TestCase):
    def test_role_filter(self):
        keep = ["Software Engineer", "C++ Developer", "Python Engineer", "Quant Researcher", "Quantitative Trader",
                "Trade Desk Operations", "Site Reliability Engineer", "Machine Learning Engineer", "Backend Engineer"]
        drop = ["Sales Engineer", "Solutions Engineer", "Product Manager", "Recruiter", "Mechanical Engineer",
                "Hardware Engineer", "Account Executive", "Customer Success Engineer", "Office Manager"]
        for t in keep:
            self.assertTrue(fj.is_target(t), t)
        for t in drop:
            self.assertFalse(fj.is_target(t), t)

    def test_priority_cities_and_salary_text(self):
        self.assertTrue(fj.PRIORITY_RE.search("New York, NY"))
        self.assertTrue(fj.PRIORITY_RE.search("SF Bay Area"))
        self.assertFalse(fj.PRIORITY_RE.search("Austin, TX"))
        self.assertEqual(fj.extract_salary("range $120k - $160k plus"), "$120k - $160k")
        self.assertEqual(fj.extract_salary("no pay info"), "")


class Seen(unittest.TestCase):
    def test_new_job_gets_today_and_known_job_keeps_first_seen(self):
        seen = {"greenhouse:acme:1": ["2026-09-01", "2026-10-01"]}
        rows = [row("greenhouse:acme:1"), row("greenhouse:acme:2")]
        fj.mark_seen(seen, rows, "2026-10-28")
        self.assertEqual(seen["greenhouse:acme:1"], ["2026-09-01", "2026-10-28"])
        self.assertEqual(seen["greenhouse:acme:2"], ["2026-10-28", "2026-10-28"])
        self.assertEqual([(r["firstSeen"], r["isNew"]) for r in rows],
                         [("2026-09-01", False), ("2026-10-28", True)])

    def test_carried_rows_do_not_refresh_last_seen(self):
        seen = {"greenhouse:acme:1": ["2026-09-01", "2026-10-01"]}
        fj.mark_seen(seen, [row("greenhouse:acme:1")], "2026-10-28", live=False)
        self.assertEqual(seen["greenhouse:acme:1"], ["2026-09-01", "2026-10-01"])

    def test_old_format_upgrades_with_clock_starting_today(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "seen.json"
            p.write_text(json.dumps({"k": "2026-09-01", "n": ["2026-10-01", "2026-10-02"]}))
            self.assertEqual(fj.load_seen(p, {}, "2026-10-28"),
                             {"k": ["2026-09-01", "2026-10-28"], "n": ["2026-10-01", "2026-10-02"]})

    def test_missing_state_seeds_from_previous_site(self):
        prev = {"generated_at": "2026-10-12T03:22:02+00:00",
                "jobs": [row("greenhouse:acme:1", first="2026-09-03")]}
        self.assertEqual(fj.load_seen("/nonexistent/seen.json", prev, "2026-10-28"),
                         {"greenhouse:acme:1": ["2026-09-03", "2026-10-12"]})

    def test_prune_after_30_days_gone_and_return_is_new(self):
        seen = {"greenhouse:acme:old": ["2026-08-01", "2026-09-27"],   # gone 31 days -> pruned
                "greenhouse:acme:edge": ["2026-08-01", "2026-09-28"],  # gone exactly 30 days -> kept
                "greenhouse:acme:live": ["2026-08-01", "2026-10-28"]}
        self.assertEqual(fj.prune_seen(seen, "2026-10-28", set()), 1)
        self.assertNotIn("greenhouse:acme:old", seen)
        back = [row("greenhouse:acme:old")]
        fj.mark_seen(seen, back, "2026-10-29")
        self.assertTrue(back[0]["isNew"])
        self.assertEqual(back[0]["firstSeen"], "2026-10-29")

    def test_prune_never_touches_a_board_that_failed(self):
        seen = {"greenhouse:acme:1": ["2026-01-01", "2026-01-02"], "builtin:9": ["2026-01-01", "2026-01-02"],
                "ashby:bolt:1": ["2026-01-01", "2026-01-02"]}
        fj.prune_seen(seen, "2026-10-28", {"greenhouse:acme", "builtin"})
        self.assertEqual(sorted(seen), ["builtin:9", "greenhouse:acme:1"])


class Run(unittest.TestCase):
    """build(): the whole run after the network, with a fake fetch result."""

    def fetched(self, live, curated=(), failed=(), attempted=4):
        return list(live), list(curated), set(failed), [f"{b}: boom" for b in failed], attempted

    def test_broken_board_keeps_last_good_jobs(self):
        with tempfile.TemporaryDirectory() as t:
            prev = {"generated_at": "2026-10-27T10:00:00+00:00", "jobs": [
                row("greenhouse:acme:1", first="2026-10-01"), row("ashby:bolt:7", company="Bolt", first="2026-10-02")]}
            Path(t, "prev.json").write_text(json.dumps(prev))
            Path(t, "seen.json").write_text(json.dumps({"greenhouse:acme:1": ["2026-10-01", "2026-10-27"],
                                                        "ashby:bolt:7": ["2026-10-02", "2026-10-27"]}))
            a = args(t, previous=str(Path(t, "prev.json")))
            payload, seen, rep = fj.build([GH, ASH], a, "2026-10-28",
                                          self.fetched([row("greenhouse:acme:1")], failed={"ashby:bolt"}))
        keys = [j["key"] for j in payload["jobs"]]
        self.assertEqual(sorted(keys), ["ashby:bolt:7", "greenhouse:acme:1"])
        self.assertEqual(rep["carried"], 1)
        self.assertEqual(seen["ashby:bolt:7"], ["2026-10-02", "2026-10-27"])  # not refreshed: not confirmed live
        self.assertEqual(seen["greenhouse:acme:1"], ["2026-10-01", "2026-10-28"])

    def test_a_closed_posting_leaves_the_site(self):
        with tempfile.TemporaryDirectory() as t:
            prev = {"jobs": [row("greenhouse:acme:1", first="2026-10-01"), row("greenhouse:acme:2", first="2026-10-01")]}
            Path(t, "prev.json").write_text(json.dumps(prev))
            payload, _seen, _ = fj.build([GH], args(t, previous=str(Path(t, "prev.json"))), "2026-10-28",
                                         self.fetched([row("greenhouse:acme:1")]))
        self.assertEqual([j["key"] for j in payload["jobs"]], ["greenhouse:acme:1"])

    def test_title_filter_curated_rows_and_counts(self):
        with tempfile.TemporaryDirectory() as t:
            live = [row("greenhouse:acme:1"), row("greenhouse:acme:2", title="Sales Engineer")]
            curated = [row("openquant:5", title="QR", source="openquant", location="London")]
            payload, _s, rep = fj.build([GH], args(t), "2026-10-28", self.fetched(live, curated))
        self.assertEqual(sorted(j["key"] for j in payload["jobs"]), ["greenhouse:acme:1", "openquant:5"])
        self.assertEqual((payload["count"], payload["new_today"]), (2, 2))
        self.assertEqual(payload["jobs"][0]["key"], "greenhouse:acme:1")  # priority city first
        self.assertEqual(set(payload["jobs"][0]), {"company", "tags", "source", "key", "title", "location", "url",
                                                  "posted", "salary", "firstSeen", "isNew", "priority"})

    def test_most_boards_failing_aborts_without_writing(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit) as e:
                fj.build([GH, ASH, LEV], args(t), "2026-10-28",
                         self.fetched([row("greenhouse:acme:1")], failed={"ashby:bolt", "lever:cog", "x:y"}))
            self.assertEqual(e.exception.code, 2)
            self.assertFalse(Path(t, "seen.json").exists())

    def test_no_roles_aborts(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaises(SystemExit):
            fj.build([GH], args(t), "2026-10-28", self.fetched([row("greenhouse:acme:1", title="Recruiter")]))

    def test_tag_runs_never_prune(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "seen.json").write_text(json.dumps({"lever:cog:1": ["2026-01-01", "2026-01-01"]}))
            _p, seen, rep = fj.build([GH], args(t, tag=["tech"]), "2026-10-28", self.fetched([row("greenhouse:acme:1")]))
        self.assertIn("lever:cog:1", seen)
        self.assertEqual(rep["pruned"], 0)

    def test_collect_survives_any_exception_from_a_board(self):
        def boom(_c):
            raise RuntimeError("unexpected payload")

        with mock.patch.dict(fj.FETCHERS, {"greenhouse": boom, "ashby": lambda c: [row("ashby:bolt:1")]}), \
                mock.patch.object(fj.time, "sleep"):
            live, _cur, failed, errors, attempted = fj.collect([GH, ASH], args("/tmp"))
        self.assertEqual(failed, {"greenhouse:acme"})
        self.assertEqual([r["key"] for r in live], ["ashby:bolt:1"])
        self.assertEqual(attempted, 2)
        self.assertIn("unexpected payload", errors[0])

    def test_main_writes_both_files_and_step_summary(self):
        with tempfile.TemporaryDirectory() as t:
            summ = Path(t, "summary.md")
            fake = ([row("greenhouse:acme:1")], [], set(), [], 1)
            with mock.patch.object(fj, "collect", return_value=fake), \
                    mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summ)}), \
                    mock.patch("sys.stdout", new_callable=io.StringIO):
                fj.main(["--seen", f"{t}/s/seen.json", "--out", f"{t}/site/jobs.json", "--today", "2026-10-28"])
            self.assertEqual(json.loads(Path(t, "s/seen.json").read_text()),
                             {"greenhouse:acme:1": ["2026-10-28", "2026-10-28"]})
            self.assertEqual(json.loads(Path(t, "site/jobs.json").read_text())["count"], 1)
            self.assertIn("| matched | 1 |", summ.read_text())


if __name__ == "__main__":
    unittest.main()
