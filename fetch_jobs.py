#!/usr/bin/env python3
"""new-jobs: pull the newest software / quant roles across Greenhouse, Ashby,
and Lever boards, keep target roles, prioritize SF/Chicago/NYC, and export a
static docs/jobs.json for the site. Standard library only.

Roles kept: software / C++ / Python engineers, quant developer, quant
researcher, quant, trade-desk operations (and adjacent SWE titles).

Usage:
  python3 fetch_jobs.py            # fetch, update seen store, export site data
  python3 fetch_jobs.py --tag ai   # limit to a company tag (repeatable)
  python3 fetch_jobs.py --seen state/seen.json --previous state/jobs.json --out _site/jobs.json   # CI

State (seen.json): key -> [first_seen, last_seen] ISO dates in local time (TZ env; CI uses America/Chicago).
A posting gone from every board for --prune-days (30) is forgotten; if it comes back it is new again.
A board that fails to fetch is skipped and logged, and its jobs from --previous are carried forward.
Exit 2 (nothing written) if most boards fail or no roles come back, so a bad run never replaces a good site.
"""

from __future__ import annotations
import argparse, datetime as dt, html, json, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEEN_PATH = ROOT / "seen.json"          # key -> first-seen ISO date
DOCS = ROOT / "docs"
UA = "new-jobs/1.0 (personal job search)"
PACING = 0.25
MAX_EXPORT = 15000
PRUNE_DAYS = 30
FAIL_LIMIT = 0.5          # more than this share of boards failing aborts the run
DROP_LIMIT = 0.5          # fewer than this share of the previous run's roles aborts the run (silent mass outage)

INCLUDE_RE = re.compile(
    r"\b(software|developer|engineer|engineering|swe|sde|programmer|back[\s-]?end|"
    r"front[\s-]?end|full[\s-]?stack|platform|infrastructure|systems?|sre|devops|"
    r"reliability|machine\s*learning|\bml\b|\bai\b|quant|quantitative|trader|trading|"
    r"trade\s*desk|desk\s*operations)\b|c\+\+|python",
    re.IGNORECASE,
)
EXCLUDE_RE = re.compile(
    r"\b(sales|solutions?|support|customer|success|account\s+executive|marketing|recruit|"
    r"talent|human\s+resources|\bhr\b|legal|counsel|designer|design\b|product\s+manager|"
    r"program\s+manager|project\s+manager|mechanical|electrical|hardware|firmware|biomedical|"
    r"chemical|civil|clinical|nurse|technician|manufacturing|facilities)\b",
    re.IGNORECASE,
)
PRIORITY_RE = re.compile(r"san francisco|\bsf\b|bay area|chicago|new york|\bnyc\b|manhattan", re.IGNORECASE)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*years", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SALARY_RE = re.compile(r"\$\s?\d{2,3}(?:,\d{3})?\s?[kK]?\s*(?:-|–|—|to)\s*\$?\s?\d{2,3}(?:,\d{3})?\s?[kK]?")


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def strip_html(s):
    return html.unescape(TAG_RE.sub(" ", s or ""))


def extract_salary(text):
    m = SALARY_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def is_target(title):
    return bool(INCLUDE_RE.search(title)) and not EXCLUDE_RE.search(title)


def norm_greenhouse(c):
    data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{c['token']}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        desc = strip_html(j.get("content", ""))
        out.append(_row(c, "greenhouse", j["id"], j.get("title", ""),
                        (j.get("location") or {}).get("name") or "",
                        j.get("absolute_url") or "",
                        j.get("first_published") or j.get("updated_at") or "",
                        extract_salary(desc)))
    return out


def norm_ashby(c):
    data = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{c['token']}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        comp = j.get("compensation") or {}
        out.append(_row(c, "ashby", j["id"], j.get("title", ""),
                        j.get("location") or ("Remote" if j.get("isRemote") else ""),
                        j.get("jobUrl") or j.get("applyUrl") or "",
                        j.get("publishedAt") or "",
                        comp.get("scrapeableCompensationSalarySummary") or comp.get("compensationTierSummary") or ""))
    return out


