#!/usr/bin/env python3
"""
Deep Trip Radio — Grafana collector
Polls icecast + Pi stats every 15 s, writes to SQLite.

Needs : Python 3.7+  —  stdlib only, no pip installs.
Usage : python collector.py
DB    : dtr_monitor.db  (created automatically alongside this script)
"""
import json
import logging
import sqlite3
import time
from pathlib import Path
from urllib.request import urlopen, Request

# ── Config ───────────────────────────────────────────────────────────────────
from config import PI_IP, DB_PATH as _DB_PATH
ICECAST_URL = f'http://{PI_IP}:8000/status-json.xsl'
STATS_URL   = f'http://{PI_IP}:8001/stats'
INTERVAL    = 15       # seconds between polls
PRUNE_DAYS  = 7        # delete rows older than this
DB_PATH     = Path(_DB_PATH)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('dtr')

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = '''
CREATE TABLE IF NOT EXISTS stream (
    ts          INTEGER PRIMARY KEY,   -- unix epoch seconds
    online      INTEGER,               -- 1 = source up, 0 = down
    listeners   INTEGER,
    title       TEXT,
    artist      TEXT,
    latency_ms  INTEGER                -- ms to reach icecast endpoint
);
CREATE TABLE IF NOT EXISTS pi_system (
    ts            INTEGER PRIMARY KEY,
    cpu_pct       REAL,
    mem_pct       REAL,
    mem_used_mb   REAL,
    mem_total_mb  REAL,
    temp_c        REAL,
    disk_pct      REAL,
    disk_used_gb  REAL,
    disk_total_gb REAL,
    wifi_dbm      REAL,
    wifi_quality  INTEGER,
    uptime_s      INTEGER,
    icecast2      INTEGER,             -- 1 = active, 0 = down
    cloudflared   INTEGER
);
CREATE TABLE IF NOT EXISTS track_history (
    ts      INTEGER PRIMARY KEY,       -- when the track started playing
    title   TEXT,
    artist  TEXT
);
'''

def open_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def prune(conn):
    cutoff = int(time.time()) - PRUNE_DAYS * 86400
    for table in ('stream', 'pi_system', 'track_history'):
        conn.execute(f'DELETE FROM {table} WHERE ts < ?', (cutoff,))
    conn.commit()
    log.info(f'Pruned rows older than {PRUNE_DAYS} days')

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch(url, timeout=5):
    req = Request(url, headers={'User-Agent': 'DTR-Collector/1.0'})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def poll_stream():
    t0 = time.time()
    try:
        data    = fetch(ICECAST_URL)
        latency = round((time.time() - t0) * 1000)
        src     = data.get('icestats', {}).get('source')
        if not src:
            return {'online': 0, 'listeners': 0, 'title': '', 'artist': '', 'latency_ms': latency}
        title  = src.get('title', '')
        artist = src.get('artist', '')
        if not artist and ' - ' in title:
            artist, title = title.split(' - ', 1)
        return {
            'online':     1,
            'listeners':  int(src.get('listeners', 0)),
            'title':      title.strip(),
            'artist':     artist.strip(),
            'latency_ms': latency,
        }
    except Exception as e:
        log.warning(f'icecast poll failed: {e}')
        return {'online': 0, 'listeners': 0, 'title': '', 'artist': '', 'latency_ms': None}

def poll_pi():
    try:
        return fetch(STATS_URL)
    except Exception as e:
        log.warning(f'pi stats poll failed: {e}')
        return None

# ── Write ─────────────────────────────────────────────────────────────────────
def write_stream(conn, ts, s):
    conn.execute(
        'INSERT OR REPLACE INTO stream VALUES (?,?,?,?,?,?)',
        (ts, s['online'], s['listeners'], s['title'], s['artist'], s['latency_ms']),
    )

def write_pi(conn, ts, pi):
    if pi is None:
        return
    mem  = pi.get('mem')  or {}
    disk = pi.get('disk') or {}
    wifi = pi.get('wifi') or {}
    svcs = pi.get('svcs') or {}
    conn.execute(
        'INSERT OR REPLACE INTO pi_system VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            ts,
            pi.get('cpu_pct'),
            mem.get('pct'),    mem.get('used_mb'),  mem.get('total_mb'),
            pi.get('temp_c'),
            disk.get('pct'),   disk.get('used_gb'), disk.get('total_gb'),
            wifi.get('dbm'),   wifi.get('quality'),
            pi.get('uptime_s'),
            int(bool(svcs.get('icecast2'))),
            int(bool(svcs.get('cloudflared'))),
        ),
    )

def write_track(conn, ts, title, artist):
    conn.execute('INSERT OR REPLACE INTO track_history VALUES (?,?,?)', (ts, title, artist))
    log.info(f'Track → {artist} – {title}')

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    conn       = open_db()
    last_title = None
    last_prune = time.time()

    log.info(f'Collector started  db={DB_PATH}')
    log.info(f'Pi={PI_IP}  interval={INTERVAL}s  keep={PRUNE_DAYS}d')

    while True:
        now    = int(time.time())
        stream = poll_stream()
        pi     = poll_pi()

        write_stream(conn, now, stream)
        write_pi(conn, now, pi)

        # record track changes
        title = stream['title']
        if title and title != last_title:
            write_track(conn, now, title, stream['artist'])
            last_title = title

        conn.commit()

        if now - last_prune > 86400:
            prune(conn)
            last_prune = now

        pi_str = (f"  cpu={pi.get('cpu_pct','?')}%  temp={pi.get('temp_c','?')}°C"
                  if pi else '')
        log.info(f"listeners={stream['listeners']}  latency={stream['latency_ms']}ms{pi_str}")

        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
