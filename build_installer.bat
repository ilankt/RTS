@echo off
REM ===========================================================================
REM  RTS - one-command Windows installer builder
REM
REM    [1] PyInstaller  ->  dist\RTS\RTS.exe      (portable, zip-and-share)
REM    [2] Inno Setup   ->  installer_output\RTS_Setup_<ver>.exe  (installer)
REM
REM  Just double-click this file (or run it from a terminal). It cd's to its
REM  own folder, so it works from anywhere.
REM
REM  Prerequisites:
REM    * Python on PATH with pygame + perlin-noise (the same one that runs the
REM      game). PyInstaller is auto-installed into it if missing.
REM    * Inno Setup 6 for step [2] only -> https://jrsoftware.org/isdl.php
REM      Without it, step [1] still produces the portable build.
REM ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=python"

REM Single source of truth for the version -> shown on the menu AND stamped
REM onto the installer (passed to Inno Setup below via /DMyAppVersion).
set "APP_VERSION="
for /f "usebackq delims=" %%v in (`%PY% -c "import core.version; print(core.version.GAME_VERSION)"`) do set "APP_VERSION=%%v"
if not defined APP_VERSION (
  echo ERROR: could not read version from core\version.py. Is Python on PATH^?
  exit /b 1
)
echo Building RTS %APP_VERSION%

echo.
echo === [1/4] Ensuring PyInstaller is installed ===
%PY% -m pip install --disable-pip-version-check --quiet pyinstaller
if errorlevel 1 (
  echo ERROR: could not install PyInstaller. Is Python on PATH^?
  exit /b 1
)

echo.
echo === [2/4] Generating the app icon from assets\ICON.png ===
REM Non-fatal: a missing icon or missing Pillow just falls back to the
REM default exe icon; it must never block the build.
%PY% tools\make_icon.py
if errorlevel 1 echo WARNING: icon generation failed - using default exe icon.

echo.
echo === [3/4] Building the app with PyInstaller ===
REM Wipe previous output so nothing stale ever ships.
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
%PY% -m PyInstaller --noconfirm RTS.spec
if errorlevel 1 (
  echo ERROR: PyInstaller build failed. See the log above.
  exit /b 1
)
echo Portable build ready: dist\RTS\RTS.exe

echo.
echo === [4/4] Building the installer with Inno Setup ===
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo.
  echo Inno Setup 6 not found - skipping the installer step.
  echo The portable build in  dist\RTS\  is ready to zip and share as-is.
  echo To also build the installer, install Inno Setup 6 from
  echo     https://jrsoftware.org/isdl.php
  echo and re-run this script.
  exit /b 0
)

"%ISCC%" /DMyAppVersion=%APP_VERSION% installer.iss
if errorlevel 1 (
  echo ERROR: Inno Setup compile failed. See the log above.
  exit /b 1
)

echo.
echo === DONE ===
echo Installer written to installer_output\ :
dir /b installer_output 2>nul
endlocal
