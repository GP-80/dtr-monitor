# DTR Monitor

Real-time monitoring dashboard for [Deep Trip Radio](https://deeptripradio.net/) — a 24/7 psychedelic internet radio station running on a Raspberry Pi Zero W.

Built with Python (stdlib only) + SQLite + Grafana.

---

## Architecture

```
Raspberry Pi                          Windows PC
────────────────────────────────      ──────────────────────────────────
icecast2        :8000  ──────────►   collector.py  (polls every 15 s)
pi_stats.py     :8001  ──────────►        │
                                          ▼
                                    dtr_monitor.db  (SQLite)
                                          │
                                          ▼
                                    Grafana  :3000
```

- **`collector.py`** — runs on Windows; polls icecast2 for stream status and `pi_stats.py` for system metrics every 15 seconds; writes to a local SQLite database
- **`pi_stats.py`** — lightweight HTTP server on the Pi (port 8001); serves CPU, RAM, temperature, disk, WiFi, uptime, and service status as JSON
- **`dtr_monitor.db`** — SQLite database; holds 7 days of rolling data (~15 MB max)
- **Grafana** — reads the SQLite database via the `frser-sqlite-datasource` plugin and displays the dashboard

---

## Files

| File | Description |
|---|---|
| `collector.py` | Windows-side poller — polls Pi every 15 s, writes to SQLite |
| `pi_stats.py` | Pi-side stats server — serves system metrics on port 8001 |
| `build_dashboard.py` | Generates `grafana_dashboard.json` — run after any dashboard changes |
| `grafana_dashboard.json` | Grafana dashboard definition — import this into Grafana |
| `GRAFANA_SETUP.md` | Step-by-step Grafana setup guide |
| `dashboard.py` | Legacy Python/CivetWeb dashboard (superseded by Grafana) |
| `stream_watch.py` | Standalone stream health monitor (diagnostic tool) |

---

## Prerequisites

### Raspberry Pi
- icecast2 running on port 8000
- Python 3.7+

### Windows PC
- Python 3.7+ (stdlib only — no pip installs needed for collector)
- [Grafana](https://grafana.com/grafana/download?platform=windows) installed as a Windows service

---

## Setup

### Step 1 — Pi: run pi_stats.py

Copy `pi_stats.py` to the Pi and create a systemd service so it starts automatically:

```bash
sudo nano /etc/systemd/system/pi-stats.service
```

Paste:

```ini
[Unit]
Description=DTR Pi stats HTTP server
After=network.target

[Service]
User=deeptripradio
ExecStart=/usr/bin/python3 /home/deeptripradio/pi_stats.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pi-stats
```

Verify:

```bash
curl http://localhost:8001/stats
```

You should see a JSON blob with `cpu_pct`, `temp_c`, `mem`, `disk`, `wifi`, `svcs`, etc.

---

### Step 2 — Windows: install Grafana

1. Download and run the `.msi` installer from https://grafana.com/grafana/download?platform=windows
2. Grafana installs as a Windows service and starts automatically on port 3000
3. Open http://localhost:3000 — default login: `admin` / `admin`

---

### Step 3 — Windows: install the SQLite plugin

Open **PowerShell as Administrator**:

```powershell
& "C:\Program Files\GrafanaLabs\grafana\bin\grafana.exe" cli --homepath "C:\Program Files\GrafanaLabs\grafana" plugins install frser-sqlite-datasource
Restart-Service Grafana
```

If Grafana refuses to load the plugin (unsigned plugin warning), add this to `C:\Program Files\GrafanaLabs\grafana\conf\grafana.ini` under `[plugins]`:

```ini
allow_loading_unsigned_plugins = frser-sqlite-datasource
```

Then restart the service again.

---

### Step 4 — Grafana: add the SQLite datasource

1. Grafana → **Connections → Data Sources → Add → SQLite**
2. Set the path:
   ```
   G:\DTR\DTR-monitor\dtr_monitor.db
   ```
3. Name it **`SQLite (DTR)`**
4. Click **Save & Test**

> **Permissions:** Grafana runs as `Network Service`. If it can't read the file, either:
> - Right-click `dtr_monitor.db` → Properties → Security → add `NETWORK SERVICE` with Read permission, or
> - Change the Grafana service log-on to your Windows user account (Services → Grafana → Properties → Log On tab)

---

### Step 5 — collector.py: configure and run

Open `collector.py` and confirm the Pi IP is correct:

```python
PI_IP = '192.168.1.94'   # update if your Pi's IP differs
```

Run manually to verify:

```powershell
python "G:\DTR\DTR-monitor\collector.py"
```

Expected output:
```
10:32:15  INFO     Collector started  db=G:\DTR\DTR-monitor\dtr_monitor.db
10:32:15  INFO     listeners=3  latency=42ms  cpu=12.4%  temp=51.2°C
```

**Auto-start at Windows boot (Task Scheduler):**

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **When the computer starts**
3. Action: **Start a program**
   - Program: `pythonw`
   - Arguments: `"G:\DTR\DTR-monitor\collector.py"`
4. Check **Run whether user is logged on or not**

> Use `pythonw` instead of `python` to run without a console window.

---

### Step 6 — import the Grafana dashboard

If you make changes to the dashboard layout, regenerate the JSON first:

```powershell
python "G:\DTR\DTR-monitor\build_dashboard.py"
```

Import into Grafana:

1. **Dashboards → Import → Upload JSON file**
2. Select `grafana_dashboard.json`
3. Map **SQLite (DTR)** to the datasource added in Step 4
4. Click **Import** (or **Import (Overwrite)** to replace an existing version)

Dashboard URL: http://localhost:3000/d/dtr-monitor-v1

---

## Dashboard panels

| Panel | Query | Notes |
|---|---|---|
| Stream | `stream.online` | Green = Live, Red = Offline |
| Listeners | `stream.listeners` | Current live count (latest poll) |
| Peak Today | `MAX(stream.listeners)` since midnight | Resets at midnight |
| Latency | `stream.latency_ms` | Round-trip time to icecast from Windows |
| Pi Uptime | `pi_system.uptime_s` | Formatted as `Xd Yh` |
| icecast2 / cloudflared | `pi_system.icecast2/cloudflared` | `systemctl is-active` check |
| Now Playing | `stream.title` | Updates every 15 s |
| Artist | `stream.artist` | |
| Recently Played | `track_history` | Last 5 track changes, newest first |
| Listener History | `stream.listeners` | Hourly peak bar chart; use top-right time picker to change range |
| CPU / Memory / Temp / Disk / WiFi | `pi_system.*` | Gauge panels |

---

## Configuration

All tunables are at the top of `collector.py`:

```python
PI_IP      = '192.168.1.94'   # Pi's local IP
INTERVAL   = 15               # poll interval in seconds
PRUNE_DAYS = 7                # days of data to keep
DB_PATH    = Path(r'G:\DTR\DTR-monitor\dtr_monitor.db')
```

---

## Thresholds

| Metric | Yellow | Red |
|---|---|---|
| CPU | > 60 % | > 80 % |
| Memory | > 70 % | > 85 % |
| Temperature | > 55 °C | > 70 °C |
| Disk | > 70 % | > 85 % |
| WiFi | < −75 dBm | < −60 dBm (green above) |
| Latency | > 150 ms | > 300 ms |

---

## Data retention

`collector.py` prunes rows older than **7 days** once per day.  
At one row per 15 seconds the database stays well under **15 MB** indefinitely.

---

## Known limitations

- **Listener History panel** is a bar chart (hourly peaks) rather than a line chart. The `frser-sqlite-datasource` plugin does not expose a time field via JSON import, so Grafana's native timeseries panel type returns "Data is missing a time field" regardless of configuration.
- **Listener count via Cloudflare**: icecast reports the number of connections it sees directly. If Cloudflare caches the audio stream at its edge, multiple end listeners may appear as a single icecast connection. Add a Cloudflare Cache Rule for `stream.deeptripradio.net/live*` set to **Bypass** to get accurate per-listener counts.
