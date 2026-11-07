@echo off
if "%~1"=="--inside" goto :main
start "MirrorHub - Connect Phone" cmd /k ""%~f0" --inside"
exit /b

:main
setlocal
title MirrorHub - Connect Phone
pushd "%~dp0"

set "ADB=tools\scrcpy\scrcpy-win64-v4.0\adb.exe"
set "SCRCPY=tools\scrcpy\scrcpy-win64-v4.0\scrcpy.exe"

echo.
echo  ============================================
echo   MirrorHub  ^|  Connect Phone (Wireless)
echo  ============================================
echo.
echo  Dalam phone:
echo  Settings - Developer Options - Wireless Debugging
echo  Tap "Pair device with pairing code"
echo.
echo  Phone akan tunjuk:
echo    IP address ^& Port : 192.168.x.x:XXXXX
echo    Wi-Fi pairing code: XXXXXX
echo.

:: ── Step 1: Pair ─────────────────────────────────────────────────────────────
set /p PAIR_ADDR="  Masukkan IP:PORT dari phone (contoh: 192.168.1.5:41234): "
set /p PAIR_CODE="  Masukkan 6-digit code: "

echo.
echo  Pairing...
"%ADB%" pair %PAIR_ADDR% %PAIR_CODE%

if errorlevel 1 (
    echo.
    echo  [ERROR] Pair gagal. Semak IP:PORT dan code, lepas tu cuba lagi.
    pause
    exit /b 1
)

echo  Pair berjaya!
echo.

:: ── Step 2: Connect ──────────────────────────────────────────────────────────
echo  Sekarang pergi balik ke skrin "Wireless Debugging" utama.
echo  Ada tertulis "IP address ^& Port" — tu port CONNECTION (lain dari pairing port).
echo.
set /p CONN_ADDR="  Masukkan IP:PORT utama tu (contoh: 192.168.1.5:5555): "

echo.
echo  Connecting...
"%ADB%" connect %CONN_ADDR%

if errorlevel 1 (
    echo  [ERROR] Connect gagal.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Phone connected! Launching mirror...
echo  ============================================
echo.

"%SCRCPY%" -s %CONN_ADDR% --video-codec=h264 --max-size=1080 --max-fps=30 --window-title="MirrorHub - Phone Mirror"

echo.
pause
