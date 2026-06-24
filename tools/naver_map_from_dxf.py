from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = app_root()
PYDEPS = ROOT / "pydeps"
if PYDEPS.exists():
    sys.path.insert(0, str(PYDEPS))


GRS80_A = 6378137.0
GRS80_INV_F = 298.257222101


@dataclass(frozen=True)
class TmProjection:
    code: str
    name: str
    lat_origin_deg: float
    lon_origin_deg: float
    scale: float
    false_easting: float
    false_northing: float


@dataclass(frozen=True)
class LineFeature:
    layer: str
    source_type: str
    handle: str | None
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ConversionResult:
    input_path: Path
    geojson_path: Path
    html_path: Path
    feature_count: int
    point_count: int
    inside_korea_count: int
    total_coordinate_count: int


PROJECTIONS: dict[str, TmProjection] = {
    "EPSG:5179": TmProjection("EPSG:5179", "Korea 2000 / Unified CS", 38.0, 127.5, 0.9996, 1_000_000.0, 2_000_000.0),
    "EPSG:5181": TmProjection("EPSG:5181", "Korea 2000 / Central Belt", 38.0, 127.0, 1.0, 200_000.0, 500_000.0),
    "EPSG:5185": TmProjection("EPSG:5185", "Korea 2000 / West Belt 2010", 38.0, 125.0, 1.0, 200_000.0, 600_000.0),
    "EPSG:5186": TmProjection("EPSG:5186", "Korea 2000 / Central Belt 2010", 38.0, 127.0, 1.0, 200_000.0, 600_000.0),
    "EPSG:5187": TmProjection("EPSG:5187", "Korea 2000 / East Belt 2010", 38.0, 129.0, 1.0, 200_000.0, 600_000.0),
    "EPSG:5188": TmProjection("EPSG:5188", "Korea 2000 / East Sea Belt 2010", 38.0, 131.0, 1.0, 200_000.0, 600_000.0),
}


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    html, body, #map {
      width: 100%;
      height: 100%;
      margin: 0;
    }

    body {
      font-family: Arial, sans-serif;
      color: #17202a;
      background: #f6f7f9;
    }

    .topbar {
      position: fixed;
      left: 16px;
      top: 16px;
      z-index: 10;
      display: flex;
      align-items: center;
      gap: 12px;
      max-width: calc(100vw - 32px);
      padding: 10px 12px;
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid rgba(23, 32, 42, 0.16);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(23, 32, 42, 0.18);
    }

    .name {
      max-width: 36vw;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 14px;
      font-weight: 700;
    }

    .meta {
      font-size: 12px;
      color: #4b5563;
      white-space: nowrap;
    }

    .tools {
      display: flex;
      gap: 6px;
      margin-left: auto;
    }

    .tools button,
    .pano-header button {
      min-height: 30px;
      padding: 0 10px;
      border: 0;
      border-radius: 6px;
      color: #ffffff;
      background: #0f6bdc;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }

    .key-panel {
      position: fixed;
      left: 50%;
      top: 50%;
      z-index: 20;
      display: none;
      width: min(420px, calc(100vw - 32px));
      transform: translate(-50%, -50%);
      padding: 18px;
      background: #ffffff;
      border: 1px solid rgba(23, 32, 42, 0.18);
      border-radius: 8px;
      box-shadow: 0 16px 40px rgba(23, 32, 42, 0.22);
    }

    .key-panel.visible {
      display: block;
    }

    .key-panel label {
      display: block;
      margin-bottom: 8px;
      font-size: 13px;
      font-weight: 700;
    }

    .key-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
    }

    .key-row input {
      min-width: 0;
      height: 36px;
      padding: 0 10px;
      border: 1px solid #bac2cf;
      border-radius: 6px;
      font-size: 13px;
    }

    .key-row button {
      height: 38px;
      padding: 0 14px;
      border: 0;
      border-radius: 6px;
      color: #ffffff;
      background: #0f6bdc;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }

    .status {
      margin-top: 10px;
      min-height: 18px;
      font-size: 12px;
      color: #6b1111;
    }

    .pano-panel {
      position: fixed;
      right: 16px;
      top: 78px;
      bottom: 16px;
      z-index: 12;
      display: none;
      width: min(540px, calc(46vw - 16px));
      min-width: 360px;
      overflow: hidden;
      background: #ffffff;
      border: 1px solid rgba(23, 32, 42, 0.18);
      border-radius: 8px;
      box-shadow: 0 16px 40px rgba(23, 32, 42, 0.22);
    }

    .pano-panel.visible {
      display: grid;
      grid-template-rows: 42px minmax(0, 1fr) auto;
    }

    .pano-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 10px;
      border-bottom: 1px solid #d7dce5;
      font-size: 13px;
      font-weight: 700;
    }

    #pano {
      min-height: 0;
    }

    .pano-status {
      padding: 8px 10px;
      border-top: 1px solid #d7dce5;
      font-size: 12px;
      color: #4b5563;
      background: #f7f8fa;
    }

    @media (max-width: 720px) {
      .topbar {
        right: 12px;
        left: 12px;
        top: 12px;
        display: grid;
      }

      .name {
        max-width: none;
      }

      .tools {
        margin-left: 0;
      }

      .pano-panel {
        left: 12px;
        right: 12px;
        top: auto;
        bottom: 12px;
        width: auto;
        min-width: 0;
        height: 46vh;
      }
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="topbar">
    <div class="name">__TITLE__</div>
    <div class="meta">__META__</div>
    <div class="tools">
      <button id="streetButton" type="button">거리뷰 표시</button>
      <button id="panoButton" type="button">로드뷰 열기</button>
    </div>
  </div>
  <div id="keyPanel" class="key-panel">
    <label for="apiKey">NAVER ncpKeyId</label>
    <div class="key-row">
      <input id="apiKey" type="password" autocomplete="off" placeholder="ncpKeyId">
      <button id="loadButton" type="button">Load</button>
    </div>
    <div id="status" class="status"></div>
  </div>
  <div id="panoPanel" class="pano-panel">
    <div class="pano-header">
      <span>로드뷰</span>
      <button id="closePanoButton" type="button">닫기</button>
    </div>
    <div id="pano"></div>
    <div id="panoStatus" class="pano-status">거리뷰 표시를 켜고 지도에서 지점을 클릭하세요.</div>
  </div>
  <script>
    const DEFAULT_API_KEY = __DEFAULT_API_KEY__;
    const COLLECTION = __GEOJSON__;
    let mapInstance = null;
    let streetLayer = null;
    let streetLayerEnabled = false;
    let panorama = null;
    let roadviewMarker = null;

    function allCoordinates() {
      const coords = [];
      for (const feature of COLLECTION.features) {
        for (const point of feature.geometry.coordinates) {
          coords.push(point);
        }
      }
      return coords;
    }

    function showStatus(message) {
      const status = document.getElementById("status");
      if (status) {
        status.textContent = message;
      }
    }

    function showKeyPanel() {
      document.getElementById("keyPanel").classList.add("visible");
    }

    function hideKeyPanel() {
      document.getElementById("keyPanel").classList.remove("visible");
    }

    window.navermap_authFailure = function () {
      showKeyPanel();
      showStatus("NAVER Maps authentication failed. Check ncpKeyId, Web Dynamic Map selection, and Web service URL.");
    };

    function loadApi(key) {
      if (!key) {
        showKeyPanel();
        return;
      }

      if (window.location.protocol === "file:") {
        showKeyPanel();
        showStatus("Open this page through http://localhost, not file://. Use the GUI HTML open button.");
        return;
      }

      localStorage.setItem("naverMapNcpKeyId", key);
      window.__naverMapLoaded = false;
      const script = document.createElement("script");
      script.src = "https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=" + encodeURIComponent(key) + "&submodules=panorama&callback=initMap";
      script.async = true;
      script.onerror = function () {
        showKeyPanel();
        showStatus("NAVER map script failed to load. Check internet access and the ncpKeyId.");
      };
      document.head.appendChild(script);

      window.setTimeout(function () {
        if (!window.__naverMapLoaded) {
          showKeyPanel();
          showStatus("NAVER map did not start. Check Web service URL: " + window.location.origin);
        }
      }, 8000);
    }

    window.initMap = function initMap() {
      try {
        window.__naverMapLoaded = true;
        hideKeyPanel();
        const coords = allCoordinates();
        if (coords.length === 0) {
          showKeyPanel();
          showStatus("No coordinates were generated.");
          return;
        }

        const lngs = coords.map((point) => point[0]);
        const lats = coords.map((point) => point[1]);
        const minLng = Math.min.apply(null, lngs);
        const maxLng = Math.max.apply(null, lngs);
        const minLat = Math.min.apply(null, lats);
        const maxLat = Math.max.apply(null, lats);
        const center = new naver.maps.LatLng((minLat + maxLat) / 2, (minLng + maxLng) / 2);

        const map = new naver.maps.Map("map", {
          center: center,
          zoom: 15,
          mapTypeControl: true,
          scaleControl: true,
          zoomControl: true
        });
        mapInstance = map;

        for (const feature of COLLECTION.features) {
          const path = feature.geometry.coordinates.map((point) => new naver.maps.LatLng(point[1], point[0]));
          new naver.maps.Polyline({
            map: map,
            path: path,
            strokeColor: feature.properties.strokeColor || "#0f6bdc",
            strokeOpacity: 0.92,
            strokeWeight: 5,
            strokeLineCap: "round",
            strokeLineJoin: "round",
            clickable: true
          });
        }

        const bounds = new naver.maps.LatLngBounds(
          new naver.maps.LatLng(minLat, minLng),
          new naver.maps.LatLng(maxLat, maxLng)
        );
        map.fitBounds(bounds, { top: 80, right: 80, bottom: 80, left: 80 });
        setupRoadview(map);
      } catch (error) {
        showKeyPanel();
        showStatus("Map render failed: " + (error && error.message ? error.message : error));
      }
    };

    function setupRoadview(map) {
      naver.maps.Event.addListener(map, "click", function (event) {
        if (streetLayerEnabled) {
          openRoadview(event.coord);
        }
      });
    }

    function setPanoStatus(message) {
      document.getElementById("panoStatus").textContent = message;
    }

    function toggleStreetLayer(force) {
      if (!mapInstance) {
        return;
      }

      if (!streetLayer) {
        streetLayer = new naver.maps.StreetLayer();
      }

      streetLayerEnabled = typeof force === "boolean" ? force : !streetLayerEnabled;
      streetLayer.setMap(streetLayerEnabled ? mapInstance : null);
      document.getElementById("streetButton").textContent = streetLayerEnabled ? "거리뷰 끄기" : "거리뷰 표시";
      setPanoStatus(streetLayerEnabled ? "파란 거리뷰 가능 도로를 클릭하세요." : "거리뷰 표시를 켜고 지도에서 지점을 클릭하세요.");
    }

    function openRoadview(position) {
      if (!mapInstance || !position) {
        return;
      }

      document.getElementById("panoPanel").classList.add("visible");
      if (!roadviewMarker) {
        roadviewMarker = new naver.maps.Marker({ map: mapInstance, position: position });
      } else {
        roadviewMarker.setPosition(position);
      }

      if (!panorama) {
        panorama = new naver.maps.Panorama("pano", {
          position: position,
          pov: { pan: 0, tilt: 0, fov: 100 }
        });
        naver.maps.Event.addListener(panorama, "pano_status", function (status) {
          setPanoStatus(status === "OK" ? "로드뷰 표시 중" : "주변 300m 안에 로드뷰가 없습니다.");
        });
        naver.maps.Event.addListener(panorama, "pano_changed", function () {
          const location = panorama.getLocation();
          if (location && location.address) {
            setPanoStatus(location.address + (location.photodate ? " / " + location.photodate : ""));
          }
        });
      } else {
        panorama.setPosition(position);
      }
    }

    function closeRoadview() {
      document.getElementById("panoPanel").classList.remove("visible");
    }

    document.getElementById("loadButton").addEventListener("click", function () {
      loadApi(document.getElementById("apiKey").value.trim());
    });

    document.getElementById("apiKey").addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        loadApi(event.target.value.trim());
      }
    });

    document.getElementById("streetButton").addEventListener("click", function () {
      toggleStreetLayer();
    });

    document.getElementById("panoButton").addEventListener("click", function () {
      if (mapInstance) {
        toggleStreetLayer(true);
        openRoadview(mapInstance.getCenter());
      }
    });

    document.getElementById("closePanoButton").addEventListener("click", closeRoadview);

    const params = new URLSearchParams(window.location.search);
    loadApi(params.get("ncpKeyId") || DEFAULT_API_KEY || localStorage.getItem("naverMapNcpKeyId") || "");
  </script>
