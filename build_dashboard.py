#!/usr/bin/env python3
"""
Deep Trip Radio — Grafana dashboard builder
Generates grafana_dashboard.json.  Run once (or after any changes).

Usage : python build_dashboard.py
Import: Grafana -> Dashboards -> Import -> Upload grafana_dashboard.json
        (delete existing dashboard first for a clean import)
"""
import json
from pathlib import Path

# ── Datasource placeholder — Grafana resolves this on import ─────────────────
DS = {'type': 'frser-sqlite-datasource', 'uid': '${DS_SQLITE}'}

# ── Palette ───────────────────────────────────────────────────────────────────
TEAL   = '#22d3ee'
PURPLE = '#8b5cf6'
GREEN  = '#34d399'
YELLOW = '#fbbf24'
RED    = '#f87171'
MUTED  = '#475569'
TEXT   = '#e2e8f0'

# ── Query helpers ─────────────────────────────────────────────────────────────
def q(sql):
    """Stat / gauge / table query — returns tabular data."""
    return [{'datasource': DS, 'rawQueryText': sql.strip(),
             'refId': 'A', 'queryType': 'table'}]

def q_ts(sql):
    """Time series query — uses table mode; Grafana transform handles time typing."""
    return [{'datasource': DS, 'rawQueryText': sql.strip(),
             'refId': 'A', 'queryType': 'table'}]

def last(table, field):
    """SELECT the most recent value of a single field."""
    return f'SELECT {field} AS value FROM {table} ORDER BY ts DESC LIMIT 1'

# ── Misc helpers ──────────────────────────────────────────────────────────────
def steps(*pairs):
    """Threshold step list: steps((None,'green'),(60,'yellow'),(80,'red'))"""
    return [{'value': v, 'color': c} for v, c in pairs]

def gp(x, y, w, h):
    return {'x': x, 'y': y, 'w': w, 'h': h}

_id = 0
def uid():
    global _id; _id += 1; return _id

# ── Panel builders ────────────────────────────────────────────────────────────
def stat(title, sql, gridpos, *,
         unit='', decimals=0, reduce='lastNotNull',
         color_mode='value', text_mode='value',
         font_size=None, mappings=None, thresholds=None, no_value='—'):
    th = thresholds or steps((None, GREEN))
    p = {
        'id': uid(), 'type': 'stat', 'title': title,
        'gridPos': gridpos, 'datasource': DS,
        'targets': q(sql),
        'options': {
            # fields: '/.*/' ensures string columns are included, not just numeric
            'reduceOptions': {'calcs': [reduce], 'fields': '/.*/', 'values': False},
            'orientation':  'auto',
            'textMode':     text_mode,
            'colorMode':    color_mode,
            'graphMode':    'none',
            'justifyMode':  'center',
            'noValue':      no_value,
        },
        'fieldConfig': {
            'defaults': {
                'unit': unit, 'decimals': decimals,
                'color': {'mode': 'thresholds'},
                'thresholds': {'mode': 'absolute', 'steps': th},
                'mappings': mappings or [],
            },
            'overrides': [],
        },
    }
    if font_size:
        p['options']['text'] = {'valueSize': font_size}
    return p

def gauge(title, sql, gridpos, *,
          unit='percent', min_val=0, max_val=100,
          decimals=1, thresholds=None):
    th = thresholds or steps((None, GREEN), (70, YELLOW), (85, RED))
    return {
        'id': uid(), 'type': 'gauge', 'title': title,
        'gridPos': gridpos, 'datasource': DS,
        'targets': q(sql),
        'options': {
            'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
            'orientation': 'auto',
            'showThresholdLabels':  False,
            'showThresholdMarkers': True,
        },
        'fieldConfig': {
            'defaults': {
                'unit': unit, 'decimals': decimals,
                'min': min_val, 'max': max_val,
                'color': {'mode': 'thresholds'},
                'thresholds': {'mode': 'absolute', 'steps': th},
                'mappings': [],
            },
            'overrides': [],
        },
    }

