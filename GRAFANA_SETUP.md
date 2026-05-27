# Deep Trip Radio — Grafana Dashboard Setup

## What you'll have when done

```
Pi
  icecast2      :8000   (already running)
  pi_stats.py   :8001   (new — lightweight systemd service)

Windows
  collector.py          (polls Pi every 15s → dtr_monitor.db)
  Grafana               (reads db → dashboard at localhost:3000)
```

---

## Step 1 — Install Grafana on Windows

1. Download the Windows installer:
   https://grafana.com/grafana/download?platform=windows

2. Run the `.msi` — Grafana installs as a Windows service and starts automatically.

3. Open http://localhost:3000 — default login is `admin` / `admin`.
   Change the password when prompted.

---

## Step 2 — Install the SQLite plugin

Open **PowerShell as Administrator** and run:

```powershell
& "C:\Program Files\GrafanaLabs\grafana\bin\grafana-cli.exe" plugins install frser-sqlite-datasource
```

Then restart the Grafana service:

```powershell
Restart-Service Grafana
```

> **If you see an unsigned plugin warning**, open
> `C:\Program Files\GrafanaLabs\grafana\conf\grafana.ini`
> and add under the `[plugins]` section:
> ```
> allow_loading_unsigned_plugins = frser-sqlite-datasource
> ```
> Then restart the service again.

---

## Step 3 — Start pi_stats.py on the Pi

SSH into the Pi and create a systemd service:

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

Copy the script and enable the service:

```bash
cp /path/to/pi_stats.py /home/deeptripradio/pi_stats.py
sudo systemctl daemon-reload
sudo systemctl enable --now pi-stats
```

Verify it's running:

```bash
curl http://localhost:8001/stats
```

You should see a JSON blob with cpu_pct, temp_c, etc.

---

## Step 4 — Add the SQLite datasource in Grafana

1. In Grafana: **Connections → Data Sources → Add → SQLite**
2. Set the path to the database file:
   ```
   G:\DTR\DTR-monitor\dtr_monitor.db
   ```
3. Name it **`SQLite (DTR)`**
4. Click **Save & Test**

> **Permission note:** The Grafana Windows service runs as `Network Service`.
> If it can't read the file, right-click `dtr_monitor.db` → Properties →
> Security → Add `NETWORK SERVICE` with Read permission.
> Alternatively, change the Grafana service log-on to your Windows user account
> (Services → Grafana → Properties → Log On tab).

---

## Step 5 — Run collector.py

Open a terminal in the `monitor/` folder and run:

```powershell
python collector.py
```

You should see log lines like:
```
10:32:15  INFO     Collector started  db=...\dtr_monitor.db
10:32:15  INFO     listeners=3  latency=42ms  cpu=12.4%  temp=51.2°C
```

**To run automatically at Windows startup** (no terminal needed):

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **When the computer starts**
3. Action: **Start a program**
   - Program: `python`
   - Arguments: `"G:\DTR\DTR-monitor\collector.py"`
4. Check **Run whether user is logged on or not**

---

## Step 6 — Build and import the dashboard

Generate the JSON (run once, or again after any changes to `build_dashboard.py`):

```powershell
python build_dashboard.py
# → grafana_dashboard.json written
```

Import into Grafana:

1. **Dashboards → Import → Upload JSON file**
2. Select `grafana_dashboard.json`
3. When prompted, map **SQLite (DTR)** to the datasource you created in Step 4
4. Click **Import**

---

## What each panel shows

| Panel | Source | Notes |
|---|---|---|
| Stream | `stream.online` | Green = Live, Red = Offline |
| Listeners | `stream.listeners` | Current live count |
| Peak Today | `MAX(stream.listeners)` since midnight | Resets at midnight |
| Latency | `stream.latency_ms` | Time to reach icecast from Windows |
| Pi Uptime | `pi_system.uptime_s` | Pi system uptime |
| icecast2 / cloudflared | `pi_system.icecast2/cloudflared` | systemctl is-active check |
| Now Playing | `stream.title` | Updates every 15s |
| Artist | `stream.artist` | |
| Recently Played | `track_history` | Last 5 tracks, newest first |
| Listener History | `stream.listeners` | 24h line chart |
| CPU / Memory / Temp / Disk / WiFi | `pi_system.*` | Gauge panels with color thresholds |

---

## Thresholds at a glance

| Metric | Yellow | Red |
|---|---|---|
| CPU | > 60% | > 80% |
| Memory | > 70% | > 85% |
| Temperature | > 55°C | > 70°C |
| Disk | > 70% | > 85% |
| WiFi | < −75 dBm | < −75 dBm (red) / > −60 dBm (green) |
| Latency | > 150ms | > 300ms |

---

## Data retention

`collector.py` prunes rows older than **7 days** once per day.
At one row per 15 seconds, the database stays under ~15 MB indefinitely.
