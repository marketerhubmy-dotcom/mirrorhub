@echo off
if "%~1"=="--inside" goto :main
start "MirrorHub Launcher" cmd /k ""%~f0" --inside"
exit /b

:main
setlocal
title MirrorHub Launcher
pushd "%~dp0"
set "HERE=%~dp0"

echo.
echo  ============================================
echo   MirrorHub  ^|  One-Click Launcher
echo  ============================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak jumpa. Install dari python.org dan tick "Add to PATH".
    pause & exit /b 1
)
echo  Python: & python --version

:: ── Check Node.js ────────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js tidak jumpa. Install dari nodejs.org.
    pause & exit /b 1
)
echo  Node.js: & node --version
echo.

:: ── Create venv ──────────────────────────────────────────────────────────────
if not exist "backend\.venv\Scripts\activate.bat" (
    echo  [1/4] Mencipta Python virtual environment...
    python -m venv "backend\.venv"
    if errorlevel 1 ( echo  [ERROR] Gagal cipta venv. & pause & exit /b 1 )
)

:: ── pip install ───────────────────────────────────────────────────────────────
if not exist "backend\.venv\Lib\site-packages\fastapi" (
    echo  [2/4] Installing backend packages - tunggu...
    call "backend\.venv\Scripts\pip.exe" install -r "backend\requirements.txt" -q
    if errorlevel 1 ( echo  [ERROR] pip install gagal. & pause & exit /b 1 )
)

:: ── npm install ───────────────────────────────────────────────────────────────
if not exist "frontend\node_modules" (
    echo  [3/4] Installing frontend packages - tunggu...
    pushd frontend
    call npm install --silent
    if errorlevel 1 ( echo  [ERROR] npm install gagal. & popd & pause & exit /b 1 )
    popd
)

echo.
echo  ============================================
echo   Pilih mod:
echo.
echo    [1] App Mode  ^<-- RECOMMENDED
echo        Buka macam apps dalam laptop
echo        (tiada browser diperlukan)
echo.
echo    [2] Dev Mode
echo        Buka dalam browser (untuk debugging)
echo  ============================================
echo.
set /p CHOICE="  Pilih (1/2): "
echo.

if "%CHOICE%"=="2" goto :devmode

:: ── Kill proses lama ─────────────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

:: ════════════════════════════════════════════════════════
:appmode
:: ════════════════════════════════════════════════════════

:: Build React kalau belum ada
if not exist "frontend\dist\index.html" (
    echo  [3/4] Building frontend - tunggu sekejap...
    pushd frontend
    call npm run build
    if errorlevel 1 ( echo  [ERROR] Build gagal. & popd & pause & exit /b 1 )
    popd
    echo  [3/4] Build done.
    echo.
)

:: Install pywebview kalau belum
if not exist "backend\.venv\Lib\site-packages\webview" (
    echo  Installing pywebview...
    call "backend\.venv\Scripts\pip.exe" install pywebview -q
)

echo  Launching MirrorHub...
echo  (Window akan terbuka dalam beberapa saat)
echo.

start "" /d "%HERE%backend" "backend\.venv\Scripts\pythonw.exe" desktop.py

timeout /t 2 /nobreak >nul
echo  MirrorHub running!
echo  Close window MirrorHub untuk stop.
echo.
pause
goto :done

:: ════════════════════════════════════════════════════════
:devmode
:: ════════════════════════════════════════════════════════

start "MirrorHub Backend :8000" /d "%HERE%backend" cmd /k ".venv\Scripts\activate && python run.py"
timeout /t 3 /nobreak >nul
start "MirrorHub Frontend :3000" /d "%HERE%frontend" cmd /k "npm run dev"
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo  Dev mode running.
echo  Dashboard : http://localhost:3000
echo.
pause

:done
popd
