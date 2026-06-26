# CIVIL-ENG

Civil engineering utilities.

## DXF Map Viewer

`tools/naver_map_webapp.py` converts AutoCAD DXF alignment linework in Korean
GRS80 coordinate systems to WGS84 GeoJSON and interactive map HTML previews for:

- NAVER Map
- Kakao Map
- Google Maps

Generated outputs are separated by provider:

- `outputs/naver_map`
- `outputs/kakao_map`
- `outputs/google_map`

For team distribution where users should not install Python, download:

- `releases/DxfMapViewer-team-0.1.0.zip`

That package includes a local Python runtime. Users only need to extract the ZIP
and double-click `Run-DxfMapViewer.cmd`.

For PCs that already have Python installed, a smaller no-EXE package is also
available:

- `releases/DxfMapViewer-python-0.1.0.zip`

Usage and API key setup:

- `docs/naver-map-dxf.md`

Quick local run from source:

```powershell
python -m pip install -r requirements.txt --target .\pydeps
$env:PYTHONPATH = ".\pydeps"
python .\tools\naver_map_webapp.py
```

Build the team package from source:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_dxf_map_team_portable.ps1
```
