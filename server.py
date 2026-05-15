#!/usr/bin/env python3
"""Render-ready Kundli Pro Max server — reads PORT env, otherwise 8787.

Routes:
  GET  /                  → dashboard
  GET  /pdf               → PDF generator
  GET  /places.json       → 11k places autocomplete
  GET  /api/health        → liveness probe
  GET  /api/agent.json    → AI-agent contract / OpenAPI-ish spec
  POST /planets, /planets/extended, etc.  → CORS proxy to freeastrologyapi
  POST /api/kundli        → AI-agent endpoint: one call returns full kundli JSON
"""
import os, sys, http.server, socketserver, urllib.request, urllib.error, json, math
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone as tz_mod

PORT = int(os.environ.get("PORT", 8787))
UPSTREAM_BASE = "https://json.freeastrologyapi.com"
DEFAULT_API_KEY = os.environ.get("FREEASTRO_API_KEY", "I1lmUcObH99laDS3k5jeU8zohpFgtYsa0jx33SW3")
HTML_FILE = "KundliProMax.html"
ALLOWED = {
    "horoscope-chart-svg-code", "navamsa-chart-svg-code",
    "planets", "planets/extended",
    "vimsottari/maha-dasas-and-antar-dasas",
    "bhava-chart-svg-code", "chart-svg-code",
}

# ===================== Embedded Astronomy Engine =====================
# (Mirrors KundliPDF.html — provides full kundli computation in Python
#  for the /api/kundli endpoint, so the AI agent gets a single-call answer.)

RAD = math.pi / 180; DEG = 180 / math.pi
RASHIS_HI = ['मेष','वृष','मिथुन','कर्क','सिंह','कन्या','तुला','वृश्चिक','धनु','मकर','कुंभ','मीन']
RASHIS_EN = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
RASHI_LORDS = ['Mars','Venus','Mercury','Moon','Sun','Mercury','Venus','Mars','Jupiter','Saturn','Saturn','Jupiter']
NAKSHATRAS = ['Ashwini','Bharani','Krittika','Rohini','Mrigashira','Ardra','Punarvasu','Pushya','Ashlesha','Magha','PurvaPhalguni','UttaraPhalguni','Hasta','Chitra','Swati','Vishakha','Anuradha','Jyeshtha','Mula','PurvaAshadha','UttaraAshadha','Shravana','Dhanishta','Shatabhisha','PurvaBhadrapada','UttaraBhadrapada','Revati']
NAK_LORDS = ['Ketu','Venus','Sun','Moon','Mars','Rahu','Jupiter','Saturn','Mercury']
NAK_YRS = {'Ketu':7,'Venus':20,'Sun':6,'Moon':10,'Mars':7,'Rahu':18,'Jupiter':16,'Saturn':19,'Mercury':17}
ORDER = ['Ketu','Venus','Sun','Moon','Mars','Rahu','Jupiter','Saturn','Mercury']
P_ORDER = ['sun','moon','mars','mercury','jupiter','venus','saturn','rahu','ketu']
PLANET_NAMES = {'sun':'Sun','moon':'Moon','mars':'Mars','mercury':'Mercury','jupiter':'Jupiter','venus':'Venus','saturn':'Saturn','rahu':'Rahu','ketu':'Ketu'}

def norm360(x):
    x = x % 360
    return x + 360 if x < 0 else x

def dms(d):
    sign = '-' if d < 0 else ''
    d = abs(d)
    D = int(d); m_ = (d - D) * 60; M = int(m_); s = round((m_ - M) * 60)
    return f"{sign}{D:02d}°{M:02d}'{s:02d}\""

def julian_day(y, m, d, h):
    if m <= 2: y -= 1; m += 12
    A = y // 100; B = 2 - A + A // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + h / 24 + B - 1524.5

def lahiri_ayanamsa(JD):
    T = (JD - 2451545.0) / 36525.0
    yr = 2000 + T * 100
    return 23.852380556 + (yr - 2000) * (50.2388 / 3600) + 0.000139 * T * T

