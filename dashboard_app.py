#!/usr/bin/env python3
"""DTR Monitor — minimal tray dashboard app."""
import os
import subprocess
import threading
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

URL            = 'http://localhost:3000/d/dtr-monitor-v1'
TITLE          = 'DTR Monitor'
W, H           = 1440, 900
COLLECTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collector.py')

_window          = None
_tray            = None
_collector_on    = False


def _check_collector_running():
    out = subprocess.run(
        ['wmic', 'process', 'where', 'name="pythonw.exe"', 'get', 'CommandLine'],
        capture_output=True, text=True
    ).stdout
    return 'collector.py' in out


def _make_icon(size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill='#00b4d8')
    c, r = size // 2, size // 6
    d.ellipse([c - r, c - r, c + r, c + r], fill='white')
    return img


def _show(icon=None, _item=None):
    if _window:
        _window.show()


def _toggle_collector(icon=None, _item=None):
    global _collector_on
    if _collector_on:
        subprocess.run(
            ['wmic', 'process', 'where', 'CommandLine like "%collector.py%"', 'delete'],
            capture_output=True
        )
        _collector_on = False
    else:
        subprocess.Popen(['pythonw', COLLECTOR_PATH],
                         creationflags=subprocess.DETACHED_PROCESS)
        _collector_on = True
    if _tray:
        _tray.update_menu()


def _quit(icon=None, _item=None):
    if _tray:
        _tray.stop()
    if _window:
        _window.destroy()


def _on_closing():
    if _window:
        _window.hide()
    return False


def _run_tray():
    global _tray
    menu = pystray.Menu(
        item('Show Dashboard', _show, default=True),
        item(lambda _: 'Disable Collector' if _collector_on else 'Enable Collector', _toggle_collector),
        item('Quit', _quit),
    )
    _tray = pystray.Icon('DTR Monitor', _make_icon(), 'DTR Monitor', menu)
    _tray.run()


if __name__ == '__main__':
    _collector_on = _check_collector_running()
    threading.Thread(target=_run_tray, daemon=True).start()
    _window = webview.create_window(TITLE, URL, width=W, height=H, hidden=True)
    _window.events.closing += _on_closing
    webview.start()
