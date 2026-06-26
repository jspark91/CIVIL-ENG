# DXF Alignment Map Preview

Use `tools/naver_map_from_dxf.py` to convert AutoCAD DXF alignment linework to
WGS84 GeoJSON and standalone NAVER, Kakao, or Google map HTML previews.

DWG is not parsed directly. Export the modelspace alignment to DXF first, then
run the converter.

## Command

For the GUI:

```powershell
python .\tools\naver_map_gui.py
```

You can also double-click:

```text
tools\Start-NaverMapDxfGui.cmd
```

The browser UI opens generated HTML through its built-in local server,
defaulting to:

```text
http://localhost:8000/<output>.html
```

Register these local URLs in each map provider's web/origin/referrer settings:

```text
http://localhost:8000
http://127.0.0.1:8000
```

Do not open the generated HTML as `file://...` when using web map APIs. Provider
keys usually check the browser origin/referrer, and `file://` pages can fail
authentication even with a valid key.

For the CLI:

```powershell
python .\tools\naver_map_from_dxf.py --provider naver --input .\path\alignment.dxf --crs EPSG:5179
```

The command writes to the provider folder:

- `outputs/naver_map/<input-name>.geojson`
- `outputs/naver_map/<input-name>.html`
- `outputs/kakao_map/<input-name>.*` when `--provider kakao`
- `outputs/google_map/<input-name>.*` when `--provider google`

Open the HTML in a browser and enter a NAVER Maps `ncpKeyId`, or pass the key at
generation time:

```powershell
python .\tools\naver_map_from_dxf.py --provider naver --input .\path\alignment.dxf --crs EPSG:5186 --api-key YOUR_NCP_KEY_ID
python .\tools\naver_map_from_dxf.py --provider kakao --input .\path\alignment.dxf --crs EPSG:5186 --api-key YOUR_KAKAO_JAVASCRIPT_KEY
python .\tools\naver_map_from_dxf.py --provider google --input .\path\alignment.dxf --crs EPSG:5186 --api-key YOUR_GOOGLE_MAPS_API_KEY
```

Generated HTML also accepts keys through the query string:

```text
alignment.html?ncpKeyId=YOUR_NCP_KEY_ID
alignment.html?appkey=YOUR_KAKAO_JAVASCRIPT_KEY
alignment.html?key=YOUR_GOOGLE_MAPS_API_KEY
```

## Roadview / Panorama

Generated map HTML includes roadview/street-view controls:

- NAVER uses `StreetLayer` and `Panorama`.
- Kakao uses `RoadviewOverlay`, `RoadviewClient`, and `Roadview`.
- Google uses `StreetViewService` and `StreetViewPanorama`.

Roadview only opens where the selected provider has coverage; the generated page
searches for a nearby panorama within roughly 300 m of the clicked location.

## Security Software

For sharing with other PCs, prefer the folder portable package:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_naver_map_portable.ps1 -Mode OneDir
```

The folder package avoids PyInstaller's one-file self-extraction behavior, which
is a common source of antivirus false positives. If a company security product
still deletes it, use the product's normal allowlist/quarantine-restore process
for the extracted folder or submit the EXE as a false positive. For wider
distribution, use code signing from a trusted certificate.

If the security product deletes all unsigned PyInstaller EXEs, build the no-EXE
package instead:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_naver_map_noexe_portable.ps1
```

That package starts the same app through `Run-NaverMapDxfViewer.cmd` and the
user's installed Python. It is less convenient because Python 3.11+ must be
installed on the target PC, but it avoids shipping a custom executable.

For team distribution where users should not install Python, build the
self-contained team package:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_dxf_map_team_portable.ps1
```

This writes `outputs/naver_map_portable/DxfMapViewer-team-0.1.0.zip`. Users only
need to extract the ZIP and run `Run-DxfMapViewer.cmd`; the package includes a
local Python runtime and the required DXF parsing dependencies.

## Coordinate Systems

Supported inputs:

- `EPSG:5179` Korea 2000 / Unified CS
- `EPSG:5181` Korea 2000 / Central Belt
- `EPSG:5185` Korea 2000 / West Belt 2010
- `EPSG:5186` Korea 2000 / Central Belt 2010
- `EPSG:5187` Korea 2000 / East Belt 2010
- `EPSG:5188` Korea 2000 / East Sea Belt 2010
- `EPSG:4326` WGS84 longitude/latitude

Default axis order is `xy`, meaning CAD X is easting/longitude and CAD Y is
northing/latitude. Use `--axis-order yx` if the source data is stored as
northing/easting.

If drawing units are millimeters but contain projected map coordinates, add:

```powershell
--unit-scale 0.001
```

## Layer Filtering

By default all supported modelspace linework is exported. Restrict output to one
or more alignment layers when the DXF contains other drawing objects:

```powershell
python .\tools\naver_map_from_dxf.py --input .\path\alignment.dxf --crs EPSG:5179 --layer ALIGN --layer CENTERLINE
```

Supported geometry: `LINE`, `ARC`, `LWPOLYLINE`, `POLYLINE`, `SPLINE`, and
`ELLIPSE`. Curves are flattened with `--max-sagitta`, defaulting to one drawing
unit.

## Verification

```powershell
python -m pytest .\tests\test_naver_map_from_dxf.py
```
