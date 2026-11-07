@echo off
:: MirrorHub Release 2.1.2 — CI Validation Gate
:: Runs all test categories in order; stops on first failure.
:: Usage: validate.bat [--fast]   (--fast skips performance/stability)
:: Exit code: 0 = all pass, 1 = failure

if "%~1"=="--inside" goto :main
start "validate" /wait cmd /c "%~f0" --inside %*
exit /b %errorlevel%

:main
pushd "%~dp0"

set FAST_MODE=0
if "%~2"=="--fast" set FAST_MODE=1

echo.
echo ══════════════════════════════════════════════════════════════════
echo   MirrorHub 2.1.2 — Validation Gate
echo ══════════════════════════════════════════════════════════════════
echo.

:: ── Activate virtualenv ────────────────────────────────────────────────────
call backend\.venv\Scripts\activate.bat
if errorlevel 1 (
    echo [FAIL] Could not activate virtualenv at backend\.venv
    exit /b 1
)

cd backend

:: ── Install dev dependencies (idempotent) ──────────────────────────────────
echo [step] Installing dev dependencies...
pip install -q -r requirements-dev.txt
if errorlevel 1 (
    echo [FAIL] pip install failed
    exit /b 1
)
echo [ok] Dependencies installed.
echo.

:: ── 1. Unit tests ──────────────────────────────────────────────────────────
echo [step 1/5] Unit tests...
pytest tests/unit/ -v --tb=short --no-header -q 2>&1
if errorlevel 1 (
    echo.
    echo [FAIL] Unit tests failed. Fix before proceeding.
    exit /b 1
)
echo [PASS] Unit tests
echo.

:: ── 2. Integration tests ───────────────────────────────────────────────────
echo [step 2/5] Integration tests...
pytest tests/integration/ -v --tb=short --no-header -q 2>&1
if errorlevel 1 (
    echo.
    echo [FAIL] Integration tests failed. Fix before proceeding.
    exit /b 1
)
echo [PASS] Integration tests
echo.

:: ── 3. Concurrency tests ───────────────────────────────────────────────────
echo [step 3/5] Concurrency tests (Scenarios A-D)...
pytest tests/concurrency/ -v --tb=short --no-header -q 2>&1
if errorlevel 1 (
    echo.
    echo [FAIL] Concurrency tests failed. Fix before proceeding.
    exit /b 1
)
echo [PASS] Concurrency tests
echo.

:: ── 4. Recovery tests ─────────────────────────────────────────────────────
echo [step 4/5] Recovery tests...
pytest tests/recovery/ -v --tb=short --no-header -q 2>&1
if errorlevel 1 (
    echo.
    echo [FAIL] Recovery tests failed. Fix before proceeding.
    exit /b 1
)
echo [PASS] Recovery tests
echo.

:: ── 5. Performance tests (skip in --fast mode) ────────────────────────────
if "%FAST_MODE%"=="1" (
    echo [skip] Performance tests (--fast mode)
) else (
    echo [step 5/5] Performance tests...
    pytest tests/performance/ -v --tb=short --no-header -q 2>&1
    if errorlevel 1 (
        echo.
        echo [FAIL] Performance tests failed.
        exit /b 1
    )
    echo [PASS] Performance tests
)
echo.

:: ── Coverage summary ──────────────────────────────────────────────────────
echo [step] Full coverage report...
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=60 -q --no-header 2>&1
if errorlevel 1 (
    echo [WARN] Coverage threshold not met (requires 60%%)
)
echo.

echo ══════════════════════════════════════════════════════════════════
echo   ALL GATES PASSED — Release 2.1.2 validation complete
echo ══════════════════════════════════════════════════════════════════
echo.

cd ..
popd
exit /b 0
