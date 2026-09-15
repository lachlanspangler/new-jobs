#!/usr/bin/env python3
"""Publish ONLY generic careers/recruiting inboxes to docs/company_emails.json
so the Companies page can show a public "email careers" link per company.

Named personal recruiter emails are deliberately NOT included here (those live in
recruiters.json / contacts_local.json). We only surface role inboxes like
careers@, recruiting@, jobs@ — low-sensitivity, already-public company addresses.

Sources: contacts_local.json (git-ignored import) + docs/recruiters.json, keeping
only entries with no personal name AND a generic-looking local part.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# local-part keywords that mark a shared role inbox (not a person)
GENERIC = re.compile(
    r"^(careers?|recruit(ing|ment|er)?|jobs?|hr|talent|hello|hi|apply|"
    r"applications?|join|joinus|people|peopleops|work(with(us)?)?|hiring|"
    r"team|contact|info|resume[s]?|cv|university|campus|newgrad|grads?)"
    r"([._+-]?[a-z0-9]+)*@", re.I)


# role-inbox keywords, matched anywhere in the local-part or the title
GEN_KW = ("career", "recruit", "talent", "hiring", "campus", "graduate", "grad",
          "people", "resourc", "staffing", "earlycareer", "interview", "helpdesk",
          "askhr", "hrconnect", "hranswer", "candidate", "job", "apply", "resume")


def is_generic(row):
    email = (row.get("email") or "").strip()
    name = (row.get("name") or "").strip()
    if not email or name or row.get("public") is False:  # role inbox, not a person/alias
        return False
    if GENERIC.match(email):     # local part starts with a generic keyword
        return True
    local = re.sub(r"[^a-z0-9]", "", email.split("@")[0].lower())
    hay = local + " " + (row.get("title") or "").lower()
    return any(k in hay for k in GEN_KW)


def collect(path, out):
    p = ROOT / path
    if not p.exists():
        return
    for company, rows in json.loads(p.read_text()).get("byCompany", {}).items():
        for r in rows:
            if is_generic(r):
                e = r["email"].strip().lower()
                lst = out.setdefault(company, [])
                if e not in lst:
                    lst.append(e)


def main():
    out = {}
    collect("contacts_local.json", out)          # private import (generic rows only)
    collect("docs/recruiters.json", out)         # public Hunter/Apollo (generic rows only)
    out = {k: v for k, v in sorted(out.items()) if v}
    dest = ROOT / "docs" / "company_emails.json"
    dest.write_text(json.dumps({"byCompany": out}, indent=0))
    print(f"Wrote {dest} — {len(out)} companies, "
          f"{sum(len(v) for v in out.values())} generic inboxes.")


if __name__ == "__main__":
    main()
