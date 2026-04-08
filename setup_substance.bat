@echo off
setlocal EnableDelayedExpansion

:: ── Check for Administrator rights (needed to write to Program Files) ─────────
net session >nul 2>&1
if errorlevel 1 (
    echo ============================================================
    echo  ERROR: This script must be run as Administrator.
    echo  Right-click setup_substance.bat and choose
    echo  "Run as administrator", then try again.
    echo ============================================================
    pause & exit /b 1
)

echo ============================================================
echo  Substance Painter MCP Server — Setup Script
echo ============================================================
echo.

:: ── Locate this script's directory ──────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: ── Find Python ──────────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.11+ from https://python.org and add it to PATH.
    pause & exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version_info.major, sys.version_info.minor)"') do set PY_VER=%%i
echo Python found: %PY_VER%

:: ── Create virtual environment ───────────────────────────────────────────────
if not exist "%SCRIPT_DIR%\.venv" (
    echo.
    echo Creating virtual environment...
    python -m venv "%SCRIPT_DIR%\.venv"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause & exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment already exists, skipping creation.
)

:: ── Install dependencies ─────────────────────────────────────────────────────
echo.
echo Installing dependencies (mcp, pydantic)...
"%SCRIPT_DIR%\.venv\Scripts\pip.exe" install -r "%SCRIPT_DIR%\requirements.txt" --quiet --upgrade
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause & exit /b 1
)
echo Dependencies installed.

:: ── Install Substance Painter Python plugin ──────────────────────────────────
echo.
echo Installing SP Python plugin...

set "SP_PLUGIN_SRC=%SCRIPT_DIR%\sp_socket_plugin.py"

:: Steam install path for Substance 3D Painter 2026
set "SP_STEAM_PLUGIN_DIR=C:\Program Files (x86)\Steam\steamapps\common\Substance 3D Painter 2026\resources\python\plugins"

:: Standard user Documents path (fallback)
set "SP_DOCS_PLUGIN_DIR=%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins"
set "SP_DOCS_PLUGIN_DIR_2026=%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter 2026\python\plugins"

:: Try Steam path first (most reliable for Steam installs)
set "SP_PLUGIN_DIR="
if exist "C:\Program Files (x86)\Steam\steamapps\common\Substance 3D Painter 2026" (
    set "SP_PLUGIN_DIR=%SP_STEAM_PLUGIN_DIR%"
    echo Detected Steam installation: Substance 3D Painter 2026
) else if exist "%SP_DOCS_PLUGIN_DIR_2026%" (
    set "SP_PLUGIN_DIR=%SP_DOCS_PLUGIN_DIR_2026%"
) else (
    set "SP_PLUGIN_DIR=%SP_DOCS_PLUGIN_DIR%"
)

if not exist "%SP_PLUGIN_DIR%" (
    mkdir "%SP_PLUGIN_DIR%"
    echo Created plugin directory: %SP_PLUGIN_DIR%
)

copy /Y "%SP_PLUGIN_SRC%" "%SP_PLUGIN_DIR%\sp_socket_plugin.py" >nul
if errorlevel 1 (
    echo WARNING: Could not copy plugin automatically.
    echo Please copy manually:
    echo   From: %SP_PLUGIN_SRC%
    echo   To:   %SP_PLUGIN_DIR%\sp_socket_plugin.py
) else (
    echo Plugin installed to: %SP_PLUGIN_DIR%\sp_socket_plugin.py
)

echo.
echo ============================================================
echo  IMPORTANT: Load the Plugin in Substance Painter
echo ============================================================
echo.
echo  1. Open Adobe Substance 3D Painter (Steam)
echo  2. In the menu bar, click:  Python ^> Reload Plugins
echo     (or simply restart SP — it loads plugins automatically)
echo  3. The plugin opens a socket on localhost:7002
echo  4. You should see "MCP socket plugin loaded" in SP's log
echo ============================================================
echo.

:: ── Update Claude Desktop config (merge, do not overwrite) ───────────────────
set "APPDATA_CLAUDE=%APPDATA%\Claude"
set "CONFIG_FILE=%APPDATA_CLAUDE%\claude_desktop_config.json"

:: Forward-slash versions of paths for JSON
set "PYTHON_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
set "SERVER_PY=%SCRIPT_DIR%\substance_painter_mcp_server.py"

echo Updating Claude Desktop configuration...
echo   Config: %CONFIG_FILE%
echo.

if not exist "%APPDATA_CLAUDE%" (
    mkdir "%APPDATA_CLAUDE%"
)

python -c ^
"import json, os, sys; ^
cfg_path = r'%CONFIG_FILE%'; ^
python_exe = r'%PYTHON_EXE%'.replace('\\\\', '/'); ^
server_py = r'%SERVER_PY%'.replace('\\\\', '/'); ^
cfg = {}; ^
try: ^
    f = open(cfg_path); ^
    cfg = json.load(f); ^
    f.close() ^
except Exception: ^
    pass; ^
cfg.setdefault('mcpServers', {}); ^
cfg['mcpServers']['substance_painter'] = {'command': python_exe, 'args': [server_py]}; ^
f = open(cfg_path, 'w'); ^
json.dump(cfg, f, indent=2); ^
f.close(); ^
print('Config updated successfully.')"

if errorlevel 1 (
    echo WARNING: Could not update Claude Desktop config automatically.
    echo Please add the following to %CONFIG_FILE% manually:
    echo.
    echo   "substance_painter": {
    echo     "command": "%PYTHON_EXE:\=/%",
    echo     "args": ["%SERVER_PY:\=/%"]
    echo   }
)

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Setup Complete!
echo ============================================================
echo.
echo  Next steps:
echo  1. Open Substance Painter (Steam)
echo  2. In SP menu bar: Python ^> Reload Plugins
echo     (or just restart SP — plugins load automatically on startup)
echo  3. Restart Claude Desktop to load the new MCP server
echo  4. Verify by asking Claude: "Get SP project info"
echo.
echo  Both Maya MCP and Substance Painter MCP will be available
echo  simultaneously in Claude Desktop.
echo ============================================================
echo.
pause
endlocal
