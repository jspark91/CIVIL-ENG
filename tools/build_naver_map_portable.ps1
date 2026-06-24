param(
    [string]$Version = "0.1.0",
    [ValidateSet("OneDir", "OneFile")]
    [string]$Mode = "OneDir"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageRoot = Join-Path $root "outputs\naver_map_portable"
$modeName = if ($Mode -eq "OneFile") { "onefile" } else { "folder" }
$distRoot = Join-Path $packageRoot "dist-$modeName"
$workRoot = Join-Path $packageRoot "build-$modeName"
$releaseName = if ($Mode -eq "OneFile") { "NaverMapDxfViewer" } else { "NaverMapDxfViewer-folder" }
$releaseRoot = Join-Path $packageRoot $releaseName
$zipPath = Join-Path $packageRoot "$releaseName-$Version.zip"
$pyinstallerMode = if ($Mode -eq "OneFile") { "--onefile" } else { "--onedir" }

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
Remove-Item -LiteralPath $distRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $releaseRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue

$env:PYTHONPATH = Join-Path $root "pydeps"

python -m PyInstaller `
    --noconfirm `
    --clean `
    $pyinstallerMode `
    --name "NaverMapDxfViewer" `
    --icon (Join-Path $root "tools\naver_map_icon.ico") `
    --paths (Join-Path $root "pydeps") `
    --hidden-import "tools.naver_map_from_dxf" `
    --distpath $distRoot `
    --workpath $workRoot `
    --specpath $packageRoot `
    (Join-Path $root "tools\naver_map_webapp.py")

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
if ($Mode -eq "OneFile") {
    Copy-Item -LiteralPath (Join-Path $distRoot "NaverMapDxfViewer.exe") -Destination $releaseRoot
} else {
    Copy-Item -Path (Join-Path $distRoot "NaverMapDxfViewer\*") -Destination $releaseRoot -Recurse
}
Copy-Item -LiteralPath (Join-Path $root "tools\naver_map_icon.ico") -Destination $releaseRoot

$readme = @"
DXF Map Viewer $Version ($Mode portable package)

How to run:
1. Double-click NaverMapDxfViewer.exe.
2. When the browser opens, choose NAVER, Kakao, or Google.
3. Choose a DXF file.
4. For GRS80 Central Belt 2010 coordinates, choose EPSG:5186.
5. Enter the selected provider API key.
6. Click the convert button.
7. In the generated map, use the roadview/street-view buttons.

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
- Do not double-click generated HTML files. Open maps through this app.
- Outputs are separated into outputs/naver_map, outputs/kakao_map, and outputs/google_map.
- ncpKeyId means NAVER Client ID, not Client Secret.
- Roadview/street-view only works where the selected provider has coverage.
- If security software deletes the executable, ask the administrator to allowlist this extracted folder.
- The folder package is less likely to be flagged than a one-file self-extracting package.
"@

Set-Content -LiteralPath (Join-Path $releaseRoot "README.txt") -Value $readme -Encoding UTF8

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

Write-Host "Portable folder: $releaseRoot"
Write-Host "Portable zip: $zipPath"
