param(
    [string]$Version = "0.1.0",
    [string]$PythonRoot = ""
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $PythonRoot) {
    $PythonRoot = Split-Path -Parent (Get-Command python).Source
}
$PythonRoot = (Resolve-Path -LiteralPath $PythonRoot).Path

$packageRoot = Join-Path $root "outputs\naver_map_portable"
$releaseRoot = Join-Path $packageRoot "DxfMapViewer-team"
$zipPath = Join-Path $packageRoot "DxfMapViewer-team-$Version.zip"
$toolsRoot = Join-Path $releaseRoot "tools"
$depsRoot = Join-Path $releaseRoot "pydeps"
$runtimeRoot = Join-Path $releaseRoot "python"

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
Remove-Item -LiteralPath $releaseRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $depsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_webapp.py") -Destination $toolsRoot
Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_from_dxf.py") -Destination $toolsRoot
Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_icon.ico") -Destination $releaseRoot
Set-Content -LiteralPath (Join-Path $toolsRoot "__init__.py") -Value "" -Encoding ASCII

$runtimeFiles = @(
    "python.exe",
    "pythonw.exe",
    "python3.dll",
    "python312.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "LICENSE.txt"
)

foreach ($file in $runtimeFiles) {
    $source = Join-Path $PythonRoot $file
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $runtimeRoot
    }
}

Copy-Item -LiteralPath (Join-Path $PythonRoot "DLLs") -Destination $runtimeRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PythonRoot "Lib") -Destination $runtimeRoot -Recurse

$skipRuntimeDirs = @(
    "site-packages",
    "test",
    "tkinter",
    "idlelib",
    "ensurepip",
    "venv",
    "turtledemo",
    "__pycache__"
)
foreach ($skip in $skipRuntimeDirs) {
    Get-ChildItem -Path (Join-Path $runtimeRoot "Lib") -Directory -Filter $skip -Recurse -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
}

$deps = @(
    "ezdxf",
    "ezdxf-1.4.3.dist-info",
    "fontTools",
    "fonttools-4.62.1.dist-info",
    "numpy",
    "numpy-2.4.3.dist-info",
    "numpy.libs",
    "pyparsing",
    "pyparsing-3.3.2.dist-info",
    "typing_extensions.py",
    "typing_extensions-4.15.0.dist-info"
)

foreach ($dep in $deps) {
    $source = Join-Path $root "pydeps\$dep"
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing dependency: $source"
    }
    Copy-Item -LiteralPath $source -Destination $depsRoot -Recurse
}

$runCmd = @"
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME=%CD%\python"
set "PYTHONPATH=%CD%\pydeps;%CD%"
set "PYTHONNOUSERSITE=1"
"%CD%\python\python.exe" "%CD%\tools\naver_map_webapp.py"
pause
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "Run-DxfMapViewer.cmd") -Value $runCmd -Encoding ASCII

$shortcutCmd = @"
@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut((Join-Path $desktop 'DXF Map Viewer.lnk')); $s.TargetPath=(Join-Path (Get-Location) 'Run-DxfMapViewer.cmd'); $s.WorkingDirectory=(Get-Location).Path; $s.IconLocation=(Join-Path (Get-Location) 'naver_map_icon.ico'); $s.Save()"
echo Desktop shortcut created.
pause
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "Create-Desktop-Shortcut.cmd") -Value $shortcutCmd -Encoding ASCII

$readme = @"
DXF Map Viewer $Version team portable package

This package does not require users to install Python.
It includes a local Python runtime and runs with Run-DxfMapViewer.cmd.

How to run:
1. Extract this ZIP to a normal folder, for example C:\DxfMapViewer.
2. Double-click Run-DxfMapViewer.cmd.
3. When the browser opens, choose NAVER, Kakao, or Google.
4. Choose a DXF file.
5. For GRS80 Central Belt 2010 coordinates, choose EPSG:5186.
6. Enter the selected provider API key and convert.

Optional:
- Double-click Create-Desktop-Shortcut.cmd to add a desktop shortcut.

Provider key settings:
- NAVER: enable Maps API / Web Dynamic Map and use ncpKeyId.
- Kakao: use the JavaScript key for Kakao Maps.
- Google: enable Maps JavaScript API and use a browser API key.
- Register these local web/origin/referrer URLs where required:
  http://localhost:8787
  http://127.0.0.1:8787
- If port 8787 is already in use, the app automatically uses the next available port.
  Add that browser port to the provider key settings as well.

Notes:
- DWG is not read directly. Export DWG to DXF from AutoCAD first.
- Outputs are separated into outputs/naver_map, outputs/kakao_map, and outputs/google_map.
- Keep all folders next to Run-DxfMapViewer.cmd.
- If security software blocks python.exe, allowlist this extracted folder.
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "README.txt") -Value $readme -Encoding UTF8

Get-ChildItem -Path $releaseRoot -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Compress-Archive -LiteralPath $releaseRoot -DestinationPath $zipPath -Force
        break
    } catch {
        if ($attempt -eq 5) {
            throw
        }
        Write-Warning "Compress-Archive failed on attempt $attempt. Retrying after file locks settle."
        Start-Sleep -Seconds 2
    }
}

Write-Host "Team portable folder: $releaseRoot"
Write-Host "Team portable zip: $zipPath"
