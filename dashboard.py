#!/usr/bin/env python3
"""
Deep Trip Radio Monitor
Usage : python dashboard.py
Open  : http://localhost:5000
Needs : Python 3.7+ stdlib only. pi_stats.py must be running on the Pi.
"""
import json, threading, time
from collections import deque
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Config ─────────────────────────────────────────────────────────────────────
from config import PI_IP
ICECAST_URL  = f'http://{PI_IP}:8000/status-json.xsl'
STATS_URL    = f'http://{PI_IP}:8001/stats'
SESSIONS_URL = f'http://{PI_IP}:8001/sessions'
PORT         = 5000
POLL_S       = 15   # main poll interval
SESSION_EVERY = 4   # poll sessions every N cycles (~60s)

# ── Shared state ───────────────────────────────────────────────────────────────
_lock    = threading.Lock()
_state   = {}
_history = deque(maxlen=5760)   # 24h at 15s intervals
_peak    = {'count': 0, 'date': None}

def _fetch(url, timeout=5):
    t0 = time.time()
    req = Request(url, headers={'User-Agent': 'DTR-Monitor/1.0'})
    with urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data, round((time.time() - t0) * 1000)

def _poll():
    cycle = 0
    while True:
        update = {}
        # Icecast
        try:
            data, ms = _fetch(ICECAST_URL)
            update['latency_ms'] = ms
            src = data.get('icestats', {}).get('source')
            if src:
                n      = int(src.get('listeners', 0))
                title  = src.get('title',  '')
                artist = src.get('artist', '')
                if not artist and ' - ' in title:
                    artist, title = title.split(' - ', 1)
                update['stream'] = {
                    'online': True, 'listeners': n,
                    'title': title.strip(), 'artist': artist.strip(),
                    'stream_start': src.get('stream_start', ''),
                }
            else:
                n = 0
                update['stream'] = {'online': False, 'listeners': 0}

            today = date.today()
            if _peak['date'] != today:
                _peak.update({'count': 0, 'date': today})
            if n > _peak['count']:
                _peak['count'] = n
            _history.append((int(time.time()), n))
        except Exception as e:
            update['stream'] = {'online': False, 'listeners': 0}

        # Pi stats
        try:
            pi, _ = _fetch(STATS_URL)
            update['pi'] = pi
        except Exception:
            update['pi'] = None

        # Sessions (every ~60s to keep log I/O light)
        if cycle % SESSION_EVERY == 0:
            try:
                sess, _ = _fetch(SESSIONS_URL)
                update['sessions'] = sess
            except Exception:
                pass

        update['ts'] = int(time.time())
        with _lock:
            _state.update(update)

        cycle += 1
        time.sleep(POLL_S)

def _api_payload():
    with _lock:
        s = dict(_state)
    cutoff = time.time() - 86400
    hist = [(ts, c) for ts, c in _history if ts >= cutoff]
    if len(hist) > 200:
        step = max(1, len(hist) // 200)
        hist = hist[::step]
    return {
        'stream':     s.get('stream'),
        'pi':         s.get('pi'),
        'sessions':   s.get('sessions'),
        'latency_ms': s.get('latency_ms'),
        'peak_today': _peak['count'],
        'history':    [{'ts': ts, 'n': c} for ts, c in hist],
        'ts':         s.get('ts'),
    }

# ── HTML dashboard ─────────────────────────────────────────────────────────────
HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deep Trip Radio — Monitor</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Outfit:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#04040e;--card:rgba(8,7,18,0.92);--border:rgba(120,53,237,0.11);
  --purple:#8b5cf6;--purple2:#a78bfa;--teal:#22d3ee;
  --green:#34d399;--yellow:#fbbf24;--red:#f87171;
  --text:#e2e8f0;--muted:#475569;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Outfit',system-ui,sans-serif;min-height:100vh;padding:16px;overflow-x:hidden}

.orb{position:fixed;border-radius:50%;pointer-events:none;z-index:0;animation:drift 26s ease-in-out infinite}
.orb-1{width:640px;height:640px;background:radial-gradient(circle,rgba(120,53,237,0.09),transparent 70%);top:-220px;left:-220px;filter:blur(120px);animation-delay:0s}
.orb-2{width:520px;height:520px;background:radial-gradient(circle,rgba(34,211,238,0.07),transparent 70%);bottom:-120px;right:-160px;filter:blur(110px);animation-delay:-9s}
.orb-3{width:360px;height:360px;background:radial-gradient(circle,rgba(139,92,246,0.055),transparent 70%);top:42%;left:42%;filter:blur(100px);animation-delay:-18s}
@keyframes drift{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(32px,-22px) scale(1.04)}66%{transform:translate(-22px,32px) scale(0.97)}}

