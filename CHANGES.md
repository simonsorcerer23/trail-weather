# 🥾 Trail History Weather — Changelog

All changes since the original fork from [imcoref/trailhistoryweather](https://github.com/imcoref/trailhistoryweather/).

---

## 🏗️ Architecture — Modularer Neuaufbau

Das Original war eine einzelne monolithische Datei. Komplett aufgeteilt in Module:

| Modul | Funktion |
|---|---|
| `main.py` | Streamlit App, Sidebar, Layout |
| `config.py` | Trail-Definitionen, Auto-Discovery, Dateipfade |
| `weather_api.py` | Open-Meteo API Calls + Response Processing |
| `map_builder.py` | Folium-Karte mit Heatmap-Overlay |
| `charts.py` | Alle Plotly-Charts (Dark Theme) |
| `elevation_utils.py` | Elevation Profile, Thru-Hike Planner, Naismith's Rule |
| `gpx_upload.py` | GPX-Upload mit pyproj Mile Marker Berechnung |
| `trail_db.py` | SQLite-Persistenz für Custom Trails |

---

## 🌙 Dark Mode Theme

- Komplettes Dark Mode UI (`plotly_dark` Template)
- Sidebar: Gradient-Hintergrund `#1a2332 → #0d1117`
- Metric-Boxen: dunkler Background + Border
- Danger/Warning-Boxen: eigene CSS-Klassen mit Orange/Gelb Gradient
- `.streamlit/config.toml` mit Dark Theme Konfiguration

---

## 🗺️ Multi-Trail Support

**Original:** Nur AZT  
**Jetzt:** 5 Trails mit Auto-Discovery

| Trail | Abkürzung | Timezone |
|---|---|---|
| Arizona Trail | AZT | America/Phoenix |
| Pacific Crest Trail | PCT | America/Los_Angeles |
| Continental Divide Trail | CDT | America/Denver |
| Appalachian Trail | AT | America/New_York |
| Colorado Trail | CT | America/Denver |

- Neue Trails automatisch erkannt wenn `{KEY}_trackpoints.csv` + `{KEY}_MM_points_list_NOBO.csv` vorhanden
- Trail-Embleme (PNG) in Sidebar (non-clickable, `pointer-events: none`)
- Timezone-aware Sunrise/Sunset Berechnung

---

## 🏔️ Elevation Profile

**Original:** Nicht vorhanden (Trackpoint-CSVs hatten keine `elevation` Spalte)

- **Elevation-Daten generiert** via Open-Meteo Elevation API
  - ~500 Punkte pro Trail (`{TRAIL}_elevation.csv`)
  - PCT: Elevation direkt aus GPX extrahiert (einzige GPX mit Höhendaten)
  - Alle 10 Mile-Marker-CSVs angereichert mit `elevation_m` + `elevation_ft`
- **Elevation Profile Chart:**
  - Voller Trail als gedimmte Linie
  - Ausgewählter MM-Range grün hervorgehoben
  - ⛺ Camp-Marker bei aktivem Thru-Hike Plan
  - Hover: Meter + Feet Anzeige

---

## 🥾 Thru-Hike Planner

**Komplett neues Feature.** Berechnet eine Tag-für-Tag Wanderplanung.

### Eingaben (Sidebar):
- 📏 **Daily Pace** (mi/day, flat): 5–40, Default 20
- 🏔️ **Elevation Adjustment** Toggle

### Naismith's Rule:
- +1 Stunde pro 600m Aufstieg
- +1 Stunde pro 800m Abstieg
- 8 Stunden Wanderzeit pro Tag
- **5-Meilen-Wegpunkte** zwischen den großen MM-Intervallen für realistische Tagesplanung

### Ergebnis:
- PCT Beispiel: **130 Tage flach → 176 Tage mit Elevation** bei 20 mi/day
- Automatische Berechnung: Gesamttage, Finish-Datum, Total Gain/Loss, Highest Camp
- Aufklappbare Itinerary-Tabelle: Day | Date | Start MM | End MM | Miles | ↑ Gain | ↓ Loss | Camp Elev

### Auto Date Range:
- Start Date = heute
- End Date = heute + Hike-Dauer (automatisch)
- Passt sich an bei: Trail-Wechsel, Pace-Änderung, Elevation-Toggle

---

## 📏 Mile Marker Range — Auto Reset

- **End MM** setzt sich automatisch auf das Maximum des aktuellen Trails
- Tracking via `_mm_source` Key (`{trail}_{direction}`)
- Bei Trail- oder Richtungswechsel: Keys löschen + `st.rerun()` → Selectbox rendert mit korrektem Default
- Range-Anzeige: `📐 Range: 0 → 2600 (2600 mi)`

---

## 🌅 Sunrise / Sunset Chart

**Original:** Nutzloser "Daylight Hours" Balken (überall ~12h)

**Jetzt:** Sunrise/Sunset Timeline Chart
- Gestapelte Balken: unsichtbarer Spacer bis Sunrise + gelber Daylight-Balken
- Y-Achse: Uhrzeit (6:00–20:00)
- Hover: Sunrise-Zeit, Sunset-Zeit, Daylight-Stunden
- "All Days" Modus: Durchschnitt pro Mile Marker
- **Sunrise/Sunset als UTC int64 Timestamps** → korrekte lokale Zeitzone-Umrechnung

---

## 💨 Wind Chart

**Original:** Nicht vorhanden

- Wind Max + Gusts als separate Linien
- Gusts: orange gestrichelt mit Fill
- **⚠️ 80 km/h Danger-Linie** (rot gestrichelt)

---

## ⚠️ Danger Alerts

**Original:** Nicht vorhanden

Automatische Erkennung gefährlicher Wetterbedingungen:

| Alert | Schwelle | Severity |
|---|---|---|
| 🥶 Freezing | Min ≤ 0°C / 32°F | Warning |
| 🔥 Extreme Heat | Max ≥ 40°C / 104°F | Error |
| 💨 High Wind | Gusts ≥ 80 km/h | Error |
| ⛈️ Dangerous Weather | Thunderstorm, Hailstorm, Heavy Snow etc. | Error |

- Vectorized Pandas-Filter (keine Row-by-Row Iteration)
- Cached mit `@st.cache_data`

---

## 📤 GPX Upload + SQLite Persistenz

**Original:** Kein Upload möglich

- GPX-Datei Upload mit `gpxpy` + `pyproj`
- Automatische Mile Marker Berechnung (konfigurierbares Intervall)
- NOBO + SOBO Richtungen generiert
- **SQLite-Datenbank** (`trail_weather.db`) für persistente Speicherung:
  - 3 Tabellen: `trails`, `trackpoints`, `milemarkers`
  - Laden, Löschen, Liste aller gespeicherten Trails
  - Docker Volume `trail-weather-uploads` für Persistenz
- Sidebar: "💾 Saved Trails" Expander (immer sichtbar)

---

## 📅 Year-over-Year Comparison

**Original:** Nicht vorhanden

- Button "📅 Compare with Previous Year"
- Lädt Wetterdaten für den gleichen Zeitraum im Vorjahr
- Chart: Aktuelle vs. Vorjahr-Temperaturen (solid vs. dashed)
- Aggregation per Mile Marker

---

## 🔗 Share via URL

**Original:** Nicht vorhanden

- Shareable URLs: `https://trail-weather.familiereis.de/?trail=PCT&start=2026-03-01&end=2026-03-05&mm_start=0&mm_end=500`
- URL-Parameter werden beim Laden angewendet
- Copy-Paste Code-Block in Sidebar

---

## 📥 CSV Export

**Original:** Nicht vorhanden

- Download-Button für komplette Wetterdaten als CSV
- Automatischer Dateiname: `{trail}_weather_{start}_{end}.csv`
- Interne Spalten (mit `_` Prefix) werden ausgeblendet

---

## ⚡ Performance-Optimierungen

| Bereich | Optimierung |
|---|---|
| Route auf Karte | Dezimiert auf max. 800 Punkte (`simplify_route`) |
| `st_folium` | `returned_objects=[]` — kein unnötiger Daten-Rücktransfer |
| Weather API | `@st.cache_data(ttl=3600)` |
| CSV Loading | `@st.cache_data` |
| Elevation Profile | `@st.cache_data(ttl=None)` — permanent gecached |
| Danger Alerts | Vectorized Pandas statt Row-by-Row |
| Segment Stats | `@st.cache_data(ttl=None)` |

---

## 🐳 Docker Deployment

**Original:** Kein Docker

- `Dockerfile`: Python 3.11-slim
  - `numpy==1.26.4` + `pandas==2.2.3` (gepinnt für Server ohne X86_V2 CPU-Support)
  - Healthcheck via `python -c "urllib.request.urlopen(...)"` (kein curl im Slim-Image)
- `docker-compose.yml`: Port 8502
  - Volumes: `trail-weather-cache` + `trail-weather-uploads`
  - `restart: unless-stopped`
- `.dockerignore`: `__pycache__`, `.cache`, `.venv`, `uploads/`
- Reverse Proxy: `https://trail-weather.familiereis.de/`

---

## 🗺️ Map Improvements

- **Weather Heatmap Overlay:** Temperature / Precipitation / Wind als Farbverlauf auf der Karte
- **Vereinfachte Route:** `route_coords` Parameter für vorverarbeitete Punkte
- **Fallback-Simplification** falls Route zu groß

---

## 📊 Weather Summary

- Pie Chart: Verteilung der Wetterbedingungen (Top 10)
- 7 Summary Metrics: Max Temp, Min Temp, Total Rain, Total Snow, Max Gust, Sunrise Range, Mile Marker Count

---

## 🧹 Sonstiges

- **Logo non-clickable:** `pointer-events: none` + `user-select: none`
- **Emoji Weather Codes:** WMO-Codes → Emoji + Text Mapping
- **Temperature-Unit Toggle:** °C / °F mit korrekter Umrechnung der Alert-Schwellen
- **NOBO/SOBO Toggle:** Richtungswechsel mit korrektem MM-Reset
- **Eigenes öffentliches Repo:** Ausgelagert aus privatem `hochgericht-server-setup`
