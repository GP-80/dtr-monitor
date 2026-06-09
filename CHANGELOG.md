# Changelog

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