</body>
</html>
"""

KAKAO_HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    html, body, #map {
      width: 100%;
      height: 100%;
      margin: 0;
      font-family: Arial, sans-serif;
    }

    .topbar {
      position: absolute;
      z-index: 10;
      top: 16px;
      left: 16px;
      right: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      border: 1px solid rgba(17, 24, 39, 0.16);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.94);
      box-shadow: 0 12px 30px rgba(17, 24, 39, 0.18);
    }

    .name {
      font-weight: 700;
      color: #1f2937;
      max-width: 44vw;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .meta {
      color: #4b5563;
      font-size: 13px;
    }

    .tools {
      display: flex;
      gap: 8px;
      margin-left: auto;
      flex-wrap: wrap;
    }

    button {
      min-height: 34px;
      padding: 0 12px;
      border: 0;
      border-radius: 6px;
      color: #ffffff;
      background: #2563eb;
      font-weight: 700;
      cursor: pointer;
    }

    .key-panel {
      display: none;
      position: absolute;
      z-index: 20;
      top: 50%;
      left: 50%;
      width: min(520px, calc(100vw - 48px));
      transform: translate(-50%, -50%);
      padding: 20px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 22px 55px rgba(17, 24, 39, 0.22);
    }

    .key-panel.visible {
      display: block;
    }

    .key-panel label {
      display: block;
      margin-bottom: 8px;
      font-weight: 700;
      color: #1f2937;
    }

    .key-row {
      display: flex;
      gap: 8px;
    }

    .key-row input {
      flex: 1;
      min-width: 0;
      height: 36px;
      padding: 0 10px;
      border: 1px solid #b9c2cf;
      border-radius: 6px;
    }

    .status {
      margin-top: 10px;
      font-size: 12px;
      color: #4b5563;
    }

    .roadview-panel {
      display: none;
      position: absolute;
      z-index: 11;
      right: 16px;
      top: 88px;
      width: min(460px, calc(100vw - 32px));
      height: min(520px, calc(100vh - 112px));
      min-height: 300px;
      border: 1px solid rgba(17, 24, 39, 0.18);
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
      box-shadow: 0 14px 36px rgba(17, 24, 39, 0.24);
    }

    .roadview-panel.visible {
      display: grid;
      grid-template-rows: 42px minmax(0, 1fr) auto;
    }

    .roadview-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 10px 0 14px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 13px;
      font-weight: 700;
    }

    .roadview-header button {
      min-height: 28px;
      padding: 0 10px;
      background: #4b5563;
    }

    #roadview {
      min-height: 0;
    }

    .roadview-status {
      padding: 8px 10px;
      font-size: 12px;
      color: #4b5563;
      background: #f7f8fa;
    }

    @media (max-width: 720px) {
      .topbar {
        display: grid;
      }

      .name {
        max-width: none;
      }

      .tools {
        margin-left: 0;
      }

      .roadview-panel {
        left: 12px;
        right: 12px;
        top: auto;
        bottom: 12px;
        width: auto;
        min-width: 0;
        height: 46vh;
      }
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="topbar">
    <div class="name">__TITLE__</div>
    <div class="meta">__META__</div>
    <div class="tools">
      <button id="roadviewLayerButton" type="button">Roadview Roads</button>
      <button id="roadviewButton" type="button">Open Roadview</button>
    </div>
  </div>
  <div id="keyPanel" class="key-panel">
    <label for="apiKey">Kakao JavaScript key</label>
    <div class="key-row">
      <input id="apiKey" type="password" autocomplete="off" placeholder="JavaScript key">
      <button id="loadButton" type="button">Load</button>
    </div>
    <div id="status" class="status"></div>
  </div>
  <div id="roadviewPanel" class="roadview-panel">
    <div class="roadview-header">
      <span>Roadview</span>
      <button id="closeRoadviewButton" type="button">Close</button>
    </div>
    <div id="roadview"></div>
    <div id="roadviewStatus" class="roadview-status">Turn on roadview roads, then click a road.</div>
  </div>
  <script>
    const DEFAULT_API_KEY = __DEFAULT_API_KEY__;
    const COLLECTION = __GEOJSON__;
    let mapInstance = null;
    let roadviewOverlay = null;
    let roadviewOverlayVisible = false;
    let roadview = null;
    let roadviewClient = null;
    let roadviewMarker = null;

    function allCoordinates() {
      const coords = [];
      for (const feature of COLLECTION.features) {
        for (const point of feature.geometry.coordinates) {
          coords.push(point);
        }
      }
      return coords;
    }

    function showStatus(message) {
      const status = document.getElementById("status");
      if (status) {
        status.textContent = message;
      }
    }

    function showKeyPanel() {
      document.getElementById("keyPanel").classList.add("visible");
    }

    function hideKeyPanel() {
      document.getElementById("keyPanel").classList.remove("visible");
    }

    function setRoadviewStatus(message) {
      document.getElementById("roadviewStatus").textContent = message;
    }

    function loadApi(key) {
      if (!key) {
        showKeyPanel();
        return;
      }

      if (window.location.protocol === "file:") {
        showKeyPanel();
        showStatus("Open this page through http://localhost, not file://.");
        return;
      }

      localStorage.setItem("kakaoMapJavaScriptKey", key);
      const script = document.createElement("script");
      script.src = "https://dapi.kakao.com/v2/maps/sdk.js?appkey=" + encodeURIComponent(key) + "&autoload=false";
      script.async = true;
      script.onerror = function () {
        showKeyPanel();
        showStatus("Kakao map script failed to load. Check internet access and JavaScript key.");
      };
      script.onload = function () {
        kakao.maps.load(initMap);
      };
      document.head.appendChild(script);
    }

    function initMap() {
      try {
        hideKeyPanel();
        const coords = allCoordinates();
        if (coords.length === 0) {
          showKeyPanel();
          showStatus("No coordinates were generated.");
          return;
        }

        const lngs = coords.map((point) => point[0]);
        const lats = coords.map((point) => point[1]);
        const minLng = Math.min.apply(null, lngs);
        const maxLng = Math.max.apply(null, lngs);
        const minLat = Math.min.apply(null, lats);
        const maxLat = Math.max.apply(null, lats);
        const center = new kakao.maps.LatLng((minLat + maxLat) / 2, (minLng + maxLng) / 2);

        const map = new kakao.maps.Map(document.getElementById("map"), {
          center: center,
          level: 4
        });
        mapInstance = map;
        roadviewClient = new kakao.maps.RoadviewClient();

        for (const feature of COLLECTION.features) {
          const path = feature.geometry.coordinates.map((point) => new kakao.maps.LatLng(point[1], point[0]));
          new kakao.maps.Polyline({
            map: map,
            path: path,
            strokeWeight: 5,
            strokeColor: feature.properties.strokeColor || "#0f6bdc",
            strokeOpacity: 0.92,
            strokeStyle: "solid"
          });
        }

        const bounds = new kakao.maps.LatLngBounds();
        for (const point of coords) {
          bounds.extend(new kakao.maps.LatLng(point[1], point[0]));
        }
        map.setBounds(bounds);

        kakao.maps.event.addListener(map, "click", function (mouseEvent) {
          if (roadviewOverlayVisible) {
            openRoadview(mouseEvent.latLng);
          }
        });
      } catch (error) {
        showKeyPanel();
        showStatus("Map render failed: " + (error && error.message ? error.message : error));
      }
    }

    function toggleRoadviewLayer(force) {
      if (!mapInstance) {
        return;
      }

      if (!roadviewOverlay) {
        if (kakao.maps.RoadviewOverlay) {
          roadviewOverlay = new kakao.maps.RoadviewOverlay();
        }
      }
      roadviewOverlayVisible = typeof force === "boolean" ? force : !roadviewOverlayVisible;
      if (roadviewOverlay) {
        roadviewOverlay.setMap(roadviewOverlayVisible ? mapInstance : null);
      }
      document.getElementById("roadviewLayerButton").textContent = roadviewOverlayVisible ? "Hide Roadview Roads" : "Roadview Roads";
      setRoadviewStatus(roadviewOverlayVisible ? "Click a road or nearby point with roadview coverage." : "Turn on roadview roads, then click a road.");
    }

    function openRoadview(position) {
      if (!mapInstance || !roadviewClient || !position) {
        return;
      }

      document.getElementById("roadviewPanel").classList.add("visible");
      if (!roadview) {
        roadview = new kakao.maps.Roadview(document.getElementById("roadview"));
      }

      roadviewClient.getNearestPanoId(position, 300, function (panoId) {
        if (!panoId) {
          setRoadviewStatus("No roadview found within 300 m.");
          return;
        }

        roadview.setPanoId(panoId, position);
        setRoadviewStatus("Roadview loaded.");
        if (!roadviewMarker) {
          roadviewMarker = new kakao.maps.Marker({ map: mapInstance, position: position });
        } else {
          roadviewMarker.setPosition(position);
        }
      });
    }

    function closeRoadview() {
      document.getElementById("roadviewPanel").classList.remove("visible");
    }

    document.getElementById("loadButton").addEventListener("click", function () {
      loadApi(document.getElementById("apiKey").value.trim());
    });

    document.getElementById("apiKey").addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        loadApi(event.target.value.trim());
      }
    });

    document.getElementById("roadviewLayerButton").addEventListener("click", function () {
      toggleRoadviewLayer();
    });

    document.getElementById("roadviewButton").addEventListener("click", function () {
      if (mapInstance) {
        toggleRoadviewLayer(true);
        openRoadview(mapInstance.getCenter());
      }
    });

    document.getElementById("closeRoadviewButton").addEventListener("click", closeRoadview);

    const params = new URLSearchParams(window.location.search);
    loadApi(params.get("appkey") || params.get("apiKey") || DEFAULT_API_KEY || localStorage.getItem("kakaoMapJavaScriptKey") || "");
  </script>
</body>
</html>
"""

