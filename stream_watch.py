#!/usr/bin/env python3
"""
Stream watchdog — polls Pi stats, icecast, and Cloudflare tunnel every N seconds.
Highlights state changes and alerts. Logs everything to a timestamped file.
"""
import requests
import time
import sys
from datetime import datetime

PI_IP       = '192.168.1.94'
STATS_URL   = f'http://{PI_IP}:8001/stats'
ICE_LOCAL   = f'http://{PI_IP}:8000/status-json.xsl'
STREAM_CF   = 'https://stream.deeptripradio.net/live'
META_CF     = 'https://stream.deeptripradio.net/status-json.xsl'
INTERVAL    = 8   # seconds between polls

def ts():
    return datetime.now().strftime('%H:%M:%S')

def poll():
    r = {}

    # --- Pi system stats ---
    try:
        resp = requests.get(STATS_URL, timeout=5)
        d    = resp.json()
        r['pi'] = dict(
            ok      = True,
            cpu     = d.get('cpu_pct', '?'),
            mem     = (d.get('mem') or {}).get('percent', '?'),
            temp    = d.get('temp_c', '?'),
            rssi    = (d.get('wifi') or {}).get('dbm', '?'),
            uptime  = d.get('uptime_s', '?'),
            svcs    = d.get('svcs', {}),
        )
    except Exception as e:
        r['pi'] = dict(ok=False, error=str(e))

    # --- icecast local ---
    try:
        resp   = requests.get(ICE_LOCAL, timeout=5)
        d      = resp.json()
        src    = d.get('icestats', {}).get('source')
        if src is None:
            mounts = []
        elif isinstance(src, dict):
            mounts = [src]
        else:
            mounts = src
        listeners = sum(int(m.get('listeners', 0)) for m in mounts)
        title = mounts[0].get('title', '') if mounts else ''
        r['ice'] = dict(ok=True, mounts=len(mounts), listeners=listeners,
                        source_up=len(mounts) > 0, title=title)
    except Exception as e:
        r['ice'] = dict(ok=False, error=str(e))

    # --- Cloudflare stream — GET with streaming so we don't download audio ---
    try:
        resp = requests.get(STREAM_CF, timeout=10, allow_redirects=True, stream=True)
        resp.close()
        r['cf_stream'] = dict(ok=resp.status_code == 200, code=resp.status_code,
                              cf_ray=resp.headers.get('cf-ray', '?'),
                              content_type=resp.headers.get('content-type', '?'))
    except Exception as e:
        r['cf_stream'] = dict(ok=False, error=str(e))

    # --- Cloudflare metadata ---
    try:
        resp = requests.get(META_CF, timeout=10)
        r['cf_meta'] = dict(ok=resp.status_code == 200, code=resp.status_code,
                            cors=resp.headers.get('access-control-allow-origin', 'MISSING'))
    except Exception as e:
        r['cf_meta'] = dict(ok=False, error=str(e))

    return r

def summarise(r):
    lines = []

    pi = r.get('pi', {})
    if pi.get('ok'):
        svcs = pi.get('svcs', {})
        svc_str = '  '.join(f"{k}={'OK' if v else '!DOWN!'}" for k, v in svcs.items())
        def fmt_f(v): return f"{v:.1f}" if isinstance(v, (int, float)) else str(v)
        lines.append(f"  PI       cpu={fmt_f(pi['cpu'])}%  mem={fmt_f(pi['mem'])}%  "
                     f"temp={fmt_f(pi['temp'])}°C  rssi={pi['rssi']}dBm  "
                     f"uptime={pi['uptime']}s")
        lines.append(f"  SVCS     {svc_str}")
    else:
        lines.append(f"  PI       UNREACHABLE — {pi.get('error')}")

    ice = r.get('ice', {})
    if ice.get('ok'):
        src = 'UP' if ice['source_up'] else '!DOWN!'
        title = ice.get('title', '')[:50]
        lines.append(f"  ICECAST  source={src}  listeners={ice['listeners']}  now={title!r}")
    else:
        lines.append(f"  ICECAST  UNREACHABLE — {ice.get('error')}")

    cf = r.get('cf_stream', {})
    if cf.get('ok'):
        lines.append(f"  CF STREAM  HTTP {cf['code']} OK  type={cf.get('content_type','?')}")
    else:
        lines.append(f"  CF STREAM  FAIL — {cf.get('error', 'HTTP '+str(cf.get('code')))}")

    cm = r.get('cf_meta', {})
    if cm.get('ok'):
        lines.append(f"  CF META    HTTP {cm['code']} OK  cors={cm['cors']}")
    else:
        lines.append(f"  CF META    FAIL — {cm.get('error', 'HTTP '+str(cm.get('code')))}")

    return '\n'.join(lines)

def alerts(r):
    a = []
    if not r.get('pi', {}).get('ok'):
        a.append("PI_UNREACHABLE")
    else:
        pi = r['pi']
        temp = pi.get('temp', 0)
        rssi = pi.get('rssi', 0)
        if isinstance(temp, (int, float)) and temp > 75:
            a.append(f"HIGH_TEMP({temp:.0f}C)")
        if isinstance(rssi, (int, float)) and rssi < -80:
            a.append(f"WEAK_WIFI({rssi}dBm)")
        for svc, up in pi.get('svcs', {}).items():
            if not up:
                a.append(f"SVC_DOWN({svc})")

    ice = r.get('ice', {})
    if not ice.get('ok'):
        a.append("ICECAST_UNREACHABLE")
    elif not ice.get('source_up'):
        a.append("EZSTREAM_DISCONNECTED")

    if not r.get('cf_stream', {}).get('ok'):
        a.append("CF_STREAM_DOWN")
    if not r.get('cf_meta', {}).get('ok'):
        a.append("CF_META_DOWN")

    return a

def state_key(r):
    return (
        r.get('pi', {}).get('ok'),
        r.get('ice', {}).get('ok'),
        r.get('ice', {}).get('source_up'),
        r.get('cf_stream', {}).get('ok'),
        r.get('cf_meta', {}).get('ok'),
        tuple(sorted(
            (k, v) for k, v in r.get('pi', {}).get('svcs', {}).items()
        )),
    )

def main():
    log_name = f"stream_watch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    print(f"Stream watchdog — polling every {INTERVAL}s | log: {log_name}")
    print("Ctrl+C to stop.\n")

    prev_state = None
    tick = 0

    with open(log_name, 'w', buffering=1) as log:
        log.write(f"# Stream watchdog started {datetime.now().isoformat()}\n\n")

        while True:
            t    = ts()
            tick += 1
            r    = poll()
            al   = alerts(r)
            cur  = state_key(r)
            changed = (cur != prev_state)

            alert_str = " *** " + " | ".join(al) if al else ""
            header    = f"[{t}] tick={tick}{alert_str}"

            body = summarise(r)

            # always print header; body only on change or every 5 ticks
            if changed or tick % 5 == 1 or al:
                print(header)
                print(body)
                print()
            else:
                print(header)

            log.write(header + '\n')
            log.write(body + '\n\n')

            if changed and prev_state is not None:
                change_msg = f"  ^^^ STATE CHANGED at {t}"
                print(change_msg)
                log.write(change_msg + '\n\n')

            prev_state = cur
            sys.stdout.flush()
            time.sleep(INTERVAL)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\nWatchdog stopped at {ts()}.")
