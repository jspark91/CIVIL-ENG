param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageRoot = Join-Path $root "outputs\naver_map_portable"
$releaseRoot = Join-Path $packageRoot "DxfMapViewer-python"
$zipPath = Join-Path $packageRoot "DxfMapViewer-python-$Version.zip"
$toolsRoot = Join-Path $releaseRoot "tools"
$depsRoot = Join-Path $releaseRoot "pydeps"

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
Remove-Item -LiteralPath $releaseRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $depsRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_webapp.py") -Destination $toolsRoot
Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_from_dxf.py") -Destination $toolsRoot
Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_icon.ico") -Destination $releaseRoot
Set-Content -LiteralPath (Join-Path $toolsRoot "__init__.py") -Value "" -Encoding ASCII

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

$cmd = @"
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\pydeps;%CD%"
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 "%CD%\tools\naver_map_webapp.py"
    goto :done
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "%CD%\tools\naver_map_webapp.py"
    goto :done
)
echo Python 3 is required for this no-EXE package.
echo Install Python from https://www.python.org/downloads/windows/
:done
pause
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "Run-DxfMapViewer.cmd") -Value $cmd -Encoding ASCII

$readme = @"
DXF Map Viewer $Version no-EXE package

This package contains no custom EXE. It runs through Python on the user's PC,
which is useful when security software deletes unsigned PyInstaller programs.

How to run:
1. Install Python 3.11 or newer if the PC does not already have it.
2. Double-click Run-DxfMapViewer.cmd.
3. When the browser opens, choose NAVER, Kakao, or Google.
4. Choose a DXF file.
5. For GRS80 Central Belt 2010 coordinates, choose EPSG:5186.
6. Enter the selected provider API key and convert.

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
- Keep the pydeps and tools folders next to Run-DxfMapViewer.cmd.
- ncpKeyId means NAVER Client ID, not Client Secret.
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

Write-Host "No-EXE portable folder: $releaseRoot"
Write-Host "No-EXE portable zip: $zipPath"
