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
import argparse, datetime as dt, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
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
# Finance roles (financial analyst / entry-level finance): a finance FIELD and an entry-type ROLE, both required, so
# "Investment Banking Analyst" and "FP&A Associate" match but "Data Analyst" and "VP, Investment Banking" don't.
FIN_FIELD_RE = re.compile(
    r"\b(financ(e|ial)|fp\s*&\s*a|investment|investing|banking|equity\s+research|private\s+(equity|credit|markets)|"
    r"venture|capital\s+markets|corporate\s+(development|finance)|corp\s*dev|treasury|valuations?|credit|"
    r"m\s*&\s*a|mergers|acquisitions|asset\s+management|wealth|portfolio|fund\s+(accounting|administration|operations)|"
    r"underwriting|restructuring|leveraged\s+finance|real\s+estate|market\s+risk|risk\s+management|"
    r"accounting|econom(ic|ics|ist)|fixed\s+income|equities|securities|sales\s*(&|and)\s*trading)\b",
    re.IGNORECASE,
)
FIN_ROLE_RE = re.compile(
    r"\b(analysts?|associates?|summer\s+analyst|analyst\s+program|rotational|rotation\s+program|new\s+grad|"
    r"graduate|junior|jr\.?|entry[\s-]+level|early\s+career|campus|interns?|internship|economist)\b",
    re.IGNORECASE,
)
FIN_EXCLUDE_RE = re.compile(
    r"\b(sales(?!\s*(&|and)\s*trading)|customer|support|success|account\s+executive|marketing|recruit\w*|talent|"
    r"human\s+resources|\bhr\b|legal|counsel|paralegal|designer|nurse|clinical|facilities|insurance\s+agent|"
    # back-office and IT roles that wear an analyst/associate title (2026-11-10 precision pass)
    r"accounts\s+(payable|receivable)|payroll|bookkeep\w*|billing|collections|teller|operations|"
    r"business\s+(systems\s+)?analyst|systems\s+analyst|data\s+analyst|client\s+service|loan\s+servic\w*|processor)\b",
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


def is_finance(title):
    """Financial analyst / entry-level finance roles (see FIN_FIELD_RE)."""
    return bool(FIN_FIELD_RE.search(title) and FIN_ROLE_RE.search(title)) and not FIN_EXCLUDE_RE.search(title)


# --- job categories ---------------------------------------------------------------------------------------------
# Every kept job gets exactly one category. Real estate and development roles are analyst/associate-level roles in a
# real-estate context: the company is tagged "realestate" in companies.json, or the title itself names real estate.
CATEGORIES = ("software", "quant", "realestate", "development", "finance")
RE_WORDS_RE = re.compile(
    r"\b(real\s+estate|reits?|propert(y|ies)|multi-?family|self[\s-]?storage|single[\s-]family|student\s+housing|"
    r"housing|hospitality|commercial\s+real|cre|land\s+acquisition|homebuild\w*)\b", re.IGNORECASE)
RE_FIELD_RE = re.compile(
    r"\b(acquisitions?|asset\s+management|investments?|investing|capital\s+markets|underwriting|valuations?|"
    r"leasing|brokerage|transactions?|debt|equity|private\s+equity|portfolio|research|capital)\b",
    re.IGNORECASE)
DEV_RE = re.compile(r"\bdevelopment\b", re.IGNORECASE)
NOT_RE_DEV_RE = re.compile(  # "development" that isn't real estate development
    r"\b(software|web|app(lication)?|product|business|sales|fund|leadership|organi[sz]ational|talent|learning|"
    r"training|curriculum|drug|clinical|engineering|game|mobile|front[\s-]?end|back[\s-]?end|full[\s-]?stack|"
    r"platform|systems?|data|ml|ai|tools?)\s+development\b|\bdevelopment\s+(engineer|operations|tools)\b|"
    r"\b(developer|devops|sdk)\b", re.IGNORECASE)
QUANT_RE = re.compile(r"\b(quant|quantitative|trader|trading|trade\s*desk|desk\s*operations)\b", re.IGNORECASE)
SALES_TRADING_RE = re.compile(r"\bsales\s*(&|and)\s*trading\b", re.IGNORECASE)
SWE_STRONG_RE = re.compile(r"\b(software|developer|engineer|engineering|programmer|swe|sde|sre|devops)\b|c\+\+",
                           re.IGNORECASE)


# Real estate, development and finance analyst roles are entry- and mid-level only (owner, 2026-11-10): nothing senior
# or staff. Software and quant keep every level, with the site's Hide senior / Hide staff toggles.
SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|vp|svp|evp|vice\s+president|managing|head|chief|partner|"
    r"executive|distinguished|fellow|md)\b", re.IGNORECASE)
