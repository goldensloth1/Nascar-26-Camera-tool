@echo off
rem Builds dist\NASCAR26-Camera Tool.exe from source. Needs Python 3 (with tkinter) on PATH.
cd /d "%~dp0"
python -m pip install -r requirements.txt || exit /b 1
python -m PyInstaller --onefile --windowed --name "NASCAR26-Camera Tool" ^
  --icon "%CD%\assets\tire.ico" ^
  --add-data "%CD%\assets\tire.ico;." ^
  --add-data "%CD%\sheets\camera_stock.json;." ^
  --paths "%CD%\tools" ^
  --distpath "%CD%\dist" --workpath "%CD%\build" --specpath "%CD%\build" ^
  --noconfirm "%CD%\tools\camera_tool.py"