def norm_lever(c):
    data = fetch(f"https://api.lever.co/v0/postings/{c['token']}?mode=json")
    out = []
    if not isinstance(data, list):
        raise ValueError(f"lever {c['token']}: expected a list of postings, got {type(data).__name__}")
    for p in data:
        created = p.get("createdAt")
        posted = dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc).isoformat() if isinstance(created, (int, float)) else ""
        sr = p.get("salaryRange") or {}
        salary = ""
        if sr.get("min") and sr.get("max"):
            cur = sr.get("currency") or "USD"
            sym = "$" if cur == "USD" else cur + " "
            salary = f"{sym}{int(sr['min']):,} – {int(sr['max']):,}"
        out.append(_row(c, "lever", p["id"], p.get("text", ""),
                        (p.get("categories") or {}).get("location") or "",
                        p.get("hostedUrl") or p.get("applyUrl") or "", posted,
                        salary or extract_salary(p.get("descriptionPlain") or "")))
    return out


def _row(c, source, jid, title, loc, url, posted, salary):
    return {"company": c["name"], "tags": c.get("tags", []), "source": source,
            "key": f"{source}:{c['token']}:{jid}", "title": (title or "").strip(),
            "location": loc, "url": url, "posted": posted, "salary": salary}


def workday_date(txt):
    t = (txt or "").lower()
    today = dt.date.today()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return (today - dt.timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\+?\s*month", t)
    if m:
        return (today - dt.timedelta(days=30 * int(m.group(1)))).isoformat()
    return ""


def norm_workday(c):
    host, tenant, site = c["host"], c["token"], c["site"]
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    seen, out = set(), []
    terms = ("software engineer", "c++", "python", "quant", "developer", "research", "data engineer", "trading")
    for term in terms:  # query relevant roles server-side, then dedup
        for offset in range(0, 100, 20):
            body = json.dumps({"limit": 20, "offset": offset, "searchText": term, "appliedFacets": {}}).encode()
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
            postings = data.get("jobPostings") or []
            for jp in postings:
                path = jp.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                out.append(_row(c, "workday", path, jp.get("title", ""),
                                jp.get("locationsText") or "", f"{base}/en-US/{site}{path}",
                                workday_date(jp.get("postedOn")), ""))
            if not postings or offset + 20 >= (data.get("total") or 0):
                break
            time.sleep(0.1)
    return out


FETCHERS = {"greenhouse": norm_greenhouse, "ashby": norm_ashby, "lever": norm_lever, "workday": norm_workday}

# --- openquant.co: a curated quant job board (Next.js + Supabase, server-rendered).
# It caps the unfiltered feed at 25 and ignores ?page, but server-side filters each
# return their COMPLETE set, so we union across filter values to recover every role.
OQ_URL = "https://openquant.co/"
OQ_NEXT_RE = re.compile(r'__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
OQ_FILTERS = [
    ("companyType", ["Hedge Fund", "Prop Trading", "Proprietary Trading", "Market Maker",
                     "Asset Manager", "Investment Bank", "Bank", "Fintech", "Crypto",
                     "Insurance", "Pension Fund", "Consulting", "Technology", "Other"]),
    ("level", ["Internship", "Entry Level", "Mid Level", "Senior Level", "Director", "Manager"]),
    ("keywords", ["Quantitative Researcher", "Quantitative Developer", "Quantitative Analyst",
                  "Quantitative Trader", "Software Engineer", "Data Scientist",
                  "Machine Learning", "Trader", "Research"]),
]


def _oq_page(params):
    import urllib.parse
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(OQ_URL + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        m = OQ_NEXT_RE.search(r.read().decode("utf-8"))
    if not m:  # page structure changed or a challenge page: an outage, not "no jobs"
        raise ValueError("openquant.co: no __NEXT_DATA__ in page")
    return json.loads(m.group(1))["props"]["pageProps"].get("data", [])


def _oq_salary(j):
    lo, hi = j.get("MinSalary"), j.get("MaxSalary")
    if lo and hi:
        return f"${round(lo/1000)}K - ${round(hi/1000)}K"
    return ""


# --- Built In city job boards (SF, NYC). Server-rendered HTML, robots.txt allows
# /jobs pagination (only ?search= queries are disallowed). Cards expose company,
# title, job id, and a "Posted/Reposted N ago" label. All roles are in-city.
BUILTIN_SITES = [("https://www.builtinsf.com", "San Francisco"),
                 ("https://www.builtinnyc.com", "New York")]
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
BI_TITLE_RE = re.compile(r'data-id="job-card-title"[^>]*>([^<]+)</a>')
BI_ID_RE = re.compile(r'track-job-id="(\d+)"')
BI_CO_RE = re.compile(r'data-id="company-title".*?<span>([^<]+)</span>', re.S)
BI_PATH_RE = re.compile(r'data-alias="(/job/[^"]+)"')
BI_POSTED_RE = re.compile(r'>([^<]*(?:Ago|Today))</span>')


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def builtin_date(txt):
    t = (txt or "").lower()
    today = dt.date.today()
    if any(w in t for w in ("today", "minute", "hour", "just")):
        return today.isoformat()
    if "yesterday" in t:
        return (today - dt.timedelta(days=1)).isoformat()
    for unit, days in (("day", 1), ("week", 7), ("month", 30)):
        m = re.search(rf"(\d+)\s*{unit}", t)
        if m:
            return (today - dt.timedelta(days=int(m.group(1)) * days)).isoformat()
    return ""


def norm_builtin(base, city, pages=6):
    out, seen = [], set()
    for p in range(1, pages + 1):
        try:
            html_ = fetch_html(f"{base}/jobs?page={p}")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
            if p == 1:
                raise  # the whole board is down: let the caller carry its last good jobs forward
            break
        blocks = html_.split('data-id="job-card"')[1:]
        if not blocks:
            if p == 1:  # a 200 with no job cards (bot challenge, redesign) is an outage, not "no jobs"
                raise ValueError(f"{base}: no job cards on page 1")
            break
        for b in blocks:
            mid = BI_ID_RE.search(b)
            mti = BI_TITLE_RE.search(b)
            if not mid or not mti or mid.group(1) in seen:
                continue
            seen.add(mid.group(1))
            mpath = BI_PATH_RE.search(b)
            mco = BI_CO_RE.search(b)
            mpost = BI_POSTED_RE.search(b)
            out.append({
                "company": html.unescape(mco.group(1).strip()) if mco else "?",
                "tags": ["tech"], "source": "builtin",
                "key": f"builtin:{mid.group(1)}",
                "title": html.unescape(mti.group(1).strip()),
                "location": city,
                "url": base + (mpath.group(1) if mpath else f"/job/{mid.group(1)}"),
                "posted": builtin_date(mpost.group(1) if mpost else ""),
                "salary": "",
            })
        time.sleep(PACING)
    return out


def fetch_openquant():
    """Return normalized quant rows from openquant.co (unioned across filter values)."""
    rows = {}
    def add(items):
        for j in items:
            jid = j.get("ID")
            if jid and jid not in rows:
                rows[jid] = j
    add(_oq_page({}))
    for field, values in OQ_FILTERS:
        for v in values:
            try:
                add(_oq_page({field: v}))
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
                pass
            time.sleep(0.2)
    out = []
    for j in rows.values():
        loc = j.get("Location") or (j.get("Country") or "")
        pos_type = j.get("PositionType") or ""
        title = j.get("Position") or ""
        out.append({
            "company": j.get("CompanyName") or "?",
            "tags": ["quant"],
            "source": "openquant",
            "key": f"openquant:{j.get('ID')}",
            "title": title.strip(),
            "location": loc,
            "url": j.get("ApplicationUrl") or "",
            "posted": j.get("PostedDate") or "",
            "salary": _oq_salary(j),
        })
    return out


# --- state: first/last-seen dates, pruning, broken-board carry-forward ----------------------------

def board_of(row):
    """The board a row came from: 'greenhouse:<token>', 'builtin:<city>', 'openquant'."""
    src = row["key"].split(":", 1)[0]
    if src == "builtin":
        return f"builtin:{row.get('location') or ''}"
    if src == "openquant":
        return "openquant"
    return ":".join(row["key"].split(":")[:2])


def key_guard(key):
    """Coarse board of a seen.json key (builtin keys don't carry their city, so all of builtin is one guard)."""
    parts = key.split(":")
    return parts[0] if parts[0] in ("builtin", "openquant") else ":".join(parts[:2])


def guard_of(board):
    return board.split(":", 1)[0] if board.startswith("builtin:") else board


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}); fix or delete it (CI: the state branch) and rerun")


def load_seen(path, previous, today):
    """seen.json -> {key: [first, last]}. Upgrades the old {key: first} format (last-seen unknown, so the 30-day
    clock starts today), and seeds from the previous jobs.json when there is no state at all (first CI run)."""
    raw = load_json(path, None)
    if raw is None:
        seeded = {}
        try:  # generated_at is UTC; every other date here is local (TZ)
            gen = dt.datetime.fromisoformat(previous["generated_at"]).astimezone().date().isoformat()
        except (KeyError, TypeError, ValueError):
            gen = today
        for j in previous.get("jobs", []):
            if j.get("key") and j.get("firstSeen"):
                seeded[j["key"]] = [j["firstSeen"], gen]
        return seeded
    return {k: ([v, today] if isinstance(v, str) else [v[0], v[1]]) for k, v in raw.items()}


def mark_seen(seen, rows, today, live=True):
    """Record first/last-seen; set firstSeen/isNew on each row. A key not in seen (never seen, or pruned) is new."""
    for j in rows:
        ent = seen.get(j["key"])
        if ent is None:
            ent = seen[j["key"]] = [today, today]
        elif live:
            ent[1] = today
        j["firstSeen"] = ent[0]
        j["isNew"] = ent[0] == today


def prune_seen(seen, today, failed_guards, days=PRUNE_DAYS):
    """Forget postings gone from every board for `days`+ days. Never prunes a board that failed this run."""
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    drop = [k for k, (_first, last) in seen.items() if last < cutoff and key_guard(k) not in failed_guards]
    for k in drop:
        del seen[k]
    return len(drop)


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def annotate(level, msg):
    """GitHub Actions annotation when running in CI, plain line otherwise."""
    print(f"::{level}::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"{level}: {msg}")


def collect(companies, args):
    """Fetch every board. Returns (rows_before_title_filter, curated_rows, failed_boards, errors, attempted)."""
    all_jobs, curated, failed, errors, attempted = [], [], set(), [], 0
    for c in companies:
        attempted += 1
        try:
            all_jobs.extend(FETCHERS[c["ats"]](c))
        except Exception as e:  # one broken board never fails the run
            failed.add(f"{c['ats']}:{c['token']}")
            errors.append(f"{c['name']}: {e}")
        time.sleep(PACING)

    # optional per-company location allow-list (e.g. SpaceX -> California only)
    loc_filters = {c["name"]: re.compile(c["onlyLocations"], re.IGNORECASE)
                   for c in companies if c.get("onlyLocations")}
    if loc_filters:
        all_jobs = [j for j in all_jobs if j["company"] not in loc_filters
                    or loc_filters[j["company"]].search(j.get("location") or "")]

    tags = {t.lower() for t in args.tag}
    if not args.no_builtin and (not tags or "tech" in tags):  # Built In SF/NYC (filtered to target roles later)
        for base, city in BUILTIN_SITES:
            attempted += 1
            try:
                rows = norm_builtin(base, city)
                all_jobs.extend(rows)
                print(f"{base}: +{len(rows)} listings")
            except Exception as e:
                failed.add(f"builtin:{city}")
                errors.append(f"{base}: {e}")

    # openquant.co is already a curated quant board — its roles skip the title filter
    if not args.no_openquant and (not tags or "quant" in tags):
        attempted += 1
        try:
            curated = fetch_openquant()
            print(f"openquant.co: +{len(curated)} quant roles")
        except Exception as e:
            failed.add("openquant")
            errors.append(f"openquant.co: {e}")
    return all_jobs, curated, failed, errors, attempted


def build(companies, args, today, fetched=None):
    """Everything after the network: returns (payload, seen, report) or raises SystemExit(2) on a bad run."""
    all_jobs, curated, failed, errors, attempted = fetched if fetched is not None else collect(companies, args)
    previous = load_json(args.previous, {}) if args.previous else {}

    def abort(msg):
        for e in errors:  # name the failures: this is the run the owner will open to diagnose
            annotate("warning", f"board failed: {e}")
        annotate("error", f"{msg} — keeping the last good site and state")
        raise SystemExit(2)

    if attempted and len(failed) / attempted > FAIL_LIMIT:
        abort(f"{len(failed)} of {attempted} boards failed")

    matched = [j for j in all_jobs if is_target(j["title"])] + curated
    live_keys = {j["key"] for j in matched}
    seen = load_seen(args.seen, previous, today)
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=args.prune_days)).isoformat()
    candidates = [j for j in previous.get("jobs", []) if board_of(j) in failed and j.get("key") not in live_keys]
    # carry a broken board's last good jobs, but only while they were confirmed live within the prune window:
    # a board that stays broken must not keep long-closed postings on the site forever
    carried = [j for j in candidates if j.get("key") in seen and seen[j["key"]][1] >= cutoff]
    for b in sorted({board_of(j) for j in candidates} - {board_of(j) for j in carried}):
        annotate("warning", f"{b} has failed for {args.prune_days}+ days; its old jobs are no longer shown")
    if not matched and not carried:
        abort("no target roles came back")
    prev_count = previous.get("count") or 0
    if not args.tag and not args.allow_drop and prev_count and len(matched) + len(carried) < DROP_LIMIT * prev_count:
        abort(f"only {len(matched) + len(carried):,} roles vs {prev_count:,} last run (rerun with --allow-drop "
              "if that's real)")

    before = len(seen)
    mark_seen(seen, matched, today)
    mark_seen(seen, carried, today, live=False)
    added = len(seen) - before
    pruned = prune_seen(seen, today, {guard_of(b) for b in failed}, args.prune_days) if not args.tag else 0

    rows = matched + carried
    for j in rows:
        j["priority"] = bool(PRIORITY_RE.search(j.get("location") or ""))
    rows.sort(key=lambda j: (j["priority"], j.get("posted") or ""), reverse=True)  # newest first, cities boosted

    export = rows[:MAX_EXPORT]  # the top MAX_EXPORT, but always keep every openquant/builtin role
    if len(rows) > MAX_EXPORT:
        have = {j["key"] for j in export}
        export += [j for j in rows[MAX_EXPORT:] if j["source"] in ("openquant", "builtin") and j["key"] not in have]
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(rows),
        "new_today": sum(1 for j in rows if j["isNew"]),
        "companies": len(companies),
        "jobs": [{k: j.get(k, "" if k not in ("tags",) else []) for k in (
            "company", "tags", "source", "key", "title", "location", "url", "posted", "salary",
            "firstSeen", "isNew", "priority")} for j in export],
    }
    report = {"live": len(all_jobs) + len(curated), "matched": len(matched), "carried": len(carried),
              "new_today": payload["new_today"], "exported": len(export), "seen_before": before,
              "seen_added": added, "pruned": pruned, "seen_after": len(seen), "failed": sorted(failed),
              "errors": errors, "attempted": attempted}
    return payload, seen, report