.wrap{position:relative;z-index:1;max-width:1400px;margin:0 auto}

.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px;
  backdrop-filter:blur(24px);position:relative;overflow:hidden;
  box-shadow:0 4px 40px rgba(0,0,0,0.45),inset 0 0 0 1px rgba(255,255,255,0.02);
  transition:border-color .35s}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent 5%,rgba(255,255,255,0.07) 50%,transparent 95%);pointer-events:none}
.card:hover{border-color:rgba(120,53,237,0.24)}

.header{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;
  padding:14px 22px;margin-bottom:14px;border-radius:16px;
  background:linear-gradient(135deg,rgba(12,10,28,0.96),rgba(8,7,18,0.92));
  border:1px solid var(--border);backdrop-filter:blur(28px);
  box-shadow:0 0 60px rgba(120,53,237,0.07),0 4px 40px rgba(0,0,0,0.45)}
.header::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent 5%,rgba(139,92,246,0.35) 40%,rgba(34,211,238,0.25) 65%,transparent 95%)}
.hl{display:flex;align-items:center;gap:14px}
.logo-mark{width:34px;height:34px;flex-shrink:0;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,rgba(139,92,246,0.18),rgba(34,211,238,0.08));
  border:1px solid rgba(139,92,246,0.22);border-radius:10px}
.htitle{font-size:15px;font-weight:700;letter-spacing:.05em;
  background:linear-gradient(130deg,#f1f5f9 35%,#a78bfa 72%,#22d3ee);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hsub{font-size:9px;color:var(--muted);margin-top:3px;letter-spacing:.16em;text-transform:uppercase}
.hr-right{display:flex;align-items:center;gap:18px}
.pip{display:flex;align-items:center;gap:9px}
.pip-dot{position:relative;width:10px;height:10px;flex-shrink:0}
.pip-dot span{display:block;width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 14px rgba(52,211,153,0.8)}
.pip-dot span::after{content:'';position:absolute;inset:-7px;border-radius:50%;background:rgba(52,211,153,0.13);animation:ripple 2.6s ease-out infinite}
.pip.off .pip-dot span{background:#374151;box-shadow:none}
.pip.off .pip-dot span::after{display:none}
@keyframes ripple{0%{transform:scale(.55);opacity:1}100%{transform:scale(2.6);opacity:0}}
.pip-text{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--green)}
.pip.off .pip-text{color:var(--muted)}
.htime{font-family:'Space Mono',monospace;font-size:10px;color:var(--muted)}

.grid{display:grid;gap:14px}
.row-top{display:grid;grid-template-columns:3fr 2fr;gap:14px}
.row-health{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}

.lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;
  color:var(--muted);margin-bottom:14px;display:flex;align-items:center;gap:7px}
.lbl-dot{width:3px;height:3px;border-radius:50%;background:var(--purple);flex-shrink:0}

/* Now Playing */
.np-card{display:flex;flex-direction:column}
.track-title{font-size:26px;font-weight:800;line-height:1.2;min-height:32px;margin-bottom:8px;letter-spacing:-.02em;
  background:linear-gradient(135deg,#f1f5f9 45%,#a78bfa);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.track-artist{font-size:15px;color:var(--purple2);font-weight:400;min-height:20px;flex:1}
.np-footer{margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.04);
  display:flex;align-items:center;gap:12px}
.live-badge{font-size:9px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  color:var(--green);background:rgba(52,211,153,0.07);
  border:1px solid rgba(52,211,153,0.2);border-radius:20px;padding:4px 12px}
.stream-since{font-size:11px;color:var(--muted)}

/* Listeners card */
.listeners-card{display:flex;flex-direction:column;justify-content:space-between}
.bignum{font-family:'Space Mono',monospace;font-size:80px;font-weight:700;line-height:1;
  color:var(--teal);text-shadow:0 0 70px rgba(34,211,238,0.45),0 0 20px rgba(34,211,238,0.2);
  margin-bottom:4px}
.bignum-sub{font-size:11px;color:var(--muted);letter-spacing:.06em;margin-bottom:20px}
.meta-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:auto}
.meta-item{border-top:1px solid rgba(255,255,255,0.05);padding-top:10px}
.meta-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);margin-bottom:4px}
.meta-val{font-family:'Space Mono',monospace;font-size:15px;font-weight:700}

