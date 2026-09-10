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
    for term in ("software engineer", "c++", "python", "quant"):  # query relevant roles server-side
        for offset in range(0, 80, 20):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
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

    matched = [j for j in all_jobs if is_target(j["title"])]

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
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(matched),
        "new_today": sum(1 for j in matched if j["isNew"]),
        "companies": len(companies),
        "jobs": [{k: j[k] for k in ("company", "tags", "source", "key", "title",
                                    "location", "url", "posted", "salary", "firstSeen", "isNew", "priority")}
                 for j in matched[:MAX_EXPORT]],
    }
    (DOCS / "jobs.json").write_text(json.dumps(payload))
    print(f"{len(all_jobs)} live postings -> {len(matched)} target roles "
          f"({payload['new_today']} new today) across {len(companies)} companies")
    if errors:
        print(f"{len(errors)} fetch errors:", *errors[:8], sep="\n  ")


if __name__ == "__main__":
    main()