ENTRY_MID_ONLY = {"realestate", "development", "finance"}


def category_of(title, tags=()):
    """The job's category, or None if it isn't a role this board keeps."""
    cat = _category(title, tags)
    if cat in ENTRY_MID_ONLY and SENIOR_RE.search(title or ""):
        return None
    return cat


def _category(title, tags=()):
    t = title or ""
    re_company = "realestate" in {x.lower() for x in tags or ()}
    re_context = re_company or bool(RE_WORDS_RE.search(t))
    analyst_level = bool(FIN_ROLE_RE.search(t)) and not FIN_EXCLUDE_RE.search(t)
    if analyst_level and re_context and not SWE_STRONG_RE.search(t):
        if DEV_RE.search(t) and not NOT_RE_DEV_RE.search(t):
            return "development"
        if RE_WORDS_RE.search(t) or RE_FIELD_RE.search(t):
            return "realestate"
    swe_or_quant = bool(INCLUDE_RE.search(t)) and not EXCLUDE_RE.search(t)
    if swe_or_quant and QUANT_RE.search(t) and not SALES_TRADING_RE.search(t):
        return "quant"
    if swe_or_quant and SWE_STRONG_RE.search(t):
        return "software"
    if is_finance(t):
        return "finance"
    if swe_or_quant:
        return "software"
    return None


def is_target(title, tags=()):
    return category_of(title, tags) is not None


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


WORKDAY_TERMS = ("software engineer", "c++", "python", "quant", "developer", "research", "data engineer", "trading",
                 "financial analyst")
# banks and asset managers: two broad finance terms (Workday's search returns every analyst/associate posting, and the
# title filter keeps the finance ones) plus their tech/quant roles. 4 terms x <=5 pages keeps each tenant <=20 calls.
FINANCE_WORKDAY_TERMS = ("analyst", "associate", "software engineer", "quant")


def norm_workday(c):
    host, tenant, site = c["host"], c["token"], c["site"]
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    seen, out = set(), []
    terms = search_terms(c, WORKDAY_TERMS)  # banks etc. use "terms": "finance" (or their own list)
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


# --- Oracle Cloud HCM (e.g. JPMorgan): the public Candidate Experience REST endpoint the careers site itself uses.
# Searched by keyword like Workday, because these boards are huge; "terms" in companies.json overrides the default.
ORACLE_PAGE = 25
ORACLE_MAX_PAGES = 4


def search_terms(c, default):
    terms = c.get("terms") or default
    return FINANCE_WORKDAY_TERMS if terms == "finance" else terms


def norm_oracle(c):
    host, site = c["host"], c["site"]
    out, seen = [], set()
    for term in search_terms(c, FINANCE_WORKDAY_TERMS):
        for page in range(ORACLE_MAX_PAGES):
            finder = (f"findReqs;siteNumber={site},keyword={urllib.parse.quote(term)},"
                      f"limit={ORACLE_PAGE},offset={page * ORACLE_PAGE},sortBy=POSTING_DATES_DESC")
            data = fetch(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                         f"?onlyData=true&expand=requisitionList&finder={finder}")
            items = data.get("items") or []
            if not items:
                raise ValueError(f"oracle {host}: no items in response")
            reqs = items[0].get("requisitionList") or []
            for r in reqs:
                jid = str(r.get("Id") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                out.append(_row(c, "oracle", jid, r.get("Title", ""), r.get("PrimaryLocation") or "",
                                f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}",
                                r.get("PostedDate") or "", ""))
            if len(reqs) < ORACLE_PAGE or (page + 1) * ORACLE_PAGE >= (items[0].get("TotalJobsCount") or 0):
                break
            time.sleep(0.2)
    return out


# --- SmartRecruiters: the public Posting API (no key needed for published postings).
SR_PAGE = 100
SR_MAX_PAGES = 10


