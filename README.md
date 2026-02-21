# Fixer

Fixer is a Windows-first background optimizer that adjusts process priorities by context (gaming, streaming, normal use), enforces configurable process policy, and can run as a tray app, startup app, or Windows service.

## Features

- Context detection for `default`, `gaming`, and `streaming` profiles.
- Priority manager with profile-driven `boost`, `throttle`, and `close` targets.
- Resource watchdog for sustained CPU hogs.
- Suspicious process detection for miner, keylogger, and unauthorized recorder patterns.
- Runtime safety modes: `safe`, `balanced`, `aggressive`.
- Tray UI with start/stop, mode/profile overrides, and log file access.
- Learning mode that writes suggestion snapshots for config tuning.
- Startup registration (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
- Windows service install/start/stop/status/remove commands.

## Development Install

```powershell
pip install -r requirements.txt
```

## Run

Single cycle dry-run:

```powershell
python -m fixer run --dry-run --once
```

Continuous console run:

```powershell
python -m fixer run --dry-run
```

Tray app:

```powershell
python -m fixer tray --dry-run
```

Legacy shortcut (maps to `run`):

```powershell
python -m fixer --dry-run
```

## Learning Mode

Enable from CLI:

```powershell
python -m fixer run --dry-run --learning-mode
```

Config section (`config/default.json`):

```json
"learning": {
  "enabled": true,
  "output_path": "data/learning_suggestions.json",
  "min_occurrences": 5,
  "autosave_seconds": 30.0
}
```

Suggestion targets produced by learning snapshots:
- `resource_allowlist`
- `suspicious.authorized_recorders`
- `game_processes`
- `streaming_processes`

## Startup Commands

Install startup entry:

```powershell
python -m fixer startup install --config config/default.json --dry-run --learning-mode
```

Status:

```powershell
python -m fixer startup status
```

Remove:

```powershell
python -m fixer startup remove
```

## Service Commands

Service mode requires admin rights.

Install (auto-start):

```powershell
python -m fixer service install --config config/default.json
```

Install (manual start):

```powershell
python -m fixer service install --config config/default.json --manual-start
```

Control:

```powershell
python -m fixer service start
python -m fixer service stop
python -m fixer service status
python -m fixer service remove
```

Service settings path:
- `C:\ProgramData\Fixer\service_settings.json`

## Build For Windows

Install build tools:

```powershell
pip install -r requirements.txt
pip install -r requirements-build.txt
```

Build executables:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Clean -RunTests -Zip
```

Build outputs:
- `dist\FixerCLI\FixerCLI.exe`
- `dist\FixerTray\FixerTray.exe`
- `release\Fixer-Windows\`
- `release\Fixer-Windows.zip` (when `-Zip` is used)

## Build Installer (Inno Setup)

After building release files, install Inno Setup (which provides `iscc`) and compile installer script:

```powershell
iscc installer\fixer.iss
```

Installer output:
- `release\Fixer-Setup.exe`

## Safety Notes

- Start in `safe` mode.
- Keep `--dry-run` enabled until process rules are tuned.
- Protected processes are never terminated.
- Review learning suggestions before applying them.