def timeseries(title, sql, gridpos, *, color=TEAL):
    """Line chart — frser-sqlite-datasource time_series mode.
    SQL must alias the epoch-seconds column as 'time'.
    """
    return {
        'id': uid(), 'type': 'timeseries', 'title': title,
        'gridPos': gridpos, 'datasource': DS,
        'targets': [{'datasource': DS, 'rawQueryText': sql.strip(),
                     'refId': 'A', 'queryType': 'time_series'}],
        'options': {
            'tooltip': {'mode': 'single', 'sort': 'none'},
            'legend':  {'showLegend': False},
        },
        'fieldConfig': {
            'defaults': {
                'color':    {'fixedColor': color, 'mode': 'fixed'},
                'unit':     'short',
                'decimals': 0,
                'custom': {
                    'lineInterpolation': 'linear',
                    'lineWidth':         2,
                    'fillOpacity':       12,
                    'gradientMode':      'opacity',
                    'showPoints':        'never',
                    'spanNulls':         True,
                },
            },
            'overrides': [],
        },
    }

def barchart(title, sql, gridpos, *, color=TEAL):
    """Hourly bar chart — plain tabular data, no time field needed.
    Fallback if timeseries shows 'Data is missing a time field'.
    """
    return {
        'id': uid(), 'type': 'barchart', 'title': title,
        'gridPos': gridpos, 'datasource': DS,
        'targets': q(sql),
        'options': {
            'xField':       'hour',
            'barWidth':     0.85,
            'fillOpacity':  70,
            'gradientMode': 'opacity',
            'orientation':  'auto',
            'stacking':     'none',
            'showValue':    'never',
            'legend':       {'showLegend': False},
            'tooltip':      {'mode': 'single'},
        },
        'fieldConfig': {
            'defaults': {
                'color':   {'fixedColor': color, 'mode': 'fixed'},
                'unit':    'none',
                'decimals': 0,
                'min':     0,
                'custom':  {'fillOpacity': 70, 'lineWidth': 0, 'gradientMode': 'opacity'},
            },
            'overrides': [],
        },
    }

def track_table(title, sql, gridpos):
    """Recently Played table — uses pre-formatted strings, no unit trickery."""
    return {
        'id': uid(), 'type': 'table', 'title': title,
        'gridPos': gridpos, 'datasource': DS,
        'targets': q(sql),
        'options': {'footer': {'show': False}, 'showHeader': True},
        'fieldConfig': {
            'defaults': {
                'color':  {'mode': 'fixed', 'fixedColor': TEXT},
                'custom': {'align': 'left', 'displayMode': 'auto', 'filterable': False},
                'mappings': [],
                'thresholds': {'mode': 'absolute', 'steps': [{'color': TEXT, 'value': None}]},
            },
            'overrides': [
                {
                    'matcher': {'id': 'byName', 'options': 'played'},
                    'properties': [
                        {'id': 'displayName',        'value': 'When'},
                        {'id': 'custom.width',        'value': 150},
                        {'id': 'custom.displayMode',  'value': 'color-text'},
                        {'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': MUTED}},
                    ],
                },
                {
                    'matcher': {'id': 'byName', 'options': 'artist'},
                    'properties': [
                        {'id': 'custom.width',       'value': 160},
                        {'id': 'custom.displayMode', 'value': 'color-text'},
                        {'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': PURPLE}},
                    ],
                },
                {
                    'matcher': {'id': 'byName', 'options': 'title'},
                    'properties': [
                        {'id': 'displayName', 'value': 'Track'},
                    ],
                },
            ],
        },
        'transformations': [],
    }

# ── Value mappings ────────────────────────────────────────────────────────────
ONLINE_MAP = [{
    'type': 'value',
    'options': {
        '0': {'text': 'Offline', 'color': RED,   'index': 0},
        '1': {'text': '● Live',  'color': GREEN,  'index': 1},
    },
}]

