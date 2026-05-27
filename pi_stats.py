#!/usr/bin/env python3
"""Deep Trip Radio — Pi system stats server. Runs on port 8001."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, os, subprocess, time, threading
from datetime import date

# ── CPU sampling ──────────────────────────────────────────────────────────────
_cpu_prev = None
_cpu_lock = threading.Lock()

def _read_cpu_raw():
    with open('/proc/stat') as f:
        vals = list(map(int, f.readline().split()[1:]))
    total = sum(vals)
    idle  = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return total, idle

def cpu_percent():
    global _cpu_prev
    cur = _read_cpu_raw()
    with _cpu_lock:
        prev, _cpu_prev = _cpu_prev, cur
    if prev is None:
        return 0.0
    dt, di = cur[0] - prev[0], cur[1] - prev[1]
    return round(100.0 * (1 - di / dt), 1) if dt else 0.0

# ── System metrics ─────────────────────────────────────────────────────────────
def memory():
    m = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':', 1)
            m[k.strip()] = int(v.split()[0])
    total = m['MemTotal']
    avail = m['MemAvailable']
    used  = total - avail
    return {'total_mb': round(total/1024,1), 'used_mb': round(used/1024,1),
            'pct': round(100*used/total, 1)}

def temperature():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read()) / 1000, 1)
    except Exception:
        return None

def disk(path='/'):
    s = os.statvfs(path)
    tot  = s.f_blocks * s.f_frsize
    free = s.f_bfree  * s.f_frsize
    used = tot - free
    return {'total_gb': round(tot/1e9,1), 'used_gb': round(used/1e9,1),
            'pct': round(100*used/tot, 1)}

def wifi():
    try:
        with open('/proc/net/wireless') as f:
            for line in f:
                if 'wlan0' in line:
                    p = line.split()
                    return {'dbm': float(p[3].rstrip('.')),
                            'quality': int(p[2].rstrip('.')),
                            'retries': int(p[7])}
    except Exception:
        pass
    return None

def uptime_s():
    with open('/proc/uptime') as f:
        return int(float(f.read().split()[0]))

def svc_active(name):
    try:
        r = subprocess.run(['systemctl', 'is-active', name],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip() == 'active'
    except Exception:
        return False

# ── Icecast session log parser ─────────────────────────────────────────────────
LOG = '/var/log/icecast2/access.log'

def sessions():
    today = date.today().strftime('%d/%b/%Y')
    durs = []
    try:
        with open(LOG, errors='replace') as f:
            for line in f:
                if today not in line:
                    continue
                if '"/live ' not in line and '"/live"' not in line:
                    continue
                if '" 200 ' not in line:
                    continue
                try:
                    d = int(line.strip().rsplit(None, 1)[-1])
                    if d >= 10:
                        durs.append(d)
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
    return {'count': len(durs),
            'avg_s': round(sum(durs)/len(durs)) if durs else 0,
            'total_s': sum(durs)}

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stats':
            body = json.dumps({
                'cpu_pct':  cpu_percent(),
                'mem':      memory(),
                'temp_c':   temperature(),
                'disk':     disk(),
                'wifi':     wifi(),
                'uptime_s': uptime_s(),
                'svcs': {
                    'icecast2':    svc_active('icecast2'),
                    'cloudflared': svc_active('cloudflared'),
                },
                'ts': int(time.time()),
            }).encode()
        elif self.path == '/sessions':
            body = json.dumps(sessions()).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

if __name__ == '__main__':
    _read_cpu_raw()
    time.sleep(0.5)
    _read_cpu_raw()
    srv = HTTPServer(('0.0.0.0', 8001), Handler)
    print('DTR stats server running on :8001')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
