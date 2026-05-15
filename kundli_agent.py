#!/usr/bin/env python3
"""
================================================================
  Kundli Pro Max — AI Agent
================================================================

A standalone CLI + Python library that connects to
  https://kundli-pro-max.onrender.com/api/kundli
and returns a complete Vedic kundli (planets, Lagna, bhav cusps,
Vimshottari dasha, PDF link) for any native.

USE AS A CLI
------------
  python3 kundli_agent.py --name "Gurpreet Kaur" --date 1969-11-21 \\
      --time 07:00:00 --lat 27.4833 --lon 94.9000 --tz 5.5

  python3 kundli_agent.py --csv natives.csv --out reports/    # batch

USE AS A LIBRARY
----------------
  from kundli_agent import KundliAgent
  agent = KundliAgent()
  k = agent.get_kundli(name="Gurpreet Kaur", date="1969-11-21",
                       time="07:00:00", lat=27.4833, lon=94.9000, tz=5.5)
  print(agent.summary(k))            # human-readable text
  print(k['links']['pdf_view'])      # direct PDF URL

USE INSIDE A CLAUDE CONVERSATION
--------------------------------
Paste the JSON output below and ask Claude to interpret. Or wire as
an MCP tool — see README at bottom of this file.

No external dependencies — standard library only.
================================================================
"""
import argparse, csv, json, sys, os
import urllib.request, urllib.error
from datetime import datetime
from typing import Optional, Dict, Any, List

DEFAULT_BASE = os.environ.get("KUNDLI_API", "https://kundli-pro-max.onrender.com")


