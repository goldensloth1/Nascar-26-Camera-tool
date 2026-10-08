# NASCAR 26 Camera Tool

A small Windows app that changes the field of view and position of every driving camera in NASCAR 26
(Cockpit, Cockpit 2, Hood, Roof, Bumper, Chase, Far chase), for all four series.

## What it does (and doesn't do)

- It edits **camera values only** (FOV and car-relative position) in the **running game's memory**, using the
  standard Windows `ReadProcessMemory` / `WriteProcessMemory` calls.
- It does **not** modify, patch or add any game files, does **not** inject code or DLLs, and does **not** hook
  any game functions. Closing the game puts every camera back to stock.
- Before writing a camera it checks that the current values match the known stock values
  (`sheets/camera_stock.json`). If a game update changes anything, it writes nothing and says so.
- Settings are saved in `%APPDATA%\NASCAR26 Camera Tool\settings.json`.
- Offline modes only.

## Files

| File | Purpose |
| --- | --- |
| `tools/camera_tool.py` | The window (tkinter), entry point |
| `tools/camera_core.py` | Finds the camera data and writes the FOV / position values |
| `tools/ue.py` | Reads the game's Unreal Engine object and name tables to find the camera data |
| `sheets/camera_stock.json` | Stock camera values, used as a safety check and for "Reset" |
| `assets/tire.ico` | App icon |

## Run from source

Needs Windows and Python 3 (from python.org, which includes tkinter). No other packages are needed to run it.

```
python tools\camera_tool.py
```

## Build the .exe

1. Install Python 3 from python.org (tick "Add python.exe to PATH").
2. Download or clone this repository.
3. Double-click `build.bat` (or run it from a command prompt in this folder).

It installs PyInstaller (`requirements.txt`) and builds `dist\NASCAR26-Camera Tool.exe`. The command it runs is:

```
python -m PyInstaller --onefile --windowed --name "NASCAR26-Camera Tool" --icon "assets\tire.ico" --add-data "assets\tire.ico;." --add-data "sheets\camera_stock.json;." --paths "tools" --noconfirm "tools\camera_tool.py"
```

## Using it

1. Start NASCAR 26.
2. Open the Camera Tool. The dot at the top turns green when it has found the game.
3. Pick a view and move the sliders. Changes save and apply straight away.
4. Restart the race (or start a new one) to see the change.
