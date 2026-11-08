<#
 Installer smoke test (no phone needed). Installs silently to a temp folder, verifies, launches, uninstalls.
   powershell -ExecutionPolicy Bypass -File packaging\smoke_installer.ps1 [-Setup dist\Mirrorhub-Setup-1.0.0.exe]
 Uses a throw-away MIRRORHUB_DATA_DIR; real %APPDATA%\Mirrorhub is never touched.
 Exit code 0 = all checks passed.
#>
param([string]$Setup, [switch]$IsolatedProfile)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Setup) { $Setup = (Get-ChildItem (Join-Path $root 'dist\Mirrorhub-Setup-*.exe') | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName }
$results = New-Object System.Collections.Generic.List[object]
function Check($name, $ok, $detail = '') { $results.Add([pscustomobject]@{ check = $name; status = $(if ($ok) { 'PASS' } else { 'FAIL' }); detail = $detail }); Write-Host ("[{0}] {1} {2}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $name, $detail) }

$work = Join-Path $env:TEMP ("mh-smoke-" + [guid]::NewGuid().ToString('N'))
$inst = Join-Path $work 'Mirrorhub app'          # path with a space on purpose
$data = Join-Path $work 'userdata'
New-Item -ItemType Directory -Force $work, $data | Out-Null
$env:MIRRORHUB_DATA_DIR = $data
if ($IsolatedProfile) {
  # Approximate a first-run user: empty profile folders, no Python/Node on PATH, no MIRRORHUB_* overrides except the data dir.
  # (Not a clean OS: registry and machine-wide runtimes are the real ones.)
  $prof = Join-Path $work 'profile'
  New-Item -ItemType Directory -Force "$prof\AppData\Roaming", "$prof\AppData\Local\Temp" | Out-Null
  $env:USERPROFILE = $prof; $env:APPDATA = "$prof\AppData\Roaming"; $env:LOCALAPPDATA = "$prof\AppData\Local"
  $env:TEMP = "$prof\AppData\Local\Temp"; $env:TMP = $env:TEMP
  $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
  Remove-Item Env:MIRRORHUB_DATA_DIR
  $data = "$prof\AppData\Roaming\Mirrorhub"
  Check 'isolated profile active (no python/node on PATH)' (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command node -ErrorAction SilentlyContinue))
}
# sentinel to prove uninstall does not delete user data
Set-Content (Join-Path $data 'sentinel.txt') 'keep me'

# 1. silent install
$p = Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /DIR=`"$inst`" /LOG=`"$work\setup.log`" /TASKS=desktopicon" -Wait -PassThru
Check 'install exit code 0' ($p.ExitCode -eq 0) "exit=$($p.ExitCode)"
$exe = Join-Path $inst 'MirrorHub.exe'
Check 'MirrorHub.exe installed' (Test-Path $exe)
Check 'adb.exe installed' (Test-Path (Join-Path $inst 'tools\scrcpy\scrcpy-win64-v4.0\adb.exe'))
Check 'scrcpy-server installed' (Test-Path (Join-Path $inst 'tools\scrcpy\scrcpy-win64-v4.0\scrcpy-server'))
Check 'frontend bundled' ((Get-ChildItem $inst -Recurse -Filter index.html -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*frontend*dist*' }).Count -ge 1)
Check 'notices installed' (Test-Path (Join-Path $inst 'THIRD_PARTY_NOTICES.txt'))
Check 'uninstaller installed' (Test-Path (Join-Path $inst 'unins000.exe'))
$startMenu = Get-ChildItem (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') -Filter 'Mirrorhub*.lnk' -ErrorAction SilentlyContinue
Check 'start menu shortcut' ($null -ne $startMenu)

# 2. installed exe selftest (clean machine behaviour: no Python/Node on PATH is required by design)
$out = & $exe --selftest 2>&1 | Out-String
Check 'installed selftest' ($out -match 'SELFTEST PASS') (($out -split "`n" | Where-Object { $_ -match 'FAIL' }) -join '; ')
Check 'selftest wrote only to data dir' (Test-Path (Join-Path $data 'mirrorhub.db')) 'mirrorhub.db created in MIRRORHUB_DATA_DIR'
Check 'no data written inside install dir' (-not (Test-Path (Join-Path $inst 'mirrorhub.db')) -and -not (Test-Path (Join-Path $inst 'uploads')))

# 3. window launch
$w = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 12
$w.Refresh()
Check 'window opens' ((-not $w.HasExited) -and $w.MainWindowTitle -eq 'MirrorHub') "title='$($w.MainWindowTitle)'"
try { $h = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 5).Content; Check 'running backend answers /health' ($h -match 'MirrorHub') $h } catch { Check 'running backend answers /health' $false $_.Exception.Message }
# second launch must attach, not crash or start a second backend
$w2 = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 6
Check 'second instance attaches (no crash)' (-not $w2.HasExited)
Stop-Process -Id $w2.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $w.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "$inst*" } | Stop-Process -Force
Start-Sleep -Seconds 1

# 4. uninstall
$u = Start-Process -FilePath (Join-Path $inst 'unins000.exe') -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru
Check 'uninstall exit code 0' ($u.ExitCode -eq 0) "exit=$($u.ExitCode)"
Start-Sleep -Seconds 2
Check 'exe removed' (-not (Test-Path $exe))
Check 'user data preserved' ((Test-Path (Join-Path $data 'sentinel.txt')) -and (Test-Path (Join-Path $data 'mirrorhub.db')))
$startMenu = Get-ChildItem (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') -Filter 'Mirrorhub*.lnk' -ErrorAction SilentlyContinue
Check 'start menu shortcut removed' ($null -eq $startMenu)

$results | ConvertTo-Json | Set-Content (Join-Path $root 'build\installer-smoke.json') -Encoding utf8
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
$fail = ($results | Where-Object status -eq 'FAIL').Count
Write-Host "`nSMOKE: $($results.Count - $fail)/$($results.Count) passed"
exit $(if ($fail) { 1 } else { 0 })
