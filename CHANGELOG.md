# Changelog

---

## 2026-10-06 — Rebuild on fresh Windows; tray app without wmic

### Fixed

- **`dashboard_app.py` collector toggle** — `wmic` is no longer shipped with Windows 11, so the Enable/Disable Collector menu item silently did nothing. Process detection and termination now use PowerShell `Get-CimInstance Win32_Process` (run without a console window). Rebuilt `DTRDashboard.exe` with the same PyInstaller command

### Notes

- Rebuilt on Grafana 13.2.3 with `frser-sqlite-datasource` 4.0.6. The datasource is provisioned with uid `ffnbrga115bswf` (the uid every panel references), so `grafana_dashboard.json` imports unchanged
- When installing the plugin via `grafana cli` from an elevated prompt, pass `--pluginsDir "C:\Program Files\GrafanaLabs\grafana\data\plugins"`. Otherwise the default relative path resolves against the current directory (e.g. `C:\Windows\data\plugins`) and Grafana reports "plugin not registered"

---

## 2026-06-12 — Fix listener map color classification

### Fixed

- **Listener map colors** — replaced the three-layer `filterData` approach (which failed silently in Grafana 13, rendering all dots green) with a single SQL query returning a numeric `status_num` field (`0=active`, `1=recent 24h`, `2=past 7d`) and Grafana threshold coloring on the markers layer. Active listeners now show green, last-24h listeners yellow, last-week listeners red.

---

## 2026-06-10 — Listener geolocation, genre tracking, dashboard layout

### Added

- **Listener geolocation pipeline** — active and recent listeners are shown as coloured dots on a world map in the Grafana dashboard:
  - `pi_stats.py`: geo worker thread geolocates listener IPs in the background via ip-api.com (free, no key); caches results in `listener_data.sqlite`; exposes `/listener-geo` endpoint returning `{ip, lat, lon, country, city, status, last_ping}` per unique IP seen in the last 7 days
  - `collector.py`: polls `/listener-geo` every ~60 s and upserts into a new `listener_locations` table in `dtr_monitor.db`
  - Status: `active` = last ping < 5 min, `recent` = < 24 h, `past` = < 7 d

- **Genre tracking** — `collector.py` fetches `/api/now` from the music server every cycle to get the current genre, stores it in a new `genre` column on the `stream` table; Grafana shows the current genre in a dedicated panel below Artist

- **Genres — last 24 h panel** — vertical bar gauge showing songs played per genre in the last 24 h, derived by joining `track_history` with `stream` on timestamp

- **Listener Locations map** (Grafana Geomap panel) — three marker layers (Active / Last 24 h / Last week) with fixed green / yellow / red colours; static HTML legend panel below the map

- **Plays 7d column** in Recently Played table — shows how many times each song appeared in `track_history` in the last 7 days

### Changed

- **Grafana layout** — Now Playing / Artist / Genre column narrowed to w=6; Listener Locations map at w=10 h=12; Recently Played at w=8; Genres bar gauge fills space below Recently Played; Listener History and Pi stats pushed down for breathing room; all panels in the left column equal-height

- **`collector.py`** — seeds `last_title` from DB on startup to prevent re-recording the currently playing track after a restart; added `cycle` counter for periodic geo polling

- **`pi_stats.py`** — added geo worker + `/listener-geo` endpoint; `recent` threshold changed from 12 h to 24 h

- **`dashboard.py`** — fixed `→` character in print statement (Windows cp1253 encoding)

### Schema changes

- `stream` table: added `genre TEXT` column (migrate existing DB with `ALTER TABLE stream ADD COLUMN genre TEXT`)
- new `listener_locations` table: `ip, lat, lon, country, city, last_ping, status`

---

## 2026-05-28 — Tray dashboard app

### Added

- **`dashboard_app.py`** — minimal Windows tray application built with `pywebview` and `pystray`. Opens the Grafana dashboard (`http://localhost:3000/d/dtr-monitor-v1`) in a frameless WebView2 window with no address bar. Hides to system tray on close; double-click icon to restore, right-click → Quit to exit.

  Compiled to `dist/DTRDashboard.exe` (standalone, no Python required) with:
  ```powershell
  pyinstaller --onefile --windowed --name DTRDashboard --hidden-import webview.platforms.edgechromium --hidden-import webview.platforms.winforms dashboard_app.py
  ```

  Auto-starts at logon via shortcut in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.

### Changed

- **`.gitignore`** — added `CHANGELOG.local.md`, `build/`, `dist/`, `*.spec` (PyInstaller artifacts)