SERVICE_MAP = [{
    'type': 'value',
    'options': {
        '0': {'text': 'Down',   'color': RED,   'index': 0},
        '1': {'text': 'Online', 'color': GREEN, 'index': 1},
    },
}]

# ── Panels ────────────────────────────────────────────────────────────────────
panels = [

    # ── Row 1: Status strip (y=0, h=4) ──────────────────────────────────────
    stat('Stream',      last('stream', 'online'),     gp(0,  0, 4, 4),
         text_mode='value', color_mode='background',
         mappings=ONLINE_MAP, thresholds=steps((None, RED), (1, GREEN))),

    stat('Listeners',   last('stream', 'listeners'),  gp(4,  0, 5, 4),
         color_mode='none', thresholds=steps((None, TEAL))),

    stat('Peak Today',
         "SELECT COALESCE(MAX(listeners), 0) AS value FROM stream "
         "WHERE date(ts, 'unixepoch') = date('now')",
         gp(9, 0, 3, 4), color_mode='none', thresholds=steps((None, PURPLE))),

    stat('Latency',     last('stream', 'latency_ms'), gp(12, 0, 3, 4),
         unit='ms', thresholds=steps((None, GREEN), (150, YELLOW), (300, RED))),

    stat('Pi Uptime',
         "SELECT printf('%dd %dh', uptime_s/86400, (uptime_s % 86400)/3600) AS value "
         "FROM pi_system ORDER BY ts DESC LIMIT 1",
         gp(15, 0, 3, 4), text_mode='value', color_mode='none',
         thresholds=steps((None, TEXT))),

    stat('icecast2',    last('pi_system', 'icecast2'),    gp(18, 0, 3, 4),
         color_mode='background', mappings=SERVICE_MAP,
         thresholds=steps((None, RED), (1, GREEN))),

    stat('cloudflared', last('pi_system', 'cloudflared'), gp(21, 0, 3, 4),
         color_mode='background', mappings=SERVICE_MAP,
         thresholds=steps((None, RED), (1, GREEN))),

    # ── Row 2: Now Playing + Recently Played (y=4) ───────────────────────────
    stat('Now Playing',
         'SELECT title AS value FROM stream ORDER BY ts DESC LIMIT 1',
         gp(0, 4, 14, 5),
         text_mode='value', color_mode='none', font_size=32,
         thresholds=steps((None, TEXT))),

    stat('Artist',
         'SELECT artist AS value FROM stream ORDER BY ts DESC LIMIT 1',
         gp(0, 9, 14, 3),
         text_mode='value', color_mode='none', font_size=32,
         thresholds=steps((None, PURPLE))),

    # datetime() returns a human-readable string — no Grafana unit conversion needed
    track_table(
        'Recently Played',
        "SELECT datetime(ts, 'unixepoch', 'localtime') AS played, artist, title "
        "FROM track_history ORDER BY ts DESC LIMIT 5",
        gp(14, 4, 10, 8),
    ),

    # ── Row 3: Listener history (y=12, h=8) ──────────────────────────────────
    # Bar chart bucketed by hour — frser-sqlite-datasource cannot expose a time
    # field via JSON import (timeseries panels show "Data is missing a time field"
    # regardless of queryType or convertFieldTypes transformations).
    barchart(
        'Listener History — ${history_period:text}',
        # $history_period value is seconds (e.g. 86400); used directly in arithmetic — no CASE needed.
        # ${history_period:text} in the title gives the human-readable label (e.g. "24 h").
        "SELECT strftime('%H:00', datetime(MIN(ts), 'unixepoch', 'localtime')) AS hour, "
        "MAX(listeners) AS listeners "
        "FROM stream "
        "WHERE ts >= strftime('%s','now') - $history_period "
        "GROUP BY strftime('%Y%m%d%H', datetime(ts, 'unixepoch', 'localtime')) "
        "ORDER BY MIN(ts)",
        gp(0, 12, 24, 8),
    ),

    # ── Row 4: Pi gauges (y=20, h=8) ─────────────────────────────────────────
    gauge('CPU',        last('pi_system', 'cpu_pct'),  gp(0,  20, 5, 8),
          thresholds=steps((None, GREEN), (60, YELLOW), (80, RED))),

    gauge('Memory',     last('pi_system', 'mem_pct'),  gp(5,  20, 5, 8),
          thresholds=steps((None, GREEN), (70, YELLOW), (85, RED))),

    gauge('Temperature',last('pi_system', 'temp_c'),   gp(10, 20, 5, 8),
          unit='celsius', min_val=20, max_val=85,
          thresholds=steps((None, GREEN), (55, YELLOW), (70, RED))),

    gauge('Disk',       last('pi_system', 'disk_pct'), gp(15, 20, 5, 8),
          thresholds=steps((None, GREEN), (70, YELLOW), (85, RED))),

    gauge('WiFi Signal',last('pi_system', 'wifi_dbm'), gp(20, 20, 4, 8),
          unit='dBm', min_val=-100, max_val=-30, decimals=0,
          thresholds=steps((None, RED), (-75, YELLOW), (-60, GREEN))),
]

