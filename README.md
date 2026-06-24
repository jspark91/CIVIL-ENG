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

For a no-EXE portable package, download:

- `releases/DxfMapViewer-python-0.1.0.zip`

That package runs through Python with `Run-DxfMapViewer.cmd`, which is useful
when company security software deletes unsigned PyInstaller executables.

Usage and API key setup:

- `docs/naver-map-dxf.md`

Quick local run from source:

```powershell
python -m pip install -r requirements.txt --target .\pydeps
$env:PYTHONPATH = ".\pydeps"
python .\tools\naver_map_webapp.py
```
