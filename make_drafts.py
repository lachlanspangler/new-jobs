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
import argparse, base64, datetime as dt, json, os, sys, time, urllib.parse, urllib.request, webbrowser
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
            if subj.startswith("Software / quant roles at "):
                _api(token, "DELETE", f"/gmail/v1/users/me/drafts/{d['id']}")
                deleted += 1
        page = res.get("nextPageToken")
        if not page:
            break
    return deleted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--template", default="email_template.txt")
    ap.add_argument("--purge", action="store_true", help="delete drafts this tool created, then exit")
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
    done = set(json.loads(DRAFTED.read_text())) if DRAFTED.exists() else set()

    # flatten contacts that have a usable email and aren't already drafted
    todo = []
    for company, contacts in by.items():
        for c in contacts:
            email = c.get("email")
            if not email or c.get("locked") or email in done:
                continue
            first = (c.get("name") or "there").split(" ")[0]
            todo.append((company, email, first))
    todo = todo[: args.limit]

    if not todo:
        print("No new contacts with unlocked emails to draft. "
              "(Run fetch_recruiters.py with a Hunter key first.)")
        return

    if args.dry_run:
        for company, email, first in todo:
            print(f"DRAFT -> {email:34} {first} @ {company}")
        print(f"\n{len(todo)} drafts would be created (dry run).")
        return

    token = access_token()
    made = 0
    for company, email, first in todo:
        subject = f"Software / quant roles at {company}"
        body = template.format(first=first, company=company)
        try:
            create_draft(token, email, subject, body)
            done.add(email); made += 1
            print(f"drafted -> {email} ({company})")
        except Exception as e:
            print(f"error {email}: {e}")
        time.sleep(0.3)
    DRAFTED.write_text(json.dumps(sorted(done)))
    print(f"\nCreated {made} Gmail drafts. Open Gmail → Drafts, review, and send.")


if __name__ == "__main__":
    main()
