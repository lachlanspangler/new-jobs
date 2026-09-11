#!/usr/bin/env python3
"""Import a recruiter/careers-email spreadsheet (.xlsx) into a LOCAL, git-ignored
contacts file (contacts_local.json) that make_drafts.py reads for outreach.

It is deliberately NOT written into docs/recruiters.json, so a compiled list of
(sometimes named) people's addresses is never published to the public site.
Rows marked "do not cold-email" / accommodation-only, and sheets titled "Why not
to use it", are skipped.

  python3 import_contacts.py "/Users/spanglew/Desktop/recruiter_careers_emails_quant_ai_software.xlsx"
"""
import datetime as dt, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "contacts_local.json"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BAD = re.compile(r"do not|accommodation|why not to use", re.I)


def load_rows(xlsx):
    z = zipfile.ZipFile(xlsx)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        r = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in r.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    def cv(c):
        v = c.find(f"{NS}v")
        if v is None:
            return ""
        return shared[int(v.text)] if c.get("t") == "s" else (v.text or "")

    sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
    for s in sheets:
        root = ET.fromstring(z.read(s))
        yield [[cv(c) for c in row.findall(f"{NS}c")] for row in root.findall(f".//{NS}row")]


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 import_contacts.py <file.xlsx>")
    xlsx = sys.argv[1]

    by, kept, skipped = {}, 0, 0
    for grid in load_rows(xlsx):
        # find the header row (one that names a Company and an Email column)
        hdr_i = next((i for i, r in enumerate(grid)
                      if any("company" in str(x).lower() for x in r)
                      and any("email" in str(x).lower() for x in r)), None)
        if hdr_i is None:
            continue
        hdr = [str(x).lower() for x in grid[hdr_i]]
        # skip whole "why not to use it" sheets
        if any("why not to use" in h for h in hdr):
            continue

        def col(*names):
            for i, h in enumerate(hdr):
                if any(n in h for n in names):
                    return i
            return None
        ci, ei = col("company"), col("email")
        ti = col("contact type", "purpose")
        si = col("suitability", "status", "purpose")

        for r in grid[hdr_i + 1:]:
            cell = lambda k: r[k] if (k is not None and k < len(r)) else ""
            company = cell(ci).strip()
            status = (cell(si) or "").strip()
            if not company or (status and BAD.search(status)):
                skipped += 1
                continue
            for email in EMAIL_RE.findall(cell(ei)):
                email = email.lower()
                rows = by.setdefault(company, [])
                if any(x["email"] == email for x in rows):
                    continue
                rows.append({"name": "", "title": (cell(ti) or "Careers inbox").strip(),
                             "email": email, "confidence": None, "locked": False,
                             "linkedin": "", "source": "import"})
                kept += 1

    OUT.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                               "byCompany": by}))
    print(f"imported {kept} contacts across {len(by)} companies (skipped {skipped} do-not-email/blank) -> {OUT.name}")


if __name__ == "__main__":
    main()
