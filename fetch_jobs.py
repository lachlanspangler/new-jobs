#!/usr/bin/env python3
"""new-jobs: pull the newest software / quant roles across Greenhouse, Ashby,
and Lever boards, keep target roles, prioritize SF/Chicago/NYC, and export a
static docs/jobs.json for the site. Standard library only.

Roles kept: software / C++ / Python engineers, quant developer, quant
researcher, quant, trade-desk operations (and adjacent SWE titles).

Usage:
  python3 fetch_jobs.py            # fetch, update seen store, export site data
  python3 fetch_jobs.py --tag ai   # limit to a company tag (repeatable)
"""

from __future__ import annotations
import argparse, datetime as dt, html, json, re, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEEN_PATH = ROOT / "seen.json"          # key -> first-seen ISO date
DOCS = ROOT / "docs"
UA = "new-jobs/1.0 (personal job search)"
PACING = 0.25
MAX_EXPORT = 2000

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
    for p in data if isinstance(data, list) else []:
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
    return json.loads(m.group(1))["props"]["pageProps"].get("data", []) if m else []


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
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
            break
        blocks = html_.split('data-id="job-card"')[1:]
        if not blocks:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--no-openquant", action="store_true", help="skip the openquant.co quant board")
    ap.add_argument("--no-builtin", action="store_true", help="skip the Built In SF/NYC boards")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "companies.json").read_text())
    companies = cfg["companies"]
    if args.tag:
        tags = {t.lower() for t in args.tag}
        companies = [c for c in companies if set(t.lower() for t in c.get("tags", [])) & tags]

    all_jobs, errors = [], []
    for c in companies:
        try:
            all_jobs.extend(FETCHERS[c["ats"]](c))
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError, TimeoutError) as e:
            errors.append(f"{c['name']}: {e}")
        time.sleep(PACING)

    # Built In SF/NYC boards (general tech listings -> filtered to target roles below)
    want_builtin = not args.no_builtin and (not args.tag or "tech" in {t.lower() for t in args.tag})
    if want_builtin:
        for base, city in BUILTIN_SITES:
            try:
                rows = norm_builtin(base, city)
                all_jobs.extend(rows)
                print(f"{base}: +{len(rows)} listings")
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
                errors.append(f"{base}: {e}")

    matched = [j for j in all_jobs if is_target(j["title"])]

    # openquant.co is already a curated quant board — include its roles as-is
    # (skip the title filter) unless a non-quant --tag filter is in effect.
    want_oq = not args.no_openquant and (not args.tag or "quant" in {t.lower() for t in args.tag})
    if want_oq:
        try:
            oq = fetch_openquant()
            matched.extend(oq)
            print(f"openquant.co: +{len(oq)} quant roles")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
            errors.append(f"openquant.co: {e}")

    # first-seen tracking for "new today"
    today = dt.date.today().isoformat()
    seen = json.loads(SEEN_PATH.read_text()) if SEEN_PATH.exists() else {}
    for j in matched:
        seen.setdefault(j["key"], today)
        j["firstSeen"] = seen[j["key"]]
        j["isNew"] = seen[j["key"]] == today
        j["priority"] = bool(PRIORITY_RE.search(j["location"] or ""))
    SEEN_PATH.write_text(json.dumps(seen))

    # newest first, priority cities boosted
    matched.sort(key=lambda j: (j["priority"], j.get("posted", "")), reverse=True)

    DOCS.mkdir(exist_ok=True)
    # export the top MAX_EXPORT by sort, but always keep every openquant role
    export = matched[:MAX_EXPORT]
    if len(matched) > MAX_EXPORT:
        have = {j["key"] for j in export}
        export += [j for j in matched[MAX_EXPORT:]
                   if j["source"] in ("openquant", "builtin") and j["key"] not in have]
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(matched),
        "new_today": sum(1 for j in matched if j["isNew"]),
        "companies": len(companies),
        "jobs": [{k: j[k] for k in ("company", "tags", "source", "key", "title",
                                    "location", "url", "posted", "salary", "firstSeen", "isNew", "priority")}
                 for j in export],
    }
    (DOCS / "jobs.json").write_text(json.dumps(payload))
    print(f"{len(all_jobs)} live postings -> {len(matched)} target roles "
          f"({payload['new_today']} new today) across {len(companies)} companies")
    if errors:
        print(f"{len(errors)} fetch errors:", *errors[:8], sep="\n  ")


if __name__ == "__main__":
    main()