def sun_lon(JD):
    T = (JD - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = norm360(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    Mr = M * RAD
    C = (1.914602 - 0.004817 * T) * math.sin(Mr) + 0.019993 * math.sin(2 * Mr) + 0.000289 * math.sin(3 * Mr)
    return norm360(L0 + C - 0.00569 - 0.00478 * math.sin((125.04 - 1934.136 * T) * RAD))

def moon_lon(JD):
    T = (JD - 2451545.0) / 36525.0
    Lp = norm360(218.3164477 + 481267.88123421 * T)
    D = norm360(297.8501921 + 445267.1114034 * T)
    M = norm360(357.5291092 + 35999.0502909 * T)
    Mp = norm360(134.9633964 + 477198.8675055 * T)
    F = norm360(93.2720950 + 483202.0175233 * T)
    l = Lp
    l += 6.288774 * math.sin(Mp * RAD); l += 1.274027 * math.sin((2 * D - Mp) * RAD)
    l += 0.658314 * math.sin(2 * D * RAD); l += 0.213618 * math.sin(2 * Mp * RAD)
    l -= 0.185116 * math.sin(M * RAD); l -= 0.114332 * math.sin(2 * F * RAD)
    l += 0.058793 * math.sin((2 * D - 2 * Mp) * RAD); l += 0.057066 * math.sin((2 * D - M - Mp) * RAD)
    l += 0.053322 * math.sin((2 * D + Mp) * RAD); l += 0.045758 * math.sin((2 * D - M) * RAD)
    return norm360(l)

def helio(planet, JD):
    T = (JD - 2451545.0) / 36525.0
    E = {
        'mercury': (252.250906 + 149472.6746358*T, 0.387098310, 0.20563175),
        'venus':   (181.979801 + 58517.8156760*T,  0.723329820, 0.00677188),
        'earth':   (100.466449 + 35999.3728519*T,  1.000001018, 0.01670862),
        'mars':    (355.433275 + 19140.2993313*T,  1.523679342, 0.09340062),
        'jupiter': (34.351484  + 3034.9056746*T,   5.202603191, 0.04849485),
        'saturn':  (50.077471  + 1222.1137943*T,   9.554909596, 0.05550862),
    }
    PI_LON = {'mercury':77.45645+0.5589*T, 'venus':131.53298, 'earth':102.93735+0.3225*T,
              'mars':336.04084+0.4439*T, 'jupiter':14.331309+0.2155*T, 'saturn':93.056787+0.5665*T}
    L_, a, e = E[planet]; L = norm360(L_); piL = norm360(PI_LON[planet])
    M = norm360(L - piL); E0 = M + (e * DEG) * math.sin(M * RAD)
    for _ in range(5):
        E0 = E0 - (E0 - (e * DEG) * math.sin(E0 * RAD) - M) / (1 - e * math.cos(E0 * RAD))
    Er = E0 * RAD
    v = 2 * math.atan2(math.sqrt(1 + e) * math.sin(Er / 2), math.sqrt(1 - e) * math.cos(Er / 2)) * DEG
    return norm360(v + piL), a * (1 - e * math.cos(Er))

def planet_geo(planet, JD):
    if planet == 'sun':  return sun_lon(JD), False
    if planet == 'moon': return moon_lon(JD), False
    if planet == 'rahu':
        T = (JD - 2451545.0) / 36525.0
        return norm360(125.04452 - 1934.136261 * T + 0.0020708 * T * T), True
    if planet == 'ketu':
        r, _ = planet_geo('rahu', JD); return norm360(r + 180), True
    el, er = helio('earth', JD); pl, pr = helio(planet, JD)
    ex = er * math.cos(el * RAD); ey = er * math.sin(el * RAD)
    px = pr * math.cos(pl * RAD); py = pr * math.sin(pl * RAD)
    l1 = norm360(math.atan2(py - ey, px - ex) * DEG)
    el2, er2 = helio('earth', JD + 1); pl2, pr2 = helio(planet, JD + 1)
    ex2 = er2 * math.cos(el2 * RAD); ey2 = er2 * math.sin(el2 * RAD)
    px2 = pr2 * math.cos(pl2 * RAD); py2 = pr2 * math.sin(pl2 * RAD)
    l2 = norm360(math.atan2(py2 - ey2, px2 - ex2) * DEG)
    diff = l2 - l1
    if diff > 180: diff -= 360
    if diff < -180: diff += 360
    return l1, diff < 0

def lst(JD, lon):
    T = (JD - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (JD - 2451545.0) + 0.000387933 * T * T
    return norm360(norm360(g) + lon)

def obliquity(JD):
    T = (JD - 2451545.0) / 36525.0
    return 23.43929111 - 0.0130041667 * T

def ascendant(JD, lat, lon):
    ramc = lst(JD, lon) * RAD; eps = obliquity(JD) * RAD; phi = lat * RAD
    a = norm360(math.atan2(-math.cos(ramc), math.sin(ramc) * math.cos(eps) + math.tan(phi) * math.sin(eps)) * DEG)
    mc = norm360(math.atan2(math.sin(ramc), math.cos(ramc) * math.cos(eps)) * DEG)
    if norm360(a - mc) > 180: a = norm360(a + 180)
    return a

def mc_lon(JD, lon):
    ramc = lst(JD, lon) * RAD; eps = obliquity(JD) * RAD
    return norm360(math.atan2(math.sin(ramc), math.cos(ramc) * math.cos(eps)) * DEG)

def sripati_cusps(JD, lat, lon):
    asc = ascendant(JD, lat, lon); mc = mc_lon(JD, lon)
    ic = norm360(mc + 180); dsc = norm360(asc + 180)
    c = [0.0] * 12
    c[0] = asc; c[3] = ic; c[6] = dsc; c[9] = mc
    arc = lambda a, b: norm360(b - a)
    c[1] = norm360(asc + arc(asc, ic) / 3); c[2] = norm360(asc + 2 * arc(asc, ic) / 3)
    c[4] = norm360(ic + arc(ic, dsc) / 3); c[5] = norm360(ic + 2 * arc(ic, dsc) / 3)
    c[7] = norm360(dsc + arc(dsc, mc) / 3); c[8] = norm360(dsc + 2 * arc(dsc, mc) / 3)
    c[10] = norm360(mc + arc(mc, asc) / 3); c[11] = norm360(mc + 2 * arc(mc, asc) / 3)
    return c

def rashi_of(l): return int(norm360(l) // 30)
def deg_in_rashi(l): return norm360(l) % 30
def nakshatra_of(l):
    sp = 360 / 27; i = int(norm360(l) // sp); p = norm360(l) - i * sp
    return {'idx': i, 'name': NAKSHATRAS[i], 'lord': NAK_LORDS[i % 9], 'pada': int(p // (sp / 4)) + 1}

def vim_dashas(moon_l, birth):
    sp = 360 / 27; ni = int(norm360(moon_l) // sp); pos = norm360(moon_l) - ni * sp
    lord = NAK_LORDS[ni % 9]; yrs = NAK_YRS[lord]; el = (pos / sp) * yrs; bal = yrs - el
    dashas = []
    cur = birth - timedelta(seconds=el * 365.25 * 86400)
    start = ORDER.index(lord)
    for i in range(9):
        L = ORDER[(start + i) % 9]; y = NAK_YRS[L]
        end = cur + timedelta(seconds=y * 365.25 * 86400)
        antars = []; a_cur = cur
        for j in range(9):
            A = ORDER[(ORDER.index(L) + j) % 9]; ay = (y * NAK_YRS[A]) / 120
            a_end = a_cur + timedelta(seconds=ay * 365.25 * 86400)
            antars.append({'lord': A, 'start': a_cur.strftime('%Y-%m-%d'), 'end': a_end.strftime('%Y-%m-%d')})
            a_cur = a_end
        dashas.append({'lord': L, 'years': y, 'start': cur.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'), 'antars': antars})
        cur = end
    return {'balance_lord': lord, 'balance_years': round(bal, 4), 'dashas': dashas}

def compute_kundli(name, gender, date_str, time_str, lat, lon, tz):
    """Top-level function: return full kundli JSON for the AI agent."""
    Y, M, D = map(int, date_str.split('-'))
    parts = time_str.split(':')
    hh, mm = int(parts[0]), int(parts[1]); ss = int(parts[2]) if len(parts) > 2 else 0
    ut_h = hh + mm / 60 + ss / 3600 - tz
    JD = julian_day(Y, M, D, ut_h)
    birth = datetime(Y, M, D, hh, mm, ss, tzinfo=tz_mod(timedelta(hours=tz)))
    ayan = lahiri_ayanamsa(JD)
    kp_ayan = ayan - 5.583 / 60

    planets = {}
    for p in P_ORDER:
        trop, retro = planet_geo(p, JD)
        sid = norm360(trop - ayan)
        r = rashi_of(sid); n = nakshatra_of(sid)
        planets[p] = {
            'name': PLANET_NAMES[p],
            'longitude_sidereal': round(sid, 6),
            'longitude_tropical': round(trop, 6),
            'rashi': RASHIS_EN[r],
            'rashi_hindi': RASHIS_HI[r],
            'rashi_lord': RASHI_LORDS[r],
            'degree': round(deg_in_rashi(sid), 6),
            'dms': dms(deg_in_rashi(sid)),
            'nakshatra': n['name'],
            'pada': n['pada'],
            'nakshatra_lord': n['lord'],
            'retrograde': retro,
        }

    asc_trop = ascendant(JD, lat, lon)
    asc_sid = norm360(asc_trop - ayan)
    asc_r = rashi_of(asc_sid); asc_n = nakshatra_of(asc_sid)

    cusps_trop = sripati_cusps(JD, lat, lon)
    cusps_sid = [norm360(c - ayan) for c in cusps_trop]

    bhav_cusps = []
    for i, c in enumerate(cusps_sid):
        r = rashi_of(c); n = nakshatra_of(c)
        bhav_cusps.append({
            'bhava': i + 1, 'rashi': RASHIS_EN[r], 'rashi_lord': RASHI_LORDS[r],
            'degree': round(deg_in_rashi(c), 6), 'dms': dms(deg_in_rashi(c)),
            'nakshatra': n['name'], 'pada': n['pada'], 'nakshatra_lord': n['lord'],
        })

    # Bhav samavibhajan (Equal House) — each bhava is 30° from Lagna
    equal_cusps = [norm360(asc_sid + i * 30) for i in range(12)]
    bhav_equal = []
    for i, c in enumerate(equal_cusps):
        r = rashi_of(c)
        bhav_equal.append({'bhava': i + 1, 'rashi': RASHIS_EN[r], 'degree': round(deg_in_rashi(c), 6)})

    dasha = vim_dashas(planets['moon']['longitude_sidereal'], birth)

    # Build URL to PDF tool with auto-render
    from urllib.parse import quote
    pdf_url = (f"https://kundli-pro-max.onrender.com/pdf?"
               f"name={quote(name)}&gender={quote(gender or 'Male')}"
               f"&date={date_str}&time={time_str}"
               f"&lat={lat}&lon={lon}&tz={tz}&auto=1")
    dashboard_url = (f"https://kundli-pro-max.onrender.com/?"
                     f"name={quote(name)}&date={date_str}&time={time_str}"
                     f"&lat={lat}&lon={lon}&tz={tz}")

    return {
        'native': {
            'name': name, 'gender': gender, 'date': date_str, 'time': time_str,
            'latitude': lat, 'longitude': lon, 'timezone': tz,
        },
        'computed_at': datetime.now(tz_mod.utc).isoformat(),
        'julian_day': round(JD, 6),
        'ayanamsa': {'lahiri': round(ayan, 6), 'kp': round(kp_ayan, 6),
                     'lahiri_dms': dms(ayan), 'kp_dms': dms(kp_ayan)},
        'lagna': {
            'longitude': round(asc_sid, 6), 'dms': dms(deg_in_rashi(asc_sid)),
            'rashi': RASHIS_EN[asc_r], 'rashi_hindi': RASHIS_HI[asc_r],
            'rashi_lord': RASHI_LORDS[asc_r],
            'nakshatra': asc_n['name'], 'pada': asc_n['pada'],
            'nakshatra_lord': asc_n['lord'],
        },
        'planets': planets,
        'bhav_sripati': bhav_cusps,
        'bhav_samavibhajan': bhav_equal,
        'vimshottari_dasha': dasha,
        'links': {
            'pdf_view': pdf_url,
            'pdf_print_ready': pdf_url + '&print=1',
            'dashboard': dashboard_url,
            'api_docs': 'https://kundli-pro-max.onrender.com/api/agent.json',
        },
    }
# ===================== End Astronomy Engine =====================


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
        elif parsed.path == "/api/agent.json":
            return self._json({
                "name": "Kundli Pro Max Agent",
                "version": "1.0",
                "description": "Compute a full Vedic kundli from birth details. Returns all planet positions (Nirayana/Lahiri sidereal), Lagna, Bhav cusps (Sripati + Samavibhajan), and 120-year Vimshottari Dasha. Also returns shareable PDF and dashboard URLs.",
                "base_url": "https://kundli-pro-max.onrender.com",
                "endpoints": {
                    "POST /api/kundli": {
                        "description": "Compute and return full kundli JSON",
                        "request": {
                            "name": "string (required) — native's name",
                            "gender": "string (optional) — Male/Female/Other",
                            "date": "YYYY-MM-DD (required) — date of birth",
                            "time": "HH:MM:SS (required) — time of birth, local",
                            "latitude": "float (required) — birthplace latitude, degrees N",
                            "longitude": "float (required) — birthplace longitude, degrees E",
                            "timezone": "float (required) — UTC offset hours (e.g. 5.5 for IST)"
                        },
                        "response_keys": ["native", "computed_at", "julian_day", "ayanamsa", "lagna", "planets", "bhav_sripati", "bhav_samavibhajan", "vimshottari_dasha", "links"]
                    }
                },
                "example_request": {
                    "name": "Gurpreet Kaur", "gender": "Female",
                    "date": "1969-11-21", "time": "07:00:00",
                    "latitude": 27.4833, "longitude": 94.9000, "timezone": 5.5
                }
            })
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

        # ===== AI Agent endpoint =====
        if endpoint == "api/kundli":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                required = ["name", "date", "time", "latitude", "longitude", "timezone"]
                missing = [k for k in required if k not in body]
                if missing:
                    return self._json({"error": "Missing required fields",
                                       "missing": missing,
                                       "schema": "GET /api/agent.json for full schema"}, 400)
                result = compute_kundli(
                    name=body["name"],
                    gender=body.get("gender", ""),
                    date_str=body["date"],
                    time_str=body["time"],
                    lat=float(body["latitude"]),
                    lon=float(body["longitude"]),
                    tz=float(body["timezone"]),
                )
                return self._json(result)
            except Exception as e:
                return self._json({"error": str(e), "type": type(e).__name__}, 500)

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
