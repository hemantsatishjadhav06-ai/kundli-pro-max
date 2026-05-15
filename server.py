#!/usr/bin/env python3
"""Render-ready Kundli Pro Max server — reads PORT env, otherwise 8787."""
import os, sys, http.server, socketserver, urllib.request, urllib.error, json
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", 8787))
UPSTREAM_BASE = "https://json.freeastrologyapi.com"
HTML_FILE = "KundliProMax.html"
ALLOWED = {
    "horoscope-chart-svg-code", "navamsa-chart-svg-code",
    "planets", "planets/extended",
    "vimsottari/maha-dasas-and-antar-dasas",
    "bhava-chart-svg-code", "chart-svg-code",
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-key")

    def end_headers(self):
        self._cors()
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", ""):
            self.path = "/" + HTML_FILE
        elif parsed.path in ("/pdf", "/pdf/"):
            self.path = "/KundliPDF.html"
        elif parsed.path == "/api/health":
            return self._json({"ok": True, "upstream": UPSTREAM_BASE,
                               "places": os.path.exists("places_compact.json")})
        elif parsed.path == "/places.json":
            for fname in ("places.json", "places_compact.json"):
                if os.path.exists(fname):
                    with open(fname, "rb") as f: data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers(); self.wfile.write(data); return
            return self._json({"error": "places not found"}, 404)
        return super().do_GET()

    def do_POST(self):
        path = self.path.lstrip("/")
        endpoint = path.split("?")[0]
        if not any(endpoint == a for a in ALLOWED):
            return self._json({"error": f"Endpoint not allowed: {endpoint}"}, 403)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        api_key = self.headers.get("x-api-key", "")
        url = f"{UPSTREAM_BASE}/{endpoint}"
        req = urllib.request.Request(url, data=body, method="POST",
            headers={"Content-Type":"application/json", "x-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            self._json({"error": str(e)}, 502)

    def _json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    print(f"🕉  Kundli Pro Max on :{PORT}  (cwd={here})", flush=True)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        try: httpd.serve_forever()
        except KeyboardInterrupt: print("\n👋  Shutting down.")

if __name__ == "__main__":
    main()
