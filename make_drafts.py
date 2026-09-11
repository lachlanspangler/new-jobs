#!/usr/bin/env python3
"""Create personalized Gmail DRAFTS (never sends) for the recruiter contacts in
docs/recruiters.json, so you can review each and hit send yourself.

Standard library only. One-time setup:

  1. Google Cloud Console -> create a project -> enable the "Gmail API".
  2. APIs & Services -> Credentials -> Create OAuth client ID -> type "Desktop app".
     Download the JSON as client_secret.json into this folder (git-ignored).
  3. Run:  python3 make_drafts.py
     A browser opens once to authorize (scope: create drafts only). A token.json
     is cached so later runs are non-interactive.

Flags:
  --limit N     cap number of drafts created (default 25)
  --dry-run     print what would be drafted, create nothing
  --template F  use a different template file (default email_template.txt)

It uses the gmail.compose scope (create drafts only) — it cannot send or read
mail. Already-drafted addresses are remembered in drafted.json to avoid dupes.
"""
import argparse, base64, datetime as dt, json, os, socket, subprocess, sys, time, urllib.parse, urllib.request, webbrowser
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCOPE = "https://www.googleapis.com/auth/gmail.compose"
TOKEN = ROOT / "token.json"
CLIENT = ROOT / "client_secret.json"
DRAFTED = ROOT / "drafted.json"
ATTACH_DIR = ROOT / "attachments"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/"

DEFAULT_TEMPLATE = """Hi {first},

I'm Lachlan Spangler, a software engineer at Amazon with a quant / low-latency background (matching engines, execution, market-microstructure tooling). I'm exploring software and quantitative roles at {company} and would love to connect about current openings.

A bit of my work: https://github.com/lachlanspangler  ·  https://linkedin.com/in/lachlan-spangler

Would you be open to a quick chat, or point me to the right person? Happy to send my resume. Totally understand if now's not the time.

Thanks,
Lachlan Spangler
"""


def client_creds():
    if CLIENT.exists():
        d = json.loads(CLIENT.read_text())
        d = d.get("installed") or d.get("web") or d
        return d["client_id"], d["client_secret"]
    cid, cs = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and cs:
        return cid, cs
    sys.exit("Missing OAuth client. Add client_secret.json (Desktop app) or set "
             "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET. See the header for setup.")


