#!/usr/bin/env python3
"""DTR Monitor — minimal tray dashboard app."""
import threading
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

URL   = 'http://localhost:3000/d/dtr-monitor-v1'
TITLE = 'DTR Monitor'
W, H  = 1440, 900

_window = None
_tray   = None


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
    menu  = pystray.Menu(
        item('Show Dashboard', _show, default=True),
        item('Quit', _quit),
    )
    _tray = pystray.Icon('DTR Monitor', _make_icon(), 'DTR Monitor', menu)
    _tray.run()


if __name__ == '__main__':
    threading.Thread(target=_run_tray, daemon=True).start()
    _window = webview.create_window(TITLE, URL, width=W, height=H, hidden=True)
    _window.events.closing += _on_closing
    webview.start()
