from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYDEPS = ROOT / "pydeps"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if PYDEPS.exists():
    sys.path.insert(0, str(PYDEPS))

from tools import naver_map_from_dxf as naver_tool


def test_epsg_5179_false_origin_maps_to_projection_origin() -> None:
    lng, lat = naver_tool.transform_point(1_000_000.0, 2_000_000.0, "EPSG:5179", "xy", 1.0)

    assert abs(lng - 127.5) < 1.0e-8
    assert abs(lat - 38.0) < 1.0e-8


def test_epsg_5186_false_origin_maps_to_projection_origin() -> None:
    lng, lat = naver_tool.transform_point(200_000.0, 600_000.0, "EPSG:5186", "xy", 1.0)

    assert abs(lng - 127.0) < 1.0e-8
    assert abs(lat - 38.0) < 1.0e-8


def test_extracts_dxf_lwpolyline_and_builds_geojson(tmp_path: Path) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        import ezdxf

    dxf_path = tmp_path / "alignment.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [
            (1_000_000.0, 2_000_000.0, 0.0),
            (1_000_050.0, 2_000_000.0, 0.0),
            (1_000_100.0, 2_000_025.0, 0.0),
        ],
        format="xyb",
        dxfattribs={"layer": "ALIGN"},
    )
    doc.saveas(dxf_path)

    lines = naver_tool.extract_dxf_lines(dxf_path, {"ALIGN"}, max_sagitta=1.0)
    collection = naver_tool.build_feature_collection(dxf_path, lines, "EPSG:5179", "xy", 1.0)

    assert len(lines) == 2
    assert len(collection["features"]) == 2
    assert naver_tool.count_points(collection) == 4
    assert collection["features"][0]["geometry"]["coordinates"][0] == [127.5, 38.0]


def test_convert_dxf_to_naver_map_writes_outputs(tmp_path: Path) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        import ezdxf

    dxf_path = tmp_path / "alignment.dxf"
    output_dir = tmp_path / "out"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((1_000_000.0, 2_000_000.0), (1_000_050.0, 2_000_000.0), dxfattribs={"layer": "ALIGN"})
    doc.saveas(dxf_path)

    result = naver_tool.convert_dxf_to_naver_map(
        input_path=dxf_path,
        source_crs="EPSG:5179",
        layer_names={"ALIGN"},
        output_dir=output_dir,
        output_name="preview",
    )

    assert result.feature_count == 1
    assert result.point_count == 2
    assert result.geojson_path == output_dir / "preview.geojson"
    assert result.html_path == output_dir / "preview.html"
    assert result.geojson_path.exists()
    assert result.html_path.exists()


def test_render_html_supports_map_providers() -> None:
    collection = {
        "type": "FeatureCollection",
        "properties": {},
        "features": [
            {
                "type": "Feature",
                "properties": {"strokeColor": "#0f6bdc"},
                "geometry": {"type": "LineString", "coordinates": [[127.0, 38.0], [127.001, 38.0]]},
            }
        ],
    }

    naver_html = naver_tool.render_html(collection, "alignment.dxf", None, "naver")
    kakao_html = naver_tool.render_html(collection, "alignment.dxf", None, "kakao")
    google_html = naver_tool.render_html(collection, "alignment.dxf", None, "google")

    assert "oapi.map.naver.com" in naver_html
    assert "dapi.kakao.com" in kakao_html
    assert "maps.googleapis.com" in google_html
    assert "Roadview" in kakao_html
    assert "Street View" in google_html
