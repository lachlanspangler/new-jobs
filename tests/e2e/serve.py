"""Serve docs/ for the browser tests, with /jobs.json replaced by a small fixture (no network, deterministic)."""
import functools, http.server, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("jobs.fixture.json")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0].endswith("/jobs.json"):
            body = FIXTURE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8612
http.server.ThreadingHTTPServer(("127.0.0.1", port),
                                functools.partial(Handler, directory=str(ROOT / "docs"))).serve_forever()
