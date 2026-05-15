#!/usr/bin/env python3
"""
============================================================
 Kundli Pro Max — CORS Proxy + Local Server
============================================================
 Solves the CORS block when Kundli Pro Max HTML calls
 json.freeastrologyapi.com directly from the browser.

 ALSO serves the HTML file itself so you get a clean
 http://localhost:8787/ deploy with one command.

 USAGE:
   python3 kundli_proxy.py
   # then open http://localhost:8787/

 No external dependencies (Python 3.7+ standard library only).
============================================================
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import json
import os
import sys
from urllib.parse import urlparse

PORT          = 8787
UPSTREAM_BASE = "https://json.freeastrologyapi.com"
HTML_FILE     = "KundliProMax.html"

# Endpoints that the dashboard is allowed to hit (whitelist for safety)
ALLOWED = {
    "horoscope-chart-svg-code",
    "navamsa-chart-svg-code",
    "planets",
    "planets/extended",
    "vimsottari/maha-dasas-and-antar-dasas",
    "bhava-chart-svg-code",
    "chart-svg-code",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves the HTML and proxies POST requests."""

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-key")

    def end_headers(self):
        self._cors()
        super().end_headers()

    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(204)
        self.end_headers()

    # ------------------------------------------------------------------
    def do_GET(self):
        """Serve the HTML or static files."""
        parsed = urlparse(self.path)
        if parsed.path in ("/", ""):
            self.path = "/" + HTML_FILE
        elif parsed.path == "/api/health":
            return self._json({"ok": True, "upstream": UPSTREAM_BASE,
                               "places_loaded": os.path.exists("places.json") or os.path.exists("places_compact.json")})
        elif parsed.path == "/places.json":
            # Serve the compact places database
            for fname in ("places.json", "places_compact.json"):
                if os.path.exists(fname):
                    with open(fname, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            return self._json({"error": "places database not found"}, status=404)
        return super().do_GET()

    # ------------------------------------------------------------------
    def do_POST(self):
        """Proxy POST → freeastrologyapi.com with CORS headers."""
        path = self.path.lstrip("/")

        # Find which upstream endpoint to call (allow multi-segment paths)
        endpoint = path
        if not any(endpoint == a or endpoint.startswith(a + "?") for a in ALLOWED):
            return self._json({"error": f"Endpoint not allowed: {endpoint}",
                               "allowed": sorted(ALLOWED)}, status=403)

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # Build upstream request
        api_key = self.headers.get("x-api-key", "")
        url = f"{UPSTREAM_BASE}/{endpoint}"

        print(f"  → POST {url}  (key={'set' if api_key else 'MISSING'}, body={len(body)}B)")

        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                print(f"    ✓ {resp.status} ({len(payload)}B)")
        except urllib.error.HTTPError as e:
            err_body = e.read()
            print(f"    ✗ HTTP {e.code}: {err_body[:200]}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            print(f"    ✗ EXCEPTION: {e}")
            self._json({"error": str(e), "upstream": url}, status=502)

    # ------------------------------------------------------------------
    def _json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):
        # Friendlier log line
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} — {fmt % args}\n")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    if not os.path.exists(HTML_FILE):
        print(f"⚠  {HTML_FILE} not found in {here}")
        print(f"   Put KundliProMax.html next to this script and re-run.")

    print("=" * 60)
    print("  🕉  Kundli Pro Max — Proxy + Static Server")
    print("=" * 60)
    print(f"  Upstream : {UPSTREAM_BASE}")
    print(f"  Serving  : {here}")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print(f"  Proxy URL (paste into the app): http://localhost:{PORT}")
    print(f"  Health   : http://localhost:{PORT}/api/health")
    print("=" * 60)
    print("  Press Ctrl+C to stop.\n")

    # Bind reuse so restarts are instant
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋  Shutting down.")


if __name__ == "__main__":
    main()
