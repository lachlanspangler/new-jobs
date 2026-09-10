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
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCOPE = "https://www.googleapis.com/auth/gmail.compose"
TOKEN = ROOT / "token.json"
CLIENT = ROOT / "client_secret.json"
DRAFTED = ROOT / "drafted.json"
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


def create_draft(token, to, subject, body):
    msg = MIMEText(body)
    msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    data = json.dumps({"message": {"raw": raw}}).encode()
    req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                                 data=data, headers={"Authorization": f"Bearer {token}",
                                                     "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--template", default="email_template.txt")
    args = ap.parse_args()

    tpath = ROOT / args.template
    template = tpath.read_text() if tpath.exists() else DEFAULT_TEMPLATE

    rj = json.loads((ROOT / "docs" / "recruiters.json").read_text())
    done = set(json.loads(DRAFTED.read_text())) if DRAFTED.exists() else set()

    # flatten contacts that have a usable email and aren't already drafted
    todo = []
    for company, contacts in (rj.get("byCompany") or {}).items():
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