def norm_smartrecruiters(c):
    out = []
    for page in range(SR_MAX_PAGES):
        data = fetch(f"https://api.smartrecruiters.com/v1/companies/{urllib.parse.quote(c['token'])}/postings"
                     f"?limit={SR_PAGE}&offset={page * SR_PAGE}")
        content = data.get("content")
        if content is None:
            raise ValueError(f"smartrecruiters {c['token']}: unexpected payload")
        if page == 0 and not content:
            raise ValueError(f"smartrecruiters {c['token']}: no postings (wrong company identifier?)")
        for p in content:
            loc = p.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
            if loc.get("remote"):
                where = f"Remote - {where}" if where else "Remote"
            out.append(_row(c, "smartrecruiters", p["id"], p.get("name", ""), where,
                            f"https://jobs.smartrecruiters.com/{c['token']}/{p['id']}", p.get("releasedDate") or "", ""))
        if len(content) < SR_PAGE or (page + 1) * SR_PAGE >= (data.get("totalFound") or 0):
            break
        time.sleep(0.2)
    return out


# --- iCIMS: the public, server-rendered job search page (robots.txt allows /jobs/search; we never touch
# login/referral/candidate paths). One card per posting; "Page X of N" tells us when to stop.
ICIMS_MAX_PAGES = 10
IC_CARD_SPLIT = '<li class="iCIMS_JobCardItem">'
IC_LINK_RE = re.compile(r'<a href="(https://[^"]+/jobs/(\d+)/[^"]*/job)[^"]*" class="iCIMS_Anchor"')
IC_TITLE_RE = re.compile(r"<h3[^>]*>\s*(.*?)\s*</h3>", re.S)
IC_DATE_RE = re.compile(r'Posted Date</span>\s*<span title="(\d{1,2})/(\d{1,2})/(\d{4})')
IC_LOC_RE = re.compile(  # two card variants: a "Job Locations" field, or a "Location" label in the card header
    r'Job Locations</span>\s*</dt>\s*<dd class="iCIMS_JobHeaderData"><span\s*>\s*(.*?)\s*</span>|'
    r'field-label">\s*Locations?\s*</span>\s*<span\s*>\s*(.*?)\s*</span>', re.S)
IC_PAGES_RE = re.compile(r"Page\s*(\d+)\s*of\s*(\d+)")


def icims_location(raw):
    """'US-CA-San Francisco' -> 'San Francisco, CA, US'; anything else is kept as is."""
    parts = [p.strip() for p in html.unescape(raw or "").split("-")]
    if len(parts) >= 3 and len(parts[0]) == 2 and len(parts[1]) <= 3:
        return f"{'-'.join(parts[2:])}, {parts[1]}, {parts[0]}"
    return html.unescape(raw or "").strip()


def parse_icims(page_html):
    rows = []
    for card in page_html.split(IC_CARD_SPLIT)[1:]:
        m = IC_LINK_RE.search(card)
        mt = IC_TITLE_RE.search(card)
        if not m or not mt:
            continue
        md, ml = IC_DATE_RE.search(card), IC_LOC_RE.search(card)
        rows.append({"id": m.group(2), "url": html.unescape(m.group(1)),
                     "title": html.unescape(TAG_RE.sub("", mt.group(1))).strip(),
                     "posted": f"{md.group(3)}-{int(md.group(1)):02d}-{int(md.group(2)):02d}" if md else "",
                     "location": icims_location(ml.group(1) or ml.group(2)) if ml else ""})
    mp = IC_PAGES_RE.search(page_html)
    return rows, (int(mp.group(1)), int(mp.group(2))) if mp else (1, 1)


def norm_icims(c):
    out, seen = [], set()
    for page in range(ICIMS_MAX_PAGES):
        page_html = fetch_html(f"https://{c['token']}.icims.com/jobs/search?ss=1&in_iframe=1&pr={page}", ua=UA)
        rows, (cur, last) = parse_icims(page_html)
        if page == 0 and not rows:
            raise ValueError(f"icims {c['token']}: no job cards on page 1")
        for r in rows:
            if r["id"] not in seen:
                seen.add(r["id"])
                out.append(_row(c, "icims", r["id"], r["title"], r["location"], r["url"], r["posted"], ""))
        if not rows or cur >= last:
            break
        time.sleep(PACING)
    return out


