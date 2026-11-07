@echo off
if "%~1"=="--inside" goto :main
start "MirrorHub - Mirror" cmd /k ""%~f0" --inside"
exit /b

:main
setlocal enabledelayedexpansion
title MirrorHub - Mirror
pushd "%~dp0"

set "ADB=tools\scrcpy\scrcpy-win64-v4.0\adb.exe"
set "SCRCPY=tools\scrcpy\scrcpy-win64-v4.0\scrcpy.exe"
set "SAVEFILE=tools\last_device.txt"

echo.
echo  ============================================
echo   MirrorHub  ^|  Mirror Phone
echo  ============================================
echo.

:: ── Cuba auto-discover via mDNS ──────────────────────────────────────────────
echo  Mencari device dalam network...
for /f "tokens=2" %%a in ('"%ADB%" mdns services 2^>nul ^| findstr "_adb-tls-connect"') do (
    set "MDNS_NAME=%%a"
)

if defined MDNS_NAME (
    echo  Device jumpa via mDNS: !MDNS_NAME!
    echo  Connecting...
    "%ADB%" connect !MDNS_NAME! >nul 2>&1
    set "TARGET=!MDNS_NAME!"
    goto :launch
)

:: ── Cuba reconnect device terakhir ───────────────────────────────────────────
if exist "%SAVEFILE%" (
    set /p LAST_DEVICE=<"%SAVEFILE%"
    echo  Cuba reconnect device terakhir: !LAST_DEVICE!
    "%ADB%" connect !LAST_DEVICE! >nul 2>&1
    "%ADB%" devices | findstr "!LAST_DEVICE!" | findstr "device" >nul 2>&1
    if not errorlevel 1 (
        set "TARGET=!LAST_DEVICE!"
        echo  Reconnect berjaya!
        goto :launch
    )
    echo  Device terakhir tidak jumpa.
    echo.
)

:: ── Manual fallback ───────────────────────────────────────────────────────────
echo  Auto-discover gagal. Masukkan IP:PORT secara manual.
echo  (Tengok IP:PORT dalam phone: Developer Options - Wireless Debugging)
echo.
set /p CONN_ADDR="  IP:PORT: "

echo.
echo  Connecting...
"%ADB%" connect %CONN_ADDR%
if errorlevel 1 (
    echo.
    echo  [ERROR] Gagal connect. Semak IP:PORT dan pastikan same WiFi.
    echo.
    echo  Kalau WiFi baru, guna connect_phone.bat untuk pair dulu.
    pause
    exit /b 1
)
set "TARGET=%CONN_ADDR%"

:: Simpan untuk next time
echo %CONN_ADDR%>"%SAVEFILE%"

:launch
echo.
echo  Launching mirror...
echo.
"%SCRCPY%" -s %TARGET% --video-codec=h264 --audio-codec=opus --max-size=1080 --max-fps=30 --window-title="MirrorHub - Phone Mirror"

echo.
pause
