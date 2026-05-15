# Kundli Pro Max · Classic Edition

A single-dashboard Vedic astrology workstation. Light parchment theme, classical typography, and **everything visible on one scrolling page**: 6 main charts on top, then Basic Details, Nirayana, Sayana + aspects, KP with sub-lords, Bhav Chalit, all 12 divisional vargas, and full 3-level Vimshottari Dasha.

## Files

| File | What it does |
|---|---|
| `KundliProMax.html` | The dashboard. Open in any browser. Self-contained, no build step. |
| `kundli_proxy.py`   | Python 3 sidecar — serves the HTML **and** proxies API requests to `json.freeastrologyapi.com` so CORS doesn't block them. |

## Two ways to run

### 1. Just open the HTML (Local engine only)

Double-click `KundliProMax.html`. The built-in VSOP87 + ELP-2000 engine computes everything offline (Sun, Moon, all planets, Rahu/Ketu, Lahiri & KP ayanamsa, Placidus cusps, Vimshottari dashas, vargas). Set **API Mode** to **Local Only** to skip API calls cleanly.

### 2. Run the proxy (Swiss Ephemeris-grade API)

```bash
cd /path/to/this/folder
python3 kundli_proxy.py
```

Then open **http://localhost:8787/** — the proxy serves the HTML *and* forwards `/planets`, `/planets/extended`, `/horoscope-chart-svg-code`, `/navamsa-chart-svg-code`, `/vimsottari/maha-dasas-and-antar-dasas` to the upstream API with the `x-api-key` header attached.

In the dashboard, leave **Proxy URL** blank when accessed via `localhost:8787` (same-origin) — the requests will go to the proxy automatically. If you open the HTML from a different origin, paste `http://localhost:8787` into the Proxy URL field.

## Shareable URLs (the "scheduler")

Every chart is fully addressable via URL parameters. Click **🔗 Share** to copy a link like:

```
KundliProMax.html?name=Amar%20Kumar&gender=Male&date=2002-05-05&time=00:00:00&lat=28.6139&lon=77.2090&tz=5.5&mode=hybrid
```

Send that to anyone — they'll see exactly the same dashboard with all charts pre-computed. Save bookmarks per native. Drop the link into a calendar invite, a CRM note, or a chat — it always renders the same kundli.

## What's on the dashboard (top → bottom)

1. **Hero header** — name, gender, DOB, time, place strip
2. **6 chart grid** — Lagna (D-1), Navamsa (D-9), Sayana (Tropical), KP, Bhav Chalit, Chandra. Each tagged with a colored pill so you know which is which at a glance.
3. **Birth Particulars** — Lagna, Janma Rashi, Panchang, Sunrise/Sunset, Geographic, Samvat, Dasha balance
4. **Nirayana** — Full Graha · Rashi · Ansh · R/M · Nakshatra · Pada · Lords table + 12 Bhava cusps
5. **Sayana** — Tropical planet table + full 12×12 aspect grid (CONJ / OPPO / TRIN / SQUR / SEXT / QUIN / SESQ / QUQU)
6. **KP** — 4-level lord chain (Sign → Star → Sub → Sub-Sub) for every planet + cuspal sub-lords
7. **Bhav Chalit** — actual Placidus house occupancy
8. **Vargas grid** — D-1, D-2, D-3, D-7, D-9, D-10, D-12, D-16, D-20, D-24, D-30, D-60
9. **Vimshottari Dasha** — collapsible 3-level: Maha → Antar → Pratyantar
10. **Raw API diagnostic** — endpoint-by-endpoint JSON responses for debugging

## Color grading (subtle classic)

| Token | Role | Hex |
|---|---|---|
| Paper | Background | `#fdfaf2` |
| Paper-2 | Card surface | `#f7f0dc` |
| Ink | Body text | `#2c2418` |
| Maroon | Primary accent (Nirayana) | `#7a1f1f` |
| Navy | Secondary (KP) | `#1e3a5f` |
| Gold | Highlight (Sayana) | `#b8860b` |
| Sage | Success (Bhav Chalit) | `#4a6741` |
| Rust | Retrograde / Navamsa | `#b04a2f` |

Typography: **Cormorant Garamond** for serif headings (classical feel), **Inter** for tables/UI, **Noto Sans Devanagari** for Sanskrit.

## API endpoint mapping (the n8n workflow, ported)

| # | Tab data source | Endpoint | Ayanamsha |
|---|---|---|---|
| 1 | Lagna SVG | `horoscope-chart-svg-code` | lahiri |
| 2 | KP positions | `planets/extended` | lahiri |
| 3 | Nirayana table | `planets` | lahiri |
| 4 | Bhav Chalit | `planets/extended` | lahiri |
| 5 | Sayana | `planets` | sayana |
| 6 | Navamsa SVG | `navamsa-chart-svg-code` | lahiri |
| 7 | Vimshottari | `vimsottari/maha-dasas-and-antar-dasas` | lahiri |

All 7 fire **in parallel** from the browser; results stream into the dashboard as they arrive.

## Buttons in the header bar

- **⚡ Generate** — recompute with current inputs
- **🔗 Share** — copy shareable URL to clipboard
- **🖨 Print** — clean print/PDF (hides input bar, expands all dashas)
- **💾 Export JSON** (footer) — dump the entire computed state to a JSON file

## Deploy options

| Where | How |
|---|---|
| Local | `python3 kundli_proxy.py` — done |
| Static host (Netlify / Vercel / GitHub Pages) | Upload `KundliProMax.html` — works in **Local** mode immediately. Set API Mode to "Local Only" or deploy the proxy separately. |
| Cloudflare Worker | Reimplement the 30-line proxy in a Worker, set Proxy URL to the worker domain. |
| Docker | `python:3.11-slim` + `COPY . /app` + `CMD ["python","kundli_proxy.py"]` — 5 lines. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| "API Blocked (CORS)" pill | Run the proxy and use `http://localhost:8787/` |
| Status pill stays "Computing" | Open browser devtools → Network tab to see which endpoint hung |
| Local dasha doesn't match Parashara's Light to the second | VSOP87/ELP-2000 truncated series is accurate to ~1 arc-minute. Use the API (via proxy) for second-level accuracy. |
| API returns 401 / 403 | Check the API Key field — the default key may be rate-limited |
| Devanagari shows as boxes | Use Chrome/Firefox/Safari — they pull Noto Sans Devanagari from Google Fonts automatically |

🕉 Built as a single self-contained dashboard. Open, share, print.
