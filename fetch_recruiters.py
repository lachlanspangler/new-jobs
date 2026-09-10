#!/usr/bin/env python3
"""Fetch recruiter / hiring-manager contacts per company via the Apollo People
Search API and write docs/recruiters.json.

Uses Apollo's official API with YOUR key (env APOLLO_API_KEY), which is the
sanctioned way to do this. On the free tier a search typically returns each
person's name, title, and LinkedIn but leaves the email 'locked' until you
unlock it with credits (People Enrichment) — we store what the API returns and
flag locked emails rather than guessing anything.

  APOLLO_API_KEY=xxxxx python3 fetch_recruiters.py
"""
import datetime as dt, json, os, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY = os.environ.get("APOLLO_API_KEY")
TITLES = ["recruiter", "technical recruiter", "talent acquisition", "university recruiter",
          "hiring manager", "engineering manager", "head of talent"]


def search(name):
    body = json.dumps({"organization_names": [name], "person_titles": TITLES,
                       "page": 1, "per_page": 5}).encode()
    req = urllib.request.Request("https://api.apollo.io/api/v1/mixed_people/search", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Cache-Control": "no-cache", "X-Api-Key": KEY})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    if not KEY:
        sys.exit("Set APOLLO_API_KEY to fetch contacts:\n  APOLLO_API_KEY=xxxx python3 fetch_recruiters.py")
    companies = json.loads((ROOT / "companies.json").read_text())["companies"]
    out = {}
    for c in companies:
        try:
            people = search(c["name"]).get("people", []) or []
            rows = []
            for p in people[:5]:
                email = p.get("email") or ""
                locked = (not email) or "not_unlocked" in email or "email_not" in email
                rows.append({
                    "name": p.get("name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
                    "title": p.get("title") or "",
                    "email": "" if locked else email,
                    "locked": locked,
                    "linkedin": p.get("linkedin_url") or "",
                })
            if rows:
                out[c["name"]] = rows
            print(f"{c['name']}: {len(rows)}")
        except Exception as e:
            print(f"{c['name']}: error {e}")
        time.sleep(0.6)
    (ROOT / "docs" / "recruiters.json").write_text(json.dumps(
        {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "byCompany": out}))
    print(f"\nwrote docs/recruiters.json — {sum(len(v) for v in out.values())} contacts / {len(out)} companies")


if __name__ == "__main__":
    main()
