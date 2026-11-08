<#
 Build the Windows installer end to end.
   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipTests] [-SkipSmoke]
 Output: dist\Mirrorhub-Setup-<version>.exe  (+ dist\SHA256SUMS.txt, build\build-report.txt)
 Never touches user data: every run here uses a throw-away MIRRORHUB_DATA_DIR.
#>
param([switch]$SkipTests, [switch]$SkipSmoke)
# Native tools write progress to stderr; with 'Stop' PowerShell 5.1 would treat that as failure. Exit codes are checked explicitly.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$report = New-Object System.Collections.Generic.List[string]
function Step($n) { Write-Host "`n=== $n ===" -ForegroundColor Cyan; $report.Add("== $n") }

$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 not found (winget install JRSoftware.InnoSetup)' }
$tmpData = Join-Path $env:TEMP ("mirrorhub-build-" + [guid]::NewGuid().ToString('N'))
$env:MIRRORHUB_DATA_DIR = $tmpData

if (-not $SkipTests) {
  Step 'backend tests'
  Push-Location backend
  $t = & $py -m pytest -q --no-cov -p no:cacheprovider 2>&1
  $code = $LASTEXITCODE
  Pop-Location
  $t | Select-Object -Last 2
  if ($code -ne 0) { throw 'backend tests failed' }
  $report.Add(($t | Select-Object -Last 1))
}

Step 'frontend build'
Push-Location frontend
npm ci --no-audit --no-fund 2>&1 | Select-Object -Last 2
npm run build 2>&1 | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }
Pop-Location

Step 'pyinstaller'
$dist = Join-Path $root 'build\pyi-dist'
# adb servers started from a previous staged build lock the folder
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like ($dist + '*') } | Stop-Process -Force
Start-Sleep -Milliseconds 500
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force -ErrorAction Stop }
Push-Location backend
& $py -m PyInstaller ..\packaging\MirrorHub.spec --noconfirm --distpath ..\build\pyi-dist --workpath ..\build\pyi-work 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { throw 'pyinstaller failed' }
Pop-Location

Step 'stage bundled tools'
$src = Join-Path $root 'tools\scrcpy\scrcpy-win64-v4.0'
$dst = Join-Path $dist 'MirrorHub\tools\scrcpy\scrcpy-win64-v4.0'
New-Item -ItemType Directory -Force $dst | Out-Null
foreach ($f in 'adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll','scrcpy.exe','scrcpy-server','SDL3.dll','avcodec-62.dll','avformat-62.dll','avutil-60.dll','swresample-6.dll','libusb-1.0.dll') {
  if (-not (Test-Path (Join-Path $src $f))) { throw "missing bundled tool $f in $src" }
  Copy-Item (Join-Path $src $f) $dst
}

if (-not $SkipSmoke) {
  Step 'frozen exe selftest'
  $out = & (Join-Path $dist 'MirrorHub\MirrorHub.exe') --selftest 2>&1 | Out-String
  ($out -split "`n") | Where-Object { $_ -match '^\[(PASS|FAIL)\]|SELFTEST' }
  if ($out -notmatch 'SELFTEST PASS') { throw 'frozen selftest failed' }
  $report.Add('frozen selftest PASS')
}

Step 'inno setup'
& $iscc packaging\Mirrorhub.iss 2>&1 | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) { throw 'iscc failed' }

$setup = Get-ChildItem dist\Mirrorhub-Setup-*.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$hash = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash
"$hash  $($setup.Name)" | Set-Content dist\SHA256SUMS.txt -Encoding ascii
$report.Add("installer: $($setup.Name) $([math]::Round($setup.Length/1MB,1)) MB sha256=$hash")
$report | Set-Content build\build-report.txt -Encoding utf8
Remove-Item $tmpData -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "`nDONE: $($setup.FullName)  ($([math]::Round($setup.Length/1MB,1)) MB)`nSHA256 $hash" -ForegroundColor Green
Pop-Location