GOOGLE_HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    html, body, #map {
      width: 100%;
      height: 100%;
      margin: 0;
      font-family: Arial, sans-serif;
    }

    .topbar {
      position: absolute;
      z-index: 10;
      top: 16px;
      left: 16px;
      right: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      border: 1px solid rgba(17, 24, 39, 0.16);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.94);
      box-shadow: 0 12px 30px rgba(17, 24, 39, 0.18);
    }

    .name {
      font-weight: 700;
      color: #1f2937;
      max-width: 44vw;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .meta {
      color: #4b5563;
      font-size: 13px;
    }

    .tools {
      display: flex;
      gap: 8px;
      margin-left: auto;
      flex-wrap: wrap;
    }

    button {
      min-height: 34px;
      padding: 0 12px;
      border: 0;
      border-radius: 6px;
      color: #ffffff;
      background: #2563eb;
      font-weight: 700;
      cursor: pointer;
    }

    .key-panel {
      display: none;
      position: absolute;
      z-index: 20;
      top: 50%;
      left: 50%;
      width: min(520px, calc(100vw - 48px));
      transform: translate(-50%, -50%);
      padding: 20px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 22px 55px rgba(17, 24, 39, 0.22);
    }

    .key-panel.visible {
      display: block;
    }

    .key-panel label {
      display: block;
      margin-bottom: 8px;
      font-weight: 700;
      color: #1f2937;
    }

    .key-row {
      display: flex;
      gap: 8px;
    }

    .key-row input {
      flex: 1;
      min-width: 0;
      height: 36px;
      padding: 0 10px;
      border: 1px solid #b9c2cf;
      border-radius: 6px;
    }

    .status {
      margin-top: 10px;
      font-size: 12px;
      color: #4b5563;
    }

    .streetview-panel {
      display: none;
      position: absolute;
      z-index: 11;
      right: 16px;
      top: 88px;
      width: min(460px, calc(100vw - 32px));
      height: min(520px, calc(100vh - 112px));
      min-height: 300px;
      border: 1px solid rgba(17, 24, 39, 0.18);
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
      box-shadow: 0 14px 36px rgba(17, 24, 39, 0.24);
    }

    .streetview-panel.visible {
      display: grid;
      grid-template-rows: 42px minmax(0, 1fr) auto;
    }

    .streetview-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 10px 0 14px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 13px;
      font-weight: 700;
    }

    .streetview-header button {
      min-height: 28px;
      padding: 0 10px;
      background: #4b5563;
    }

    #streetview {
      min-height: 0;
    }

    .streetview-status {
      padding: 8px 10px;
      font-size: 12px;
      color: #4b5563;
      background: #f7f8fa;
    }

    @media (max-width: 720px) {
      .topbar {
        display: grid;
      }

      .name {
        max-width: none;
      }

      .tools {
        margin-left: 0;
      }

      .streetview-panel {
        left: 12px;
        right: 12px;
        top: auto;
        bottom: 12px;
        width: auto;
        min-width: 0;
        height: 46vh;
      }
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="topbar">
    <div class="name">__TITLE__</div>
    <div class="meta">__META__</div>
    <div class="tools">
      <button id="coverageButton" type="button">Street View Roads</button>
      <button id="streetviewButton" type="button">Open Street View</button>
    </div>
  </div>
  <div id="keyPanel" class="key-panel">
    <label for="apiKey">Google Maps API key</label>
    <div class="key-row">
      <input id="apiKey" type="password" autocomplete="off" placeholder="API key">
      <button id="loadButton" type="button">Load</button>
    </div>
    <div id="status" class="status"></div>
  </div>
  <div id="streetviewPanel" class="streetview-panel">
    <div class="streetview-header">
      <span>Street View</span>
      <button id="closeStreetviewButton" type="button">Close</button>
    </div>
    <div id="streetview"></div>
    <div id="streetviewStatus" class="streetview-status">Turn on Street View roads, then click a road.</div>
  </div>
  <script>
    const DEFAULT_API_KEY = __DEFAULT_API_KEY__;
    const COLLECTION = __GEOJSON__;
    let mapInstance = null;
    let streetViewLayer = null;
    let streetViewLayerVisible = false;
    let streetViewService = null;
    let streetViewPanorama = null;
    let streetViewMarker = null;

    function allCoordinates() {
      const coords = [];
      for (const feature of COLLECTION.features) {
        for (const point of feature.geometry.coordinates) {
          coords.push(point);
        }
      }
      return coords;
    }

    function showStatus(message) {
      const status = document.getElementById("status");
      if (status) {
        status.textContent = message;
      }
    }

    function showKeyPanel() {
      document.getElementById("keyPanel").classList.add("visible");
    }

    function hideKeyPanel() {
      document.getElementById("keyPanel").classList.remove("visible");
    }

    function setStreetviewStatus(message) {
      document.getElementById("streetviewStatus").textContent = message;
    }

    function loadApi(key) {
      if (!key) {
        showKeyPanel();
        return;
      }

      if (window.location.protocol === "file:") {
        showKeyPanel();
        showStatus("Open this page through http://localhost, not file://.");
        return;
      }

      localStorage.setItem("googleMapsApiKey", key);
      window.initGoogleMap = initMap;
      const script = document.createElement("script");
      script.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(key) + "&callback=initGoogleMap";
      script.async = true;
      script.defer = true;
      script.onerror = function () {
        showKeyPanel();
        showStatus("Google Maps script failed to load. Check internet access and API key.");
      };
      document.head.appendChild(script);
    }

    function initMap() {
      try {
        hideKeyPanel();
        const coords = allCoordinates();
        if (coords.length === 0) {
          showKeyPanel();
          showStatus("No coordinates were generated.");
          return;
        }

        const lngs = coords.map((point) => point[0]);
        const lats = coords.map((point) => point[1]);
        const minLng = Math.min.apply(null, lngs);
        const maxLng = Math.max.apply(null, lngs);
        const minLat = Math.min.apply(null, lats);
        const maxLat = Math.max.apply(null, lats);
        const center = { lat: (minLat + maxLat) / 2, lng: (minLng + maxLng) / 2 };

        const map = new google.maps.Map(document.getElementById("map"), {
          center: center,
          zoom: 15,
          mapTypeControl: true,
          scaleControl: true,
          streetViewControl: true
        });
        mapInstance = map;
        streetViewService = new google.maps.StreetViewService();

        const bounds = new google.maps.LatLngBounds();
        for (const feature of COLLECTION.features) {
          const path = feature.geometry.coordinates.map((point) => ({ lat: point[1], lng: point[0] }));
          new google.maps.Polyline({
            map: map,
            path: path,
            strokeColor: feature.properties.strokeColor || "#0f6bdc",
            strokeOpacity: 0.92,
            strokeWeight: 5
          });
          for (const point of path) {
            bounds.extend(point);
          }
        }
        map.fitBounds(bounds, 80);

        map.addListener("click", function (event) {
          if (streetViewLayerVisible) {
            openStreetView(event.latLng);
          }
        });
      } catch (error) {
        showKeyPanel();
        showStatus("Map render failed: " + (error && error.message ? error.message : error));
      }
    }

    function toggleStreetViewLayer(force) {
      if (!mapInstance) {
        return;
      }

      if (!streetViewLayer) {
        if (google.maps.StreetViewCoverageLayer) {
          streetViewLayer = new google.maps.StreetViewCoverageLayer();
        }
      }
      streetViewLayerVisible = typeof force === "boolean" ? force : !streetViewLayerVisible;
      if (streetViewLayer) {
        streetViewLayer.setMap(streetViewLayerVisible ? mapInstance : null);
      }
      document.getElementById("coverageButton").textContent = streetViewLayerVisible ? "Hide Street View Roads" : "Street View Roads";
      setStreetviewStatus(streetViewLayerVisible ? "Click a road or nearby point with Street View coverage." : "Turn on Street View roads, then click a road.");
    }

    function openStreetView(position) {
      if (!mapInstance || !streetViewService || !position) {
        return;
      }

      document.getElementById("streetviewPanel").classList.add("visible");
      const request = { location: position, radius: 300 };
      streetViewService.getPanorama(request, function (data, status) {
        if (status !== "OK" || !data || !data.location) {
          setStreetviewStatus("No Street View found within 300 m.");
          return;
        }

        if (!streetViewPanorama) {
          streetViewPanorama = new google.maps.StreetViewPanorama(document.getElementById("streetview"), {
            pov: { heading: 0, pitch: 0 },
            zoom: 1
          });
        }

        streetViewPanorama.setPano(data.location.pano);
        streetViewPanorama.setVisible(true);
        setStreetviewStatus(data.location.description || "Street View loaded.");

        if (!streetViewMarker) {
          streetViewMarker = new google.maps.Marker({ map: mapInstance, position: data.location.latLng });
        } else {
          streetViewMarker.setPosition(data.location.latLng);
        }
      });
    }

    function closeStreetView() {
      document.getElementById("streetviewPanel").classList.remove("visible");
    }

    document.getElementById("loadButton").addEventListener("click", function () {
      loadApi(document.getElementById("apiKey").value.trim());
    });

    document.getElementById("apiKey").addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        loadApi(event.target.value.trim());
      }
    });

    document.getElementById("coverageButton").addEventListener("click", function () {
      toggleStreetViewLayer();
    });

    document.getElementById("streetviewButton").addEventListener("click", function () {
      if (mapInstance) {
        toggleStreetViewLayer(true);
        openStreetView(mapInstance.getCenter());
      }
    });

    document.getElementById("closeStreetviewButton").addEventListener("click", closeStreetView);

    const params = new URLSearchParams(window.location.search);
    loadApi(params.get("key") || params.get("apiKey") || DEFAULT_API_KEY || localStorage.getItem("googleMapsApiKey") || "");
  </script>