# --- SAP SuccessFactors Recruiting Marketing (RMK) career sites: the public, server-rendered /search/ page. It is the
# path robots.txt allows (the RSS feed and JSON under /services/ are disallowed, so we never use them). Two layouts:
# a results table (<tr class="data-row">) and Career Site Builder tiles (<li class="job-tile">). Page size is set by
# each site, so we advance startrow by the rows we got. Sites that render results with JavaScript ("Unify") have
# neither layout and count as a failed board.
SF_MAX_PAGES = 10
SF_ROW_SPLIT = '<tr class="data-row"'
SF_TILE_SPLIT = '<li class="job-tile'
SF_LINK_RE = re.compile(r'<a[^>]*?href="([^"]*/(\d+)/)"[^>]*class="jobTitle-link[^"]*"[^>]*>(.*?)</a>|'
                        r'<a[^>]*class="jobTitle-link[^"]*"[^>]*href="([^"]*/(\d+)/)"[^>]*>(.*?)</a>', re.S)
SF_LOC_RE = re.compile(r'<td class="colLocation[^"]*"[^>]*>\s*<span class="jobLocation">\s*(.*?)\s*</span>', re.S)
SF_DATE_RE = re.compile(r'<td class="colDate[^"]*"[^>]*>\s*<span class="jobDate">\s*(.*?)\s*</span>', re.S)
SF_FIELD_RE = re.compile(r'class="section-label[^"]*"[^>]*>\s*(.*?)\s*</span>\s*<div id="job-\d+-desktop-section-[^"]*-value">'
                         r'\s*(.*?)\s*</div>', re.S)
SF_TOTAL_RE = re.compile(r'class="paginationLabel"[^>]*>.*?<b>[^<]*</b>.*?<b>\s*([\d,.]+)\s*</b>|'
                         r'id="tile-search-results-label"[^>]*>[^<]*?(\d[\d,.]*)\s*\D*</span>', re.S)
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def sf_date(txt):
    """'7 Nov 2026' or 'Nov 9, 2026' -> '2026-11-07'; anything else -> ''."""
    t = (txt or "").strip().replace(",", " ")
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$", t) or re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\s+(\d{4})$", t)
    if not m:
        return ""
    a, b, y = m.groups()
    day, mon = (a, b) if a.isdigit() else (b, a)
    mon = MONTHS.get(mon.lower())
    return f"{y}-{mon:02d}-{int(day):02d}" if mon else ""


def _clean(fragment):
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", fragment or ""))).strip()


def parse_successfactors(page_html):
    """-> (rows, total). rows: {id, path, title, location, posted}; total None if the page doesn't say."""
    rows = []
    if SF_TILE_SPLIT in page_html:
        for tile in page_html.split(SF_TILE_SPLIT)[1:]:
            m = SF_LINK_RE.search(tile)
            if not m:
                continue
            path, jid, title = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
            fields = {_clean(k).lower(): _clean(v) for k, v in SF_FIELD_RE.findall(tile)}
            loc = ", ".join(v for k, v in fields.items() if re.search(r"location|city|state|region|country", k) and v)
            posted = next((sf_date(v) for k, v in fields.items() if "date" in k), "")
            rows.append({"id": jid, "path": html.unescape(path), "title": _clean(title), "location": loc, "posted": posted})
    else:
        for tr in page_html.split(SF_ROW_SPLIT)[1:]:
            tr = tr.split("</tr>")[0]
            m = SF_LINK_RE.search(tr)
            if not m:
                continue
            path, jid, title = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
            ml, md = SF_LOC_RE.search(tr), SF_DATE_RE.search(tr)
            rows.append({"id": jid, "path": html.unescape(path), "title": _clean(title),
                         "location": _clean(ml.group(1)) if ml else "", "posted": sf_date(_clean(md.group(1))) if md else ""})
    mt = SF_TOTAL_RE.search(page_html)
    total = int(re.sub(r"\D", "", mt.group(1) or mt.group(2))) if mt else None
    return rows, total