/* Chart */
.chart-wrap{width:100%;height:160px;position:relative;margin-top:4px}
svg.chart{width:100%;height:100%;display:block}
.no-data{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  color:var(--muted);font-size:12px;letter-spacing:.08em;opacity:.45}

/* Gauges */
.gauge-card{display:flex;flex-direction:column;align-items:center;text-align:center;padding:18px 12px}
.g-wrap{position:relative;width:86px;height:86px;margin:0 auto 12px}
.g-wrap svg{width:100%;height:100%}
.g-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.g-val{font-family:'Space Mono',monospace;font-size:14px;font-weight:700;line-height:1}
.g-unit{font-size:8px;color:var(--muted);margin-top:2px}
.g-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;color:var(--muted)}
.g-sub{font-size:9px;color:#2d3a4d;margin-top:5px;font-family:'Space Mono',monospace}

/* Services bar */
.svc-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.svc-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--muted);margin-right:4px}
.badge{display:flex;align-items:center;gap:7px;
  background:rgba(120,53,237,0.04);border:1px solid var(--border);border-radius:8px;
  padding:6px 14px;font-size:12px;font-weight:500}
.bdot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.bok{background:var(--green);box-shadow:0 0 7px rgba(52,211,153,0.65)}
.bbad{background:var(--red);box-shadow:0 0 5px rgba(248,113,113,0.4)}