</body>
</html>
"""

HTML_TEMPLATES = {
    "naver": HTML_TEMPLATE,
    "kakao": KAKAO_HTML_TEMPLATE,
    "google": GOOGLE_HTML_TEMPLATE,
}

PROVIDER_OUTPUT_DIRS = {
    "naver": "naver_map",
    "kakao": "kakao_map",
    "google": "google_map",
}


def normalize_crs(value: str) -> str:
    match = re.search(r"EPSG\s*:?\s*(\d+)", value, flags=re.IGNORECASE)
    if match:
        return f"EPSG:{match.group(1)}"

    normalized = value.strip().upper().replace(" ", "")
    if normalized.isdigit():
        normalized = f"EPSG:{normalized}"
    return normalized


def inverse_tm_to_wgs84(easting: float, northing: float, projection: TmProjection) -> tuple[float, float]:
    f = 1.0 / GRS80_INV_F
    e2 = f * (2.0 - f)
    e_prime2 = e2 / (1.0 - e2)
    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))

    m0 = meridional_arc(math.radians(projection.lat_origin_deg), e2)
    m = m0 + (northing - projection.false_northing) / projection.scale
    mu = m / (GRS80_A * (1.0 - e2 / 4.0 - 3.0 * e2**2 / 64.0 - 5.0 * e2**3 / 256.0))

    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1**4 / 512.0) * math.sin(8.0 * mu)
    )

    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    tan_phi1 = math.tan(phi1)
    n1 = GRS80_A / math.sqrt(1.0 - e2 * sin_phi1**2)
    r1 = GRS80_A * (1.0 - e2) / (1.0 - e2 * sin_phi1**2) ** 1.5
    t1 = tan_phi1**2
    c1 = e_prime2 * cos_phi1**2
    d = (easting - projection.false_easting) / (n1 * projection.scale)

    lat_rad = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * e_prime2) * d**4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1**2 - 252.0 * e_prime2 - 3.0 * c1**2) * d**6 / 720.0
    )
    lon_rad = math.radians(projection.lon_origin_deg) + (
        d
        - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1**2 + 8.0 * e_prime2 + 24.0 * t1**2) * d**5 / 120.0
    ) / cos_phi1

    return math.degrees(lon_rad), math.degrees(lat_rad)


def meridional_arc(phi: float, e2: float) -> float:
    return GRS80_A * (
        (1.0 - e2 / 4.0 - 3.0 * e2**2 / 64.0 - 5.0 * e2**3 / 256.0) * phi
        - (3.0 * e2 / 8.0 + 3.0 * e2**2 / 32.0 + 45.0 * e2**3 / 1024.0) * math.sin(2.0 * phi)
        + (15.0 * e2**2 / 256.0 + 45.0 * e2**3 / 1024.0) * math.sin(4.0 * phi)
        - (35.0 * e2**3 / 3072.0) * math.sin(6.0 * phi)
    )


def transform_point(
    x: float,
    y: float,
    source_crs: str,
    axis_order: str,
    unit_scale: float,
) -> tuple[float, float]:
    x *= unit_scale
    y *= unit_scale

    if axis_order == "yx":
        easting, northing = y, x
    else:
        easting, northing = x, y

    if source_crs == "EPSG:4326":
        return easting, northing

    projection = PROJECTIONS[source_crs]
    return inverse_tm_to_wgs84(easting, northing, projection)


def point2(value) -> tuple[float, float]:
    return float(value.x), float(value.y)


def sample_arc(entity, max_sagitta: float) -> list[tuple[float, float]]:
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    start = math.radians(float(entity.dxf.start_angle))
    end = math.radians(float(entity.dxf.end_angle))
    while end < start:
        end += math.tau

    sweep = end - start
    if sweep <= 0.0 or radius <= 0.0:
        return []

    if max_sagitta <= 0.0:
        segment_angle = math.radians(5.0)
    else:
        bounded = min(max(max_sagitta / radius, 0.0), 1.0)
        segment_angle = 2.0 * math.acos(max(0.0, 1.0 - bounded))
        if segment_angle <= 0.0:
            segment_angle = math.radians(5.0)

    segments = max(2, int(math.ceil(abs(sweep) / segment_angle)))
    return [
        (
            float(center.x) + radius * math.cos(start + sweep * index / segments),
            float(center.y) + radius * math.sin(start + sweep * index / segments),
        )
        for index in range(segments + 1)
    ]


def flatten_entity(entity, max_sagitta: float) -> list[list[tuple[float, float]]]:
    entity_type = entity.dxftype()

    if entity_type == "LINE":
        return [[point2(entity.dxf.start), point2(entity.dxf.end)]]

    if entity_type == "ARC":
        points = sample_arc(entity, max_sagitta)
        return [points] if len(points) >= 2 else []

    if entity_type in {"LWPOLYLINE", "POLYLINE"}:
        try:
            parts: list[list[tuple[float, float]]] = []
            for virtual_entity in entity.virtual_entities():
                parts.extend(flatten_entity(virtual_entity, max_sagitta))
            return parts
        except Exception:
            pass

    if entity_type in {"SPLINE", "ELLIPSE"}:
        try:
            points = [point2(point) for point in entity.flattening(max_sagitta)]
            return [points] if len(points) >= 2 else []
        except Exception:
            return []

    return []


def load_ezdxf_modules():
    with contextlib.redirect_stderr(io.StringIO()):
        import ezdxf
        from ezdxf.disassemble import recursive_decompose

    return ezdxf, recursive_decompose


def extract_dxf_lines(
    path: Path,
    layer_names: set[str] | None,
    max_sagitta: float,
) -> list[LineFeature]:
    ezdxf, recursive_decompose = load_ezdxf_modules()

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            doc = ezdxf.readfile(path)
    except ezdxf.DXFError as exc:
        raise SystemExit(f"Could not read DXF: {path} ({exc})") from exc

    features: list[LineFeature] = []
    for entity in recursive_decompose(doc.modelspace()):
        layer = str(getattr(entity.dxf, "layer", "0"))
        if layer_names is not None and layer.upper() not in layer_names:
            continue

        for points in flatten_entity(entity, max_sagitta):
            clean_points = drop_repeated_points(points)
            if len(clean_points) < 2:
                continue
            features.append(
                LineFeature(
                    layer=layer,
                    source_type=entity.dxftype(),
                    handle=getattr(entity.dxf, "handle", None),
                    points=tuple(clean_points),
                )
            )

    return features


def drop_repeated_points(points: Iterable[tuple[float, float]], tolerance: float = 1.0e-9) -> list[tuple[float, float]]:
    output: list[tuple[float, float]] = []
    last: tuple[float, float] | None = None
    for point in points:
        if last is None or abs(point[0] - last[0]) > tolerance or abs(point[1] - last[1]) > tolerance:
            output.append(point)
            last = point
    return output


def build_feature_collection(
    dxf_path: Path,
    lines: list[LineFeature],
    source_crs: str,
    axis_order: str,
    unit_scale: float,
) -> dict:
    features = []
    colors = ["#0f6bdc", "#d93025", "#188038", "#b26a00", "#7b1fa2", "#00838f"]

    for index, line in enumerate(lines):
        coordinates = []
        for x, y in line.points:
            lng, lat = transform_point(x, y, source_crs, axis_order, unit_scale)
            if math.isfinite(lng) and math.isfinite(lat):
                coordinates.append([round(lng, 8), round(lat, 8)])

        coordinates = drop_repeated_geojson_points(coordinates)
        if len(coordinates) < 2:
            continue

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "source": str(dxf_path),
                    "layer": line.layer,
                    "sourceType": line.source_type,
                    "handle": line.handle,
                    "pointCount": len(coordinates),
                    "strokeColor": colors[index % len(colors)],
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "properties": {
            "source": str(dxf_path),
            "sourceCrs": source_crs,
            "axisOrder": axis_order,
            "unitScale": unit_scale,
        },
        "features": features,
    }


def drop_repeated_geojson_points(points: Iterable[list[float]]) -> list[list[float]]:
    output: list[list[float]] = []
    last: list[float] | None = None
    for point in points:
        if last is None or point != last:
            output.append(point)
            last = point
    return output


def count_points(collection: dict) -> int:
    return sum(len(feature["geometry"]["coordinates"]) for feature in collection["features"])


def coordinates_in_korea(collection: dict) -> tuple[int, int]:
    total = 0
    inside = 0
    for feature in collection["features"]:
        for lng, lat in feature["geometry"]["coordinates"]:
            total += 1
            if 124.0 <= lng <= 132.5 and 32.0 <= lat <= 39.5:
                inside += 1
    return inside, total


def normalize_provider(value: str | None) -> str:
    provider = (value or "naver").strip().lower()
    aliases = {
        "naver": "naver",
        "네이버": "naver",
        "kakao": "kakao",
        "카카오": "kakao",
        "google": "google",
        "구글": "google",
    }
    normalized = aliases.get(provider)
    if not normalized:
        supported = ", ".join(sorted(HTML_TEMPLATES))
        raise ValueError(f"Unsupported map provider {value!r}. Supported: {supported}")
    return normalized


def render_html(collection: dict, title: str, api_key: str | None, provider: str = "naver") -> str:
    normalized_provider = normalize_provider(provider)
    meta = f"{len(collection['features'])} features / {count_points(collection)} points"
    output = HTML_TEMPLATES[normalized_provider]
    output = output.replace("__TITLE__", html.escape(title))
    output = output.replace("__META__", html.escape(meta))
    output = output.replace("__DEFAULT_API_KEY__", json.dumps(api_key or ""))
    output = output.replace("__GEOJSON__", json.dumps(collection, ensure_ascii=False, separators=(",", ":")))
    return output


def convert_dxf_to_naver_map(
    input_path: Path,
    source_crs: str,
    axis_order: str = "xy",
    unit_scale: float = 1.0,
    layer_names: set[str] | None = None,
    max_sagitta: float = 1.0,
    output_dir: Path | None = None,
    output_name: str | None = None,
    api_key: str | None = None,
    provider: str = "naver",
) -> ConversionResult:
    if input_path.suffix.lower() == ".dwg":
        raise ValueError("DWG is not parsed directly. Export the drawing to DXF, then run this tool on the DXF file.")
    if input_path.suffix.lower() != ".dxf":
        raise ValueError(f"Expected a DXF input file, got: {input_path}")
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    normalized_crs = normalize_crs(source_crs)
    if normalized_crs != "EPSG:4326" and normalized_crs not in PROJECTIONS:
        supported = ", ".join(["EPSG:4326", *sorted(PROJECTIONS)])
        raise ValueError(f"Unsupported CRS {source_crs!r}. Supported: {supported}")
    if axis_order not in {"xy", "yx"}:
        raise ValueError("axis_order must be 'xy' or 'yx'.")
    if unit_scale <= 0.0:
        raise ValueError("unit_scale must be greater than zero.")
    if max_sagitta <= 0.0:
        raise ValueError("max_sagitta must be greater than zero.")

    normalized_layers = {layer.upper() for layer in layer_names} if layer_names else None
    lines = extract_dxf_lines(input_path, normalized_layers, max_sagitta)
    if not lines:
        layer_hint = " Check layer filters." if normalized_layers else ""
        raise ValueError(f"No supported DXF linework was found in modelspace.{layer_hint}")

    collection = build_feature_collection(input_path, lines, normalized_crs, axis_order, unit_scale)
    if not collection["features"]:
        raise ValueError("No valid geographic line features were generated.")

    normalized_provider = normalize_provider(provider)
    target_dir = output_dir or ROOT / "outputs" / PROVIDER_OUTPUT_DIRS[normalized_provider]
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = output_name or input_path.stem
    geojson_path = target_dir / f"{base_name}.geojson"
    html_path = target_dir / f"{base_name}.html"

    geojson_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(collection, input_path.name, api_key, normalized_provider), encoding="utf-8")

    inside, total = coordinates_in_korea(collection)
    return ConversionResult(
        input_path=input_path,
        geojson_path=geojson_path,
        html_path=html_path,
        feature_count=len(collection["features"]),
        point_count=count_points(collection),
        inside_korea_count=inside,
        total_coordinate_count=total,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert DXF alignment linework to WGS84 GeoJSON and a web map HTML preview.",
    )
    parser.add_argument("--input", required=True, help="Input DXF path. DWG must be exported to DXF first.")
    parser.add_argument("--provider", choices=sorted(HTML_TEMPLATES), default="naver", help="Map provider for generated HTML.")
    parser.add_argument("--crs", default="EPSG:5179", help="Source CRS: EPSG:5179, 5181, 5185-5188, or 4326.")
    parser.add_argument("--axis-order", choices=["xy", "yx"], default="xy", help="xy means CAD X=easting/lng and Y=northing/lat.")
    parser.add_argument("--unit-scale", type=float, default=1.0, help="Scale CAD drawing units to projection meters before conversion.")
    parser.add_argument("--layer", action="append", help="Only export matching DXF layer. Repeat for multiple layers.")
    parser.add_argument("--max-sagitta", type=float, default=1.0, help="Curve flattening tolerance in CAD drawing units.")
    parser.add_argument("--output-dir", help="Directory for generated files. Defaults to outputs/<provider>_map.")
    parser.add_argument("--output-name", help="Base output filename without extension. Defaults to input stem.")
    parser.add_argument("--api-key", help="Optional provider API key to embed.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    input_path = Path(args.input)

    try:
        result = convert_dxf_to_naver_map(
            input_path=input_path,
            source_crs=args.crs,
            axis_order=args.axis_order,
            unit_scale=args.unit_scale,
            layer_names=set(args.layer) if args.layer else None,
            max_sagitta=args.max_sagitta,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            output_name=args.output_name,
            api_key=args.api_key or default_api_key(args.provider),
            provider=args.provider,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Read: {result.input_path}")
    print(f"Line features: {result.feature_count}")
    print(f"Points: {result.point_count}")
    print(f"GeoJSON: {result.geojson_path}")
    print(f"HTML: {result.html_path}")
    if result.total_coordinate_count and result.inside_korea_count / result.total_coordinate_count < 0.9:
        print("Warning: most converted points are outside Korea. Check --crs, --axis-order, and --unit-scale.")

    return 0


def default_api_key(provider: str) -> str | None:
    normalized_provider = normalize_provider(provider)
    env_names = {
        "naver": "NAVER_MAPS_NCP_KEY_ID",
        "kakao": "KAKAO_MAPS_JAVASCRIPT_KEY",
        "google": "GOOGLE_MAPS_API_KEY",
    }
    return os.environ.get(env_names[normalized_provider])


if __name__ == "__main__":
    raise SystemExit(main())