def norm_successfactors(c):
    host = c["host"]
    terms = c.get("terms")
    terms = [""] if not terms else search_terms(c, None)
    out, seen = [], set()
    for term in terms:
        start = 0
        for page in range(SF_MAX_PAGES):
            q = urllib.parse.urlencode({"q": term, "startrow": start, "sortColumn": "referencedate",
                                        "sortDirection": "desc", **({"locale": c["locale"]} if c.get("locale") else {})})
            rows, total = parse_successfactors(fetch_html(f"https://{host}/search/?{q}", ua=UA))
            if page == 0 and not rows and term == terms[0]:
                if total == 0:
                    break  # a real "no results" page for this search term
                raise ValueError(f"successfactors {host}: no job rows on page 1 (JavaScript-rendered site?)")
            for r in rows:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    out.append(_row(c, "successfactors", r["id"], r["title"], r["location"],
                                    f"https://{host}{r['path']}", r["posted"], ""))
            start += len(rows)
            if not rows or (total is not None and start >= total):
                break
            time.sleep(PACING)
    return out


FETCHERS = {"greenhouse": norm_greenhouse, "ashby": norm_ashby, "lever": norm_lever, "workday": norm_workday,
            "oracle": norm_oracle, "smartrecruiters": norm_smartrecruiters, "icims": norm_icims,
            "successfactors": norm_successfactors}

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


def fetch_html(url, ua=BROWSER_UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html"})
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


# Boards are fetched in parallel, but politely per host: shared public APIs (Greenhouse, Ashby, Lever,
# SmartRecruiters) get at most SHARED_HOST_LANES requests in flight, and an employer's own host (a Workday tenant, an
# Oracle pod, an iCIMS or SuccessFactors site) one at a time, with the usual pacing between boards on each lane.
WORKERS = 12
SHARED_HOST_LANES = 3
SHARED_HOSTS = {"greenhouse": "boards-api.greenhouse.io", "ashby": "api.ashbyhq.com", "lever": "api.lever.co",
                "smartrecruiters": "api.smartrecruiters.com"}


def host_of(c):
    if c["ats"] in SHARED_HOSTS:
        return SHARED_HOSTS[c["ats"]]
    if c["ats"] == "workday":
        return f"{c['token']}.{c['host']}.myworkdayjobs.com"
    if c["ats"] == "icims":
        return f"{c['token']}.icims.com"
    return c.get("host") or c["token"]


def fetch_all(companies):
    """[(company, rows or None, error or None)] in companies order; one board's failure never affects another."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lanes = {}
    for c in companies:
        h = host_of(c)
        lanes.setdefault(h, threading.BoundedSemaphore(SHARED_HOST_LANES if h in SHARED_HOSTS.values() else 1))

    def one(c):
        with lanes[host_of(c)]:
            try:
                return c, FETCHERS[c["ats"]](c), None
            except Exception as e:  # one broken board never fails the run
                return c, None, e
            finally:
                time.sleep(PACING)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(one, companies))


def collect(companies, args):
    """Fetch every board. Returns (rows_before_title_filter, curated_rows, failed_boards, errors, attempted)."""
    all_jobs, curated, failed, errors, attempted = [], [], set(), [], 0
    for c, rows, err in fetch_all(companies):
        attempted += 1
        if err is None:
            all_jobs.extend(rows)
        else:
            failed.add(f"{c['ats']}:{c['token']}")
            errors.append(f"{c['name']}: {err}")

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

    matched = [j for j in all_jobs if is_target(j["title"], j.get("tags"))] + curated
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
        # curated openquant rows skip the title filter: anything it doesn't recognise is a quant role
        j["category"] = category_of(j["title"], j.get("tags")) or ("quant" if j["source"] == "openquant" else "software")
    rows.sort(key=lambda j: (j["priority"], j.get("posted") or ""), reverse=True)  # newest first, cities boosted

    export = rows[:MAX_EXPORT]  # the top MAX_EXPORT, but always keep every openquant/builtin role
    if len(rows) > MAX_EXPORT:
        have = {j["key"] for j in export}
        export += [j for j in rows[MAX_EXPORT:] if j["source"] in ("openquant", "builtin") and j["key"] not in have]
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(rows),
        "new_today": sum(1 for j in rows if j["isNew"]),
        "categories": {c: sum(1 for j in rows if j["category"] == c) for c in CATEGORIES},
        "companies": len(companies),
        "jobs": [{k: j.get(k, "" if k not in ("tags",) else []) for k in (
            "company", "tags", "source", "key", "title", "location", "url", "posted", "salary",
            "firstSeen", "isNew", "priority", "category")} for j in export],
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