def summarize(report, companies):
    r = report
    line = (f"{r['live']} live postings -> {r['matched']} target roles ({r['new_today']} new today) across "
            f"{companies} companies; carried {r['carried']} from {len(r['failed'])} failed boards; "
            f"seen {r['seen_before']} -> {r['seen_after']} (+{r['seen_added']}, pruned {r['pruned']})")
    print(line)
    for e in r["errors"]:
        annotate("warning", f"board skipped, last good jobs kept: {e}")
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a") as f:
            f.write("### Job refresh\n\n| | |\n|---|---:|\n")
            for k in ("live", "matched", "new_today", "carried", "exported", "seen_before", "seen_added",
                      "pruned", "seen_after", "attempted"):
                f.write(f"| {k.replace('_', ' ')} | {r[k]:,} |\n")
            if r["errors"]:
                f.write(f"\n**{len(r['errors'])} boards skipped** (last good jobs kept):\n\n")
                f.write("".join(f"- {e}\n" for e in r["errors"]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--no-openquant", action="store_true", help="skip the openquant.co quant board")
    ap.add_argument("--no-builtin", action="store_true", help="skip the Built In SF/NYC boards")
    ap.add_argument("--seen", default=str(SEEN_PATH), help="first/last-seen state file (read + written)")
    ap.add_argument("--out", default=str(DOCS / "jobs.json"), help="site data to write")
    ap.add_argument("--previous", default=None,
                    help="last good jobs.json, for carrying forward broken boards (default: --out if it exists)")
    ap.add_argument("--prune-days", type=int, default=PRUNE_DAYS)
    ap.add_argument("--allow-drop", action="store_true",
                    help=f"accept a run with under {DROP_LIMIT:.0%} of the previous run's roles")
    ap.add_argument("--today", default=None, help="override the local date (YYYY-MM-DD), for tests")
    args = ap.parse_args(argv)
    if args.previous is None and Path(args.out).exists():
        args.previous = args.out

    cfg = json.loads((ROOT / "companies.json").read_text())
    companies = cfg["companies"]
    if args.tag:
        tags = {t.lower() for t in args.tag}
        companies = [c for c in companies if set(t.lower() for t in c.get("tags", [])) & tags]

    today = args.today or dt.date.today().isoformat()
    payload, seen, report = build(companies, args, today)
    write_atomic(args.seen, json.dumps(seen, separators=(",", ":")))
    write_atomic(args.out, json.dumps(payload))
    summarize(report, len(companies))


if __name__ == "__main__":
    main()