# ── Dashboard ─────────────────────────────────────────────────────────────────
dashboard = {
    # __inputs tells Grafana to ask which datasource to map DS_SQLITE to on import
    '__inputs': [{
        'name':       'DS_SQLITE',
        'label':      'SQLite (DTR)',
        'description':'SQLite datasource pointing to dtr_monitor.db',
        'type':       'datasource',
        'pluginId':   'frser-sqlite-datasource',
        'pluginName': 'SQLite',
    }],
    'title':       'Deep Trip Radio',
    'uid':         'dtr-monitor-v1',
    'description': 'Live monitoring — 24/7 psychedelic internet radio',
    'tags':        ['radio', 'icecast', 'raspberrypi'],
    'style':       'dark',
    'timezone':    'browser',
    'refresh':     '15s',
    'time':        {'from': 'now-24h', 'to': 'now'},
    'timepicker':  {},
    'graphTooltip':         1,
    'schemaVersion':        38,
    'version':              1,
    'panels':               panels,
    'annotations':          {'list': []},
    'templating':           {'list': [{
        'type':        'custom',
        'name':        'history_period',
        'label':       'History',
        # "label : value" — dropdown shows label, $history_period substitutes numeric value
        'query':       '5 min : 300, 30 min : 1800, 1 h : 3600, 6 h : 21600, 12 h : 43200, 24 h : 86400, 7 days : 604800',
        'queryValue':  '',
        'current':     {'selected': True, 'text': '24 h', 'value': '86400'},
        'options': [
            {'selected': False, 'text': '5 min',  'value': '300'},
            {'selected': False, 'text': '30 min', 'value': '1800'},
            {'selected': False, 'text': '1 h',    'value': '3600'},
            {'selected': False, 'text': '6 h',    'value': '21600'},
            {'selected': False, 'text': '12 h',   'value': '43200'},
            {'selected': True,  'text': '24 h',   'value': '86400'},
            {'selected': False, 'text': '7 days', 'value': '604800'},
        ],
        'hide':        0,
        'includeAll':  False,
        'multi':       False,
        'skipUrlSync': False,
        'refresh':     0,
        'sort':        0,
    }]},
    'links':                [],
    'fiscalYearStartMonth': 0,
    'liveNow':              False,
}

out = Path(__file__).parent / 'grafana_dashboard.json'
out.write_text(json.dumps(dashboard, indent=2), encoding='utf-8')
print(f'Dashboard written -> {out}')
print('Delete the existing dashboard in Grafana, then import this file fresh.')
