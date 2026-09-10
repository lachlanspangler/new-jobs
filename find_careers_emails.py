#!/usr/bin/env python3
"""Find published careers/recruiting inbox addresses on each company's OWN site
and merge them into docs/recruiters.json. No API key, no LinkedIn, no third-party
lists — it only reads pages on the company's own domain and keeps role-based
inboxes (careers@, recruiting@, talent@, jobs@, university@, …) it actually finds.

  python3 find_careers_emails.py            # all companies
  python3 find_careers_emails.py --tag ai   # limit by tag
"""
import argparse, datetime as dt, html, json, re, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "docs" / "recruiters.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PAGES = ["", "/careers", "/careers/", "/contact", "/about", "/jobs", "/company/careers", "/join-us", "/join"]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ROLE_RE = re.compile(r"^(careers?|recruit(ing|ment)?|jobs?|talent|hiring|hr|people|"
                     r"university|campus|earlycareers?|gradrecruiting|hello|contact|apply|joinus|work)@", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return html.unescape(r.read(400000).decode("utf-8", "ignore"))


def emails_for(domain):
    found = set()
    base = f"https://{domain}"
    for p in PAGES:
        try:
            text = fetch(base + p)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, UnicodeError):
            continue
        for m in EMAIL_RE.findall(text):
            e = m.lower()
            # keep role inboxes on this company's domain (avoid vendors / personal / noreply)
            if ROLE_RE.match(e) and e.split("@", 1)[1].endswith(domain) and "noreply" not in e and "no-reply" not in e:
                found.add(e)
        if found:
            break  # got what we need; don't hammer more pages
        time.sleep(0.2)
    return sorted(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--company", default="")
    args = ap.parse_args()

    companies = json.loads((ROOT / "companies.json").read_text())["companies"]
    if args.tag:
        tags = {t.lower() for t in args.tag}
        companies = [c for c in companies if set(t.lower() for t in c.get("tags", [])) & tags]
    if args.company:
        companies = [c for c in companies if args.company.lower() in c["name"].lower()]

    data = json.loads(PATH.read_text()) if PATH.exists() else {}
    by = data.get("byCompany", {}) if isinstance(data, dict) else {}

    added = 0
    for c in companies:
        dom = c.get("domain")
        if not dom:
            continue
        try:
            emails = emails_for(dom)
        except Exception as e:
            print(f"{c['name']}: error {e}"); emails = []
        if emails:
            existing = by.setdefault(c["name"], [])
            have = {x.get("email", "").lower() for x in existing}
            for e in emails:
                if e not in have:
                    existing.append({"name": "", "title": "Careers inbox", "email": e,
                                     "confidence": None, "locked": False, "linkedin": "", "source": "site"})
                    added += 1
            print(f"{c['name']}: {emails}")
        else:
            print(f"{c['name']}: —")
        PATH.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                    "source": (data.get("source") if isinstance(data, dict) else None) or "mixed",
                                    "byCompany": by}))
        time.sleep(0.3)
    print(f"\nadded {added} careers inboxes; {sum(len(v) for v in by.values())} total contacts / {len(by)} companies")


if __name__ == "__main__":
    main()
