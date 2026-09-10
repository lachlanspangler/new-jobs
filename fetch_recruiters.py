#!/usr/bin/env python3
"""Fetch recruiter / talent contacts per company and write docs/recruiters.json.

Primary source: Hunter.io Domain Search (best email yield) — for each company's
domain it returns real, deliverability-scored addresses for the HR / talent
department, with name, title, and LinkedIn. Set HUNTER_API_KEY.

Fallback: Apollo People Search (set APOLLO_API_KEY) — returns names/titles but
usually leaves the email locked on the free tier.

  HUNTER_API_KEY=xxxx python3 fetch_recruiters.py            # all companies
  HUNTER_API_KEY=xxxx python3 fetch_recruiters.py --tag quant --tag ai

Both are official APIs used with YOUR key. Nothing is scraped or invented; keep
outreach personalized and low-volume so you stay on the right side of anti-spam
rules and each platform's terms.
"""
import argparse, datetime as dt, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HUNTER = os.environ.get("HUNTER_API_KEY")
APOLLO = os.environ.get("APOLLO_API_KEY")
APOLLO_TITLES = ["recruiter", "technical recruiter", "talent acquisition", "university recruiter",
                 "hiring manager", "engineering manager", "head of talent"]


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def hunter(domain):
    q = urllib.parse.urlencode({"domain": domain, "department": "hr", "limit": 10, "api_key": HUNTER})
    data = get_json(f"https://api.hunter.io/v2/domain-search?{q}").get("data", {})
    rows = []
    for e in data.get("emails", []):
        name = " ".join(x for x in [e.get("first_name"), e.get("last_name")] if x).strip()
        rows.append({"name": name or "—", "title": e.get("position") or "",
                     "email": e.get("value") or "", "confidence": e.get("confidence"),
                     "locked": not e.get("value"), "linkedin": e.get("linkedin") or ""})
    return rows


def apollo(name):
    body = json.dumps({"organization_names": [name], "person_titles": APOLLO_TITLES,
                       "page": 1, "per_page": 5}).encode()
    people = get_json("https://api.apollo.io/api/v1/mixed_people/search", data=body,
                      headers={"Content-Type": "application/json", "X-Api-Key": APOLLO}).get("people", [])
    rows = []
    for p in people[:5]:
        email = p.get("email") or ""
        locked = (not email) or "not_unlocked" in email or "email_not" in email
        rows.append({"name": p.get("name") or "—", "title": p.get("title") or "",
                     "email": "" if locked else email, "confidence": None,
                     "locked": locked, "linkedin": p.get("linkedin_url") or ""})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
    args = ap.parse_args()
    if not HUNTER and not APOLLO:
        sys.exit("Set HUNTER_API_KEY (preferred) or APOLLO_API_KEY, then re-run.")

    companies = json.loads((ROOT / "companies.json").read_text())["companies"]
    if args.tag:
        tags = {t.lower() for t in args.tag}
        companies = [c for c in companies if set(t.lower() for t in c.get("tags", [])) & tags]

    src = "hunter" if HUNTER else "apollo"
    path = ROOT / "docs" / "recruiters.json"
    merged = {}
    if path.exists():
        try:
            merged = json.loads(path.read_text()).get("byCompany", {})   # accumulate across runs
        except ValueError:
            merged = {}
    added = 0
    for c in companies:
        try:
            rows = hunter(c["domain"]) if (HUNTER and c.get("domain")) else apollo(c["name"])
            if rows:
                merged[c["name"]] = rows   # refresh/add this company
                added += len(rows)
            print(f"{c['name']}: {len(rows)}")
        except Exception as e:
            print(f"{c['name']}: error {e}")
        time.sleep(0.5)

    path.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": src, "byCompany": merged,
    }))
    print(f"\nwrote docs/recruiters.json ({src}) — {added} contacts added/refreshed this run; "
          f"{sum(len(v) for v in merged.values())} total across {len(merged)} companies")


if __name__ == "__main__":
    main()