class KundliAgent:
    """The AI-agent client. Single method does everything."""

    def __init__(self, base_url: str = DEFAULT_BASE, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ----------------------------------------------------------------
    def get_kundli(self, name: str, date: str, time: str,
                   lat: float, lon: float, tz: float,
                   gender: str = "") -> Dict[str, Any]:
        """Hit /api/kundli and return the parsed JSON."""
        payload = {
            "name": name, "gender": gender,
            "date": date, "time": time,
            "latitude": float(lat), "longitude": float(lon), "timezone": float(tz),
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/kundli",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "body": e.read().decode()[:500]}
        except Exception as e:
            return {"error": str(e), "type": type(e).__name__}

    # ----------------------------------------------------------------
    def summary(self, k: Dict[str, Any]) -> str:
        """Return a clean human-readable kundli summary (suitable for chat)."""
        if "error" in k:
            return f"❌ Error: {k['error']}"
        n = k["native"]
        L = k["lagna"]
        lines = [
            "🕉  KUNDLI PRO MAX — Natal Report",
            "=" * 60,
            f"  Native     : {n['name']}  ({n.get('gender', '—')})",
            f"  Born       : {n['date']}  {n['time']}",
            f"  Place      : {n['latitude']}°N, {n['longitude']}°E  (UTC+{n['timezone']})",
            f"  Ayanamsa   : Lahiri {k['ayanamsa']['lahiri_dms']}",
            f"  Julian Day : {k['julian_day']}",
            "",
            f"  LAGNA      : {L['rashi']} ({L['rashi_hindi']}) {L['dms']}",
            f"               Nakshatra {L['nakshatra']}  Pada {L['pada']}",
            f"               Rashi Lord: {L['rashi_lord']}  ·  Nak. Lord: {L['nakshatra_lord']}",
            "",
            "  PLANETARY POSITIONS (Nirayana / Lahiri Sidereal)",
            "  " + "-" * 56,
            f"  {'Graha':<10}{'Rashi':<14}{'Degree':<14}{'Nakshatra-Pada':<22}R/M",
        ]
        for key, p in k["planets"].items():
            retro = "R" if p["retrograde"] else "D"
            lines.append(
                f"  {p['name']:<10}{p['rashi']:<14}{p['dms']:<14}"
                f"{p['nakshatra']+'-'+str(p['pada']):<22}{retro}"
            )

        lines.append("")
        lines.append("  BHAVA CUSPS — Sripati (Parashari)")
        lines.append("  " + "-" * 56)
        for c in k["bhav_sripati"]:
            lines.append(
                f"  Bhava {c['bhava']:2d}  {c['rashi']:<13} {c['dms']}  "
                f"{c['nakshatra']}-{c['pada']}  ({c['rashi_lord']})"
            )

        # Current dasha (find the one that contains "today")
        today = datetime.now().strftime("%Y-%m-%d")
        cur_md, cur_ad = None, None
        for md in k["vimshottari_dasha"]["dashas"]:
            if md["start"] <= today <= md["end"]:
                cur_md = md
                for ad in md["antars"]:
                    if ad["start"] <= today <= ad["end"]:
                        cur_ad = ad; break
                break

        lines.append("")
        lines.append("  VIMSHOTTARI DASHA")
        lines.append("  " + "-" * 56)
        lines.append(f"  Birth Mahadasha : {k['vimshottari_dasha']['balance_lord']}  "
                     f"(balance {k['vimshottari_dasha']['balance_years']} years)")
        if cur_md:
            lines.append(f"  Current Maha    : {cur_md['lord']}  ({cur_md['start']} → {cur_md['end']})")
        if cur_ad:
            lines.append(f"  Current Antar   : {cur_md['lord']}-{cur_ad['lord']}  "
                         f"({cur_ad['start']} → {cur_ad['end']})")

        lines.append("")
        lines.append("  LINKS")
        lines.append("  " + "-" * 56)
        for k_, v in k["links"].items():
            lines.append(f"  {k_:<18}: {v}")
        lines.append("=" * 60)
        return "\n".join(lines)

    # ----------------------------------------------------------------
    def batch(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process many natives. Each row needs keys: name,date,time,latitude,longitude,timezone."""
        out = []
        for r in rows:
            k = self.get_kundli(
                name=r["name"],
                gender=r.get("gender", ""),
                date=r["date"],
                time=r["time"],
                lat=float(r["latitude"]),
                lon=float(r["longitude"]),
                tz=float(r["timezone"]),
            )
            out.append(k)
        return out


# =========================================================
# CLI
# =========================================================
def main():
    p = argparse.ArgumentParser(description="Kundli Pro Max — AI Agent CLI")
    p.add_argument("--name", help="Native's name")
    p.add_argument("--gender", default="", help="Male/Female/Other")
    p.add_argument("--date", help="YYYY-MM-DD")
    p.add_argument("--time", help="HH:MM:SS")
    p.add_argument("--lat", type=float, help="Latitude (°N)")
    p.add_argument("--lon", type=float, help="Longitude (°E)")
    p.add_argument("--tz", type=float, help="Timezone offset in hours (e.g. 5.5 for IST)")
    p.add_argument("--csv", help="Batch CSV file with header: name,gender,date,time,latitude,longitude,timezone")
    p.add_argument("--out", default=".", help="Output dir for batch mode")
    p.add_argument("--base", default=DEFAULT_BASE, help="Override API base URL")
    p.add_argument("--json", action="store_true", help="Output raw JSON instead of text summary")
    args = p.parse_args()

    agent = KundliAgent(base_url=args.base)

    # Batch mode
    if args.csv:
        if not os.path.exists(args.csv):
            print(f"❌ CSV not found: {args.csv}"); sys.exit(1)
        os.makedirs(args.out, exist_ok=True)
        with open(args.csv) as f:
            rows = list(csv.DictReader(f))
        print(f"📂 Loaded {len(rows)} natives from {args.csv}")
        for i, r in enumerate(rows, 1):
            print(f"  [{i}/{len(rows)}] {r.get('name','?')} ...", end=" ", flush=True)
            k = agent.get_kundli(
                name=r["name"], gender=r.get("gender", ""),
                date=r["date"], time=r["time"],
                lat=float(r["latitude"]), lon=float(r["longitude"]),
                tz=float(r["timezone"]),
            )
            fname = (r["name"].replace(" ", "_") + ".json")
            with open(os.path.join(args.out, fname), "w") as f:
                json.dump(k, f, indent=2)
            if "error" in k:
                print(f"❌ {k['error']}")
            else:
                print(f"✓ {k['links']['pdf_view']}")
        print(f"\n✓ Wrote {len(rows)} JSON files to {args.out}/")
        return

    # Single mode
    if not all([args.name, args.date, args.time]) or args.lat is None or args.lon is None or args.tz is None:
        p.error("Single-native mode needs --name --date --time --lat --lon --tz")

    k = agent.get_kundli(
        name=args.name, gender=args.gender,
        date=args.date, time=args.time,
        lat=args.lat, lon=args.lon, tz=args.tz,
    )
    if args.json:
        print(json.dumps(k, indent=2))
    else:
        print(agent.summary(k))


if __name__ == "__main__":
    main()


# ============================================================
# CLAUDE / AI INTEGRATION TEMPLATE
# ============================================================
# Paste this into a Claude conversation when you want Claude to use the agent:
#
#   You have access to a Vedic-astrology AI agent at:
#     POST https://kundli-pro-max.onrender.com/api/kundli
#
#   Body schema:
#     { "name": str, "gender": str, "date": "YYYY-MM-DD",
#       "time": "HH:MM:SS", "latitude": float, "longitude": float,
#       "timezone": float }
#
#   Response: full kundli JSON with these keys:
#     native, computed_at, julian_day, ayanamsa, lagna, planets,
#     bhav_sripati, bhav_samavibhajan, vimshottari_dasha, links
#
#   When the user asks about a person's kundli, ask for name + DOB +
#   time + birthplace (city is fine — convert to lat/lon/timezone).
#   Then call the API, and present:
#     1. Lagna details + Janma Rashi (Moon sign)
#     2. Current Vimshottari Mahadasha and Antardasha
#     3. Any planets the user asks about
#     4. The PDF link (links.pdf_view) — user can open / print
#
# As an MCP tool definition (claude-agent-sdk style):
#
#   tools = [{
#       "name": "compute_kundli",
#       "description": "Compute a Vedic kundli for any native...",
#       "input_schema": {
#           "type": "object",
#           "properties": {
#               "name": {"type": "string"},
#               "date": {"type": "string", "format": "date"},
#               "time": {"type": "string"},
#               "latitude": {"type": "number"},
#               "longitude": {"type": "number"},
#               "timezone": {"type": "number"}
#           },
#           "required": ["name", "date", "time", "latitude", "longitude", "timezone"]
#       }
#   }]
# ============================================================