def _post_token(fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def authorize():
    cid, cs = client_creds()
    params = urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    code_box = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path).query
            code_box["code"] = urllib.parse.parse_qs(q).get("code", [None])[0]
            self.send_response(200); self.end_headers()
            self.wfile.write(b"<h2>Authorized. You can close this tab and return to the terminal.</h2>")
        def log_message(self, *a): pass

    print("Opening browser to authorize (create-drafts only)…")
    webbrowser.open(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
    srv = HTTPServer(("localhost", PORT), Handler)
    srv.handle_request()
    srv.server_close()
    if not code_box.get("code"):
        sys.exit("No auth code received.")
    tok = _post_token({"code": code_box["code"], "client_id": cid, "client_secret": cs,
                       "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    tok["_expiry"] = time.time() + tok.get("expires_in", 3600) - 60
    TOKEN.write_text(json.dumps(tok))
    return tok["access_token"]


def access_token():
    if not TOKEN.exists():
        return authorize()
    tok = json.loads(TOKEN.read_text())
    if tok.get("_expiry", 0) > time.time():
        return tok["access_token"]
    cid, cs = client_creds()
    if not tok.get("refresh_token"):
        return authorize()
    new = _post_token({"client_id": cid, "client_secret": cs,
                       "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    tok.update(new); tok["_expiry"] = time.time() + new.get("expires_in", 3600) - 60
    TOKEN.write_text(json.dumps(tok))
    return tok["access_token"]


def greeting_for(name, company):
    first = name.split(" ")[0] if name else ""
    return first if first else f"{company} team"


_MX = {}
def deliverable(email):
    """True if the email's domain plausibly accepts mail (has MX, or at least
    resolves). Skips only clearly dead/typo domains to protect deliverability."""
    dom = email.rsplit("@", 1)[-1].lower()
    if dom in _MX:
        return _MX[dom]
    ok = False
    try:
        out = subprocess.run(["nslookup", "-query=mx", dom], capture_output=True,
                             text=True, timeout=6).stdout.lower()
        ok = "mail exchanger" in out
    except Exception:
        pass
    if not ok:
        try:
            socket.getaddrinfo(dom, None)  # domain at least resolves
            ok = True
        except Exception:
            ok = False
    _MX[dom] = ok
    return ok


def build_message(to, subject, body):
    files = sorted(p for p in ATTACH_DIR.glob("*") if p.is_file()) if ATTACH_DIR.exists() else []
    if not files:
        msg = MIMEText(body)
    else:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body))
        for p in files:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(p.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=p.name)
            msg.attach(part)
    msg["To"] = to
    msg["Subject"] = subject
    return msg


def _api(token, method, path, data=None):
    req = urllib.request.Request("https://gmail.googleapis.com" + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def create_draft(token, to, subject, body):
    raw = base64.urlsafe_b64encode(build_message(to, subject, body).as_bytes()).decode()
    return _api(token, "POST", "/gmail/v1/users/me/drafts", json.dumps({"message": {"raw": raw}}).encode()).get("id")


def purge(token):
    """Delete drafts this tool created (subject starts with the outreach prefix)."""
    deleted, page = 0, None
    while True:
        res = _api(token, "GET", "/gmail/v1/users/me/drafts?maxResults=100" + (f"&pageToken={page}" if page else ""))
        for d in res.get("drafts", []):
            meta = _api(token, "GET", f"/gmail/v1/users/me/drafts/{d['id']}?format=metadata&metadataHeaders=Subject")
            hdrs = (meta.get("message", {}).get("payload", {}) or {}).get("headers", [])
            subj = next((h["value"] for h in hdrs if h["name"].lower() == "subject"), "")
            if any(p in subj for p in ("Software / quant roles at ", "Amazon SDE interested in ")):
                _api(token, "DELETE", f"/gmail/v1/users/me/drafts/{d['id']}")
                deleted += 1
        page = res.get("nextPageToken")
        if not page:
            break
    return deleted


def write_outreach(records):
    """Publish a per-company emailed tally (counts + dates only, no addresses) for the site."""
    by = {}
    for r in records:
        co, d = r.get("company") or "?", r.get("date") or ""
        e = by.setdefault(co, {"emailed": 0, "first": d, "last": d})
        e["emailed"] += 1
        if d:
            e["first"] = min(e["first"] or d, d)
            e["last"] = max(e["last"] or d, d)
    (ROOT / "docs" / "outreach.json").write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total": len(records), "byCompany": by}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--template", default="email_template.txt")
    ap.add_argument("--purge", action="store_true", help="delete drafts this tool created, then exit")
    ap.add_argument("--generic", action="store_true", help="only generic role inboxes (no named person)")
    ap.add_argument("--one-per-company", action="store_true", help="at most one draft per company")
    ap.add_argument("--no-mx", action="store_true", help="skip the MX/domain deliverability check")
    args = ap.parse_args()

    if args.purge:
        n = purge(access_token())
        if DRAFTED.exists():
            DRAFTED.unlink()
        print(f"Deleted {n} tool-created drafts and reset the history. Re-run to recreate them.")
        return

    tpath = ROOT / args.template
    template = tpath.read_text() if tpath.exists() else DEFAULT_TEMPLATE

    by = json.loads((ROOT / "docs" / "recruiters.json").read_text()).get("byCompany", {})
    local = ROOT / "contacts_local.json"
    if local.exists():  # merge in the git-ignored imported list
        for company, rows in json.loads(local.read_text()).get("byCompany", {}).items():
            have = {x.get("email", "").lower() for x in by.get(company, [])}
            by.setdefault(company, []).extend(r for r in rows if r.get("email", "").lower() not in have)
    records = []
    if DRAFTED.exists():
        raw = json.loads(DRAFTED.read_text())
        records = [r if isinstance(r, dict) else {"email": r} for r in raw]
    done = {r["email"] for r in records}

    # flatten contacts that have a usable email and aren't already drafted
    todo = []
    for company, contacts in by.items():
        for c in contacts:
            email = c.get("email")
            if not email or c.get("locked") or email in done:
                continue
            name = (c.get("name") or "").strip()
            todo.append((company, email, name))
    if args.generic:
        todo = [t for t in todo if not t[2]]          # only no-name role inboxes
    if args.one_per_company:
        seen, uniq = set(), []
        for t in todo:
            if t[0] in seen:
                continue
            seen.add(t[0]); uniq.append(t)
        todo = uniq
    # take up to --limit deliverable contacts (skip dead/typo domains unless --no-mx)
    picked, skipped = [], 0
    for t in todo:
        if len(picked) >= args.limit:
            break
        if not args.no_mx and not deliverable(t[1]):
            print(f"skip (no MX / dead domain): {t[1]}"); skipped += 1; continue
        picked.append(t)
    todo = picked
    if skipped:
        print(f"({skipped} contact(s) skipped for undeliverable domains)")

    if not todo:
        print("No new contacts with unlocked emails to draft. "
              "(Run fetch_recruiters.py with a Hunter key first.)")
        return

    if args.dry_run:
        for company, email, name in todo:
            print(f"DRAFT -> {email:34} Hi {greeting_for(name, company)} @ {company}")
        print(f"\n{len(todo)} drafts would be created (dry run).")
        return

    try:
        with_roles = {j["company"] for j in json.loads((ROOT / "docs" / "jobs.json").read_text()).get("jobs", [])}
    except Exception:
        with_roles = set()

    token = access_token()
    today = dt.date.today().isoformat()
    made = 0
    for company, email, name in todo:
        subject = f"Amazon SDE interested in {company}"
        roles = " I'm especially keen on your current openings." if company in with_roles else ""
        body = template.format(greeting=greeting_for(name, company), company=company, roles=roles)
        try:
            create_draft(token, email, subject, body)
            records.append({"email": email, "company": company, "date": today})
            made += 1
            print(f"drafted -> {email} ({company})")
        except Exception as e:
            print(f"error {email}: {e}")
        time.sleep(0.3)
    DRAFTED.write_text(json.dumps(records, indent=0))
    write_outreach(records)
    print(f"\nCreated {made} Gmail drafts ({len(records)} total logged). Open Gmail → Drafts, review, and send.")


if __name__ == "__main__":
    main()