@media(max-width:960px){.row-top{grid-template-columns:1fr}.row-health{grid-template-columns:repeat(3,1fr)}}
@media(max-width:520px){.row-health{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
<div class="orb orb-3"></div>
<div class="wrap">

<header class="header">
  <div class="hl">
    <div class="logo-mark">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
        <circle cx="12" cy="12" r="2.5" fill="#a78bfa"/>
        <path d="M8.5 12a3.5 3.5 0 017 0" stroke="#22d3ee" stroke-width="1.6" fill="none" stroke-linecap="round"/>
        <path d="M5.5 12a6.5 6.5 0 0113 0" stroke="#8b5cf6" stroke-width="1.4" fill="none" stroke-linecap="round" opacity=".6"/>
        <path d="M2.5 12a9.5 9.5 0 0119 0" stroke="#6d28d9" stroke-width="1.2" fill="none" stroke-linecap="round" opacity=".3"/>
      </svg>
    </div>
    <div>
      <div class="htitle">Deep Trip Radio Monitor</div>
      <div class="hsub">System Dashboard</div>
    </div>
  </div>
  <div class="hr-right">
    <div class="pip off" id="pip">
      <div class="pip-dot"><span></span></div>
      <div class="pip-text" id="live-label">Connecting</div>
    </div>
    <div class="htime" id="updated">—</div>
  </div>
</header>

<div class="grid">

  <div class="row-top">
    <div class="card np-card">
      <div class="lbl"><span class="lbl-dot"></span>Now Playing</div>
      <div class="track-title" id="track-title">—</div>
      <div class="track-artist" id="track-artist">—</div>
      <div class="np-footer">
        <div class="live-badge" id="np-badge" style="display:none">Live</div>
        <div class="stream-since" id="stream-since"></div>
      </div>
    </div>

    <div class="card listeners-card">
      <div class="lbl"><span class="lbl-dot"></span>Listeners</div>
      <div class="bignum" id="listeners">—</div>
      <div class="bignum-sub">live now</div>
      <div class="meta-row">
        <div class="meta-item">
          <div class="meta-label">Peak today</div>
          <div class="meta-val" id="peak">—</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">Latency</div>
          <div class="meta-val" id="lat-val">—</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">Pi Uptime</div>
          <div class="meta-val" id="uptime-val">—</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">Services</div>
          <div class="svc-bar" style="margin-top:4px">
            <div class="badge"><div class="bdot bbad" id="svc-icecast2"></div>icecast2</div>
            <div class="badge"><div class="bdot bbad" id="svc-cloudflared"></div>cloudflared</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="lbl"><span class="lbl-dot"></span>Listener History — Last 24h</div>
    <div class="chart-wrap">
      <svg class="chart" viewBox="0 0 800 140" preserveAspectRatio="none">
        <defs>
          <linearGradient id="areagrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.18"/>
            <stop offset="90%" stop-color="#22d3ee" stop-opacity="0"/>
          </linearGradient>
          <linearGradient id="linegrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#8b5cf6"/>
            <stop offset="100%" stop-color="#22d3ee"/>
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <line x1="0" y1="46" x2="800" y2="46" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>
        <line x1="0" y1="84" x2="800" y2="84" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>
        <line x1="0" y1="122" x2="800" y2="122" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>
        <path id="chart-area" fill="url(#areagrad)" stroke="none" d=""/>
        <path id="chart-line" fill="none" stroke="url(#linegrad)" stroke-width="2.5" filter="url(#glow)" d=""/>
        <text id="chart-ymax" x="6" y="16" fill="#334155" font-size="9" font-family="monospace">0</text>
      </svg>
      <div class="no-data" id="no-data">Collecting data…</div>
    </div>
  </div>

  <div class="row-health">
    <div class="card gauge-card">
      <div class="g-wrap">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#0c0b1e" stroke-width="9"/>
          <circle id="g-cpu" cx="50" cy="50" r="38" fill="none" stroke="#22d3ee" stroke-width="9"
            stroke-dasharray="238.76" stroke-dashoffset="238.76" stroke-linecap="round"
            transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="g-center"><div class="g-val" style="color:#22d3ee" id="cpu-val">—</div></div>
      </div>
      <div class="g-label">CPU</div>
    </div>

    <div class="card gauge-card">
      <div class="g-wrap">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#0c0b1e" stroke-width="9"/>
          <circle id="g-mem" cx="50" cy="50" r="38" fill="none" stroke="#a78bfa" stroke-width="9"
            stroke-dasharray="238.76" stroke-dashoffset="238.76" stroke-linecap="round"
            transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="g-center"><div class="g-val" style="color:#a78bfa" id="mem-val">—</div></div>
      </div>
      <div class="g-label">Memory</div>
      <div class="g-sub" id="mem-sub"></div>
    </div>

    <div class="card gauge-card">
      <div class="g-wrap">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#0c0b1e" stroke-width="9"/>
          <circle id="g-temp" cx="50" cy="50" r="38" fill="none" stroke="#34d399" stroke-width="9"
            stroke-dasharray="238.76" stroke-dashoffset="238.76" stroke-linecap="round"
            transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="g-center"><div class="g-val" id="temp-val">—</div></div>
      </div>
      <div class="g-label">Temp</div>
    </div>

    <div class="card gauge-card">
      <div class="g-wrap">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#0c0b1e" stroke-width="9"/>
          <circle id="g-disk" cx="50" cy="50" r="38" fill="none" stroke="#fbbf24" stroke-width="9"
            stroke-dasharray="238.76" stroke-dashoffset="238.76" stroke-linecap="round"
            transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="g-center"><div class="g-val" style="color:#fbbf24" id="disk-val">—</div></div>
      </div>
      <div class="g-label">Disk</div>
      <div class="g-sub" id="disk-sub"></div>
    </div>

    <div class="card gauge-card">
      <div class="g-wrap">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#0c0b1e" stroke-width="9"/>
          <circle id="g-wifi" cx="50" cy="50" r="38" fill="none" stroke="#34d399" stroke-width="9"
            stroke-dasharray="238.76" stroke-dashoffset="238.76" stroke-linecap="round"
            transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="g-center"><div class="g-val" id="wifi-val">—</div><div class="g-unit">dBm</div></div>
      </div>
      <div class="g-label">WiFi</div>
      <div class="g-sub" id="wifi-sub"></div>
    </div>
  </div>

</div>
</div>
<script>
const REFRESH = 15000;
const CIRC = 238.76;

function fmt(s) {
  if (!s && s !== 0) return "—";
  s = Math.round(s);
  const h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
  if (h>0) return h+"h "+m+"m";
  if (m>0) return m+"m "+sec+"s";
  return sec+"s";
}
function fmtUp(s) {
  if (!s) return "—";
  const d=Math.floor(s/86400), h=Math.floor((s%86400)/3600), m=Math.floor((s%3600)/60);
  if (d>0) return d+"d "+h+"h "+m+"m";
  if (h>0) return h+"h "+m+"m";
  return m+"m";
}
function txt(id, v) { const e=document.getElementById(id); if(e) e.textContent=v; }

function setGauge(id, pct, color) {
  const el=document.getElementById(id);
  if (!el) return;
  el.style.strokeDashoffset=(CIRC*(1-Math.min(Math.max(pct,0),100)/100)).toFixed(2);
  if (color) el.style.stroke=color;
}
function dynColor(pct, lo, hi) {
  if (pct < lo) return null;
  if (pct < hi) return "#fbbf24";
  return "#f87171";
}
function tempColor(t) { return t<55?"#34d399":t<70?"#fbbf24":"#f87171"; }
function wifiColor(pct) { return pct>=55?"#34d399":pct>=35?"#fbbf24":"#f87171"; }
function latColor(ms) { return ms<100?"#34d399":ms<300?"#fbbf24":"#f87171"; }

function streamDur(s) {
  if (!s) return "";
  try {
    const sec=Math.floor((Date.now()-new Date(s))/1000);
    return "Stream up "+fmt(sec);
  } catch(e) { return ""; }
}

function buildChart(history) {
  const nd=document.getElementById("no-data");
  if (!history||history.length<2) { nd.style.display="flex"; return; }
  nd.style.display="none";
  const W=800, H=140, PT=22, PB=6, h=H-PT-PB;
  const max=Math.max(...history.map(p=>p.n),1);
  const pts=history.map((p,i)=>[(i/(history.length-1))*W, PT+h-(p.n/max)*h]);
  function smooth(pts) {
    let d="M"+pts[0][0].toFixed(1)+","+pts[0][1].toFixed(1);
    for (let i=1;i<pts.length;i++) {
      const [x0,y0]=pts[i-1],[x1,y1]=pts[i], cx=((x0+x1)/2).toFixed(1);
      d+=" C"+cx+","+y0.toFixed(1)+" "+cx+","+y1.toFixed(1)+" "+x1.toFixed(1)+","+y1.toFixed(1);
    }
    return d;
  }
  const line=smooth(pts);
  document.getElementById("chart-line").setAttribute("d", line);
  document.getElementById("chart-area").setAttribute("d", line+" L800,"+(PT+h)+" L0,"+(PT+h)+" Z");
  document.getElementById("chart-ymax").textContent=max;
}

async function refresh() {
  try {
    const d=await (await fetch("/api/status")).json();
    const stream=d.stream||{}, pi=d.pi||{};
    const online=stream.online;

    document.getElementById("pip").className="pip"+(online?"":" off");
    txt("live-label", online?"LIVE":"OFFLINE");
    txt("updated", new Date().toLocaleTimeString());

    txt("track-title", stream.title||"—");
    txt("track-artist", stream.artist||"—");
    txt("stream-since", streamDur(stream.stream_start));
    const badge=document.getElementById("np-badge");
    if (badge) badge.style.display=online?"":"none";

    txt("listeners", online ? stream.listeners : "—");
    txt("peak", d.peak_today!=null?d.peak_today:"—");

    if (d.latency_ms!=null) {
      const lv=document.getElementById("lat-val");
      txt("lat-val", d.latency_ms+"ms");
      if (lv) lv.style.color=latColor(d.latency_ms);
    }
    if (pi.uptime_s) txt("uptime-val", fmtUp(pi.uptime_s));

    buildChart(d.history);

    if (pi.cpu_pct!=null) {
      const cc=dynColor(pi.cpu_pct,60,80)||"#22d3ee";
      txt("cpu-val", pi.cpu_pct+"%");
      const cv=document.getElementById("cpu-val"); if(cv) cv.style.color=cc;
      setGauge("g-cpu", pi.cpu_pct, cc);
    }
    if (pi.mem) {
      const mc=dynColor(pi.mem.pct,70,85)||"#a78bfa";
      txt("mem-val", pi.mem.pct+"%");
      txt("mem-sub", pi.mem.used_mb+"/"+pi.mem.total_mb+"MB");
      setGauge("g-mem", pi.mem.pct, mc);
    }
    if (pi.temp_c!=null) {
      const tc=tempColor(pi.temp_c);
      txt("temp-val", pi.temp_c+"°");
      const tv=document.getElementById("temp-val"); if(tv) tv.style.color=tc;
      setGauge("g-temp", (pi.temp_c-30)/55*100, tc);
    }
    if (pi.disk) {
      txt("disk-val", pi.disk.pct+"%");
      txt("disk-sub", pi.disk.used_gb+"/"+pi.disk.total_gb+"GB");
      setGauge("g-disk", pi.disk.pct, dynColor(pi.disk.pct,70,85)||"#fbbf24");
    }
    if (pi.wifi) {
      const dbm=pi.wifi.dbm, pct=Math.max(0,Math.min(100,2*(dbm+100))), wc=wifiColor(pct);
      txt("wifi-val", dbm);
      const wv=document.getElementById("wifi-val"); if(wv) wv.style.color=wc;
      txt("wifi-sub", "q:"+pi.wifi.quality+"/70");
      setGauge("g-wifi", pct, wc);
    }

    if (pi.svcs) {
      const map={icecast2:"svc-icecast2",cloudflared:"svc-cloudflared"};
      for (const [k,id] of Object.entries(map)) {
        const el=document.getElementById(id);
        if (el) el.className="bdot "+(pi.svcs[k]?"bok":"bbad");
      }
    }
  } catch(e) {
    txt("live-label", "ERROR");
  }
}

refresh();
setInterval(refresh, REFRESH);
</script>
</body>
</html>'''

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            body, ct = HTML.encode('utf-8'), 'text/html; charset=utf-8'
        elif self.path == '/api/status':
            body = json.dumps(_api_payload()).encode()
            ct = 'application/json'
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    print(f'DTR Monitor → http://localhost:{PORT}')
    print(f'Polling Pi at {PI_IP} every {POLL_S}s')
    srv = HTTPServer(('localhost', PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('Stopped.')
