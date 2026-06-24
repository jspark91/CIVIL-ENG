from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import naver_map_from_dxf


PORT = 8787
OUTPUT_ROOT = ROOT / "outputs"
PROVIDER_OUTPUT_DIRS = naver_map_from_dxf.PROVIDER_OUTPUT_DIRS


INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DXF Map Viewer</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f5f7fb;
      color: #1f2937;
    }

    main {
      width: min(980px, calc(100vw - 32px));
      margin: 24px auto;
    }

    .panel {
      background: #ffffff;
      border: 1px solid #d7dce5;
      border-radius: 8px;
      box-shadow: 0 12px 28px rgba(31, 41, 55, 0.12);
      padding: 18px;
    }

    h1 {
      margin: 0 0 14px;
      font-size: 20px;
    }

    .grid {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 10px 12px;
      align-items: center;
    }

    label {
      font-size: 13px;
      font-weight: 700;
    }

    input, select {
      min-width: 0;
      height: 34px;
      padding: 0 9px;
      border: 1px solid #b9c2cf;
      border-radius: 6px;
      font-size: 13px;
      box-sizing: border-box;
      background: #ffffff;
    }

    input[type=file] {
      height: auto;
      padding: 7px 9px;
    }

    .inline {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 14px;
    }

    button, a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      padding: 0 14px;
      border: 0;
      border-radius: 6px;
      color: #ffffff;
      background: #0f6bdc;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }

    button:disabled {
      background: #94a3b8;
      cursor: wait;
    }

    .hint {
      margin-top: 12px;
      font-size: 12px;
      color: #526071;
      line-height: 1.5;
    }

    .status {
      margin-top: 14px;
      min-height: 96px;
      padding: 10px;
      border-radius: 6px;
      background: #111827;
      color: #e5e7eb;
      white-space: pre-wrap;
      font-family: Consolas, monospace;
      font-size: 12px;
      overflow: auto;
    }

    .result {
      display: none;
      margin-top: 14px;
      padding: 12px;
      border: 1px solid #b7dfc3;
      border-radius: 6px;
      background: #effaf1;
    }

    .result.visible {
      display: block;
    }

    @media (max-width: 720px) {
      .grid {
        grid-template-columns: 1fr;
      }

      .inline {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>DXF Map Viewer</h1>
      <div class="grid">
        <label for="dxf">DXF 파일</label>
        <input id="dxf" type="file" accept=".dxf">

        <label for="provider">지도</label>
        <select id="provider">
          <option value="naver">NAVER Map</option>
          <option value="kakao">Kakao Map</option>
          <option value="google">Google Maps</option>
        </select>

        <label for="outputName">출력 이름</label>
        <input id="outputName" placeholder="비워두면 DXF 파일명 사용">

        <label for="crs">좌표계</label>
        <select id="crs">
          <option value="EPSG:5186">EPSG:5186 - GRS80 중부좌표 2010</option>
          <option value="EPSG:5181">EPSG:5181 - GRS80 중부좌표</option>
          <option value="EPSG:5179">EPSG:5179 - GRS80 통합좌표/UTM-K</option>
          <option value="EPSG:5185">EPSG:5185 - GRS80 서부좌표 2010</option>
          <option value="EPSG:5187">EPSG:5187 - GRS80 동부좌표 2010</option>
          <option value="EPSG:5188">EPSG:5188 - GRS80 동해좌표 2010</option>
          <option value="EPSG:4326">EPSG:4326 - WGS84 경위도</option>
        </select>

        <label>옵션</label>
        <div class="inline">
          <select id="axisOrder">
            <option value="xy">축 xy</option>
            <option value="yx">축 yx</option>
          </select>
          <input id="unitScale" value="1.0" title="단위 배율">
          <input id="maxSagitta" value="1.0" title="곡선 허용오차">
        </div>

        <label for="layers">레이어</label>
        <input id="layers" placeholder="예: CZ-CNTL 또는 ALIGN,CENTERLINE">

        <label id="apiKeyLabel" for="apiKey">NAVER ncpKeyId</label>
        <input id="apiKey" type="password" autocomplete="off" placeholder="Client ID / ncpKeyId">
      </div>

      <div class="actions">
        <button id="convertButton">변환 실행</button>
      </div>

      <div class="hint">
        Register <strong>http://localhost:8787</strong> and <strong>http://127.0.0.1:8787</strong>
        in each map provider's web/origin/referrer setting.
        Outputs are separated into outputs/naver_map, outputs/kakao_map, and outputs/google_map.
      </div>

      <div id="result" class="result"></div>
      <div id="status" class="status">DXF 파일을 선택하고 변환 실행을 누르세요.</div>
    </section>
  </main>

  <script>
    const dxfInput = document.getElementById("dxf");
    const providerInput = document.getElementById("provider");
    const outputNameInput = document.getElementById("outputName");
    const apiKeyInput = document.getElementById("apiKey");
    const apiKeyLabel = document.getElementById("apiKeyLabel");
    const statusBox = document.getElementById("status");
    const resultBox = document.getElementById("result");
    const button = document.getElementById("convertButton");
    const providerNames = {
      naver: "NAVER",
      kakao: "Kakao",
      google: "Google"
    };
    const keyLabels = {
      naver: "NAVER ncpKeyId",
      kakao: "Kakao JavaScript key",
      google: "Google Maps API key"
    };
    const keyPlaceholders = {
      naver: "Client ID / ncpKeyId",
      kakao: "JavaScript key",
      google: "API key"
    };

    dxfInput.addEventListener("change", function () {
      const file = dxfInput.files[0];
      if (file && !outputNameInput.value.trim()) {
        outputNameInput.value = file.name.replace(/\\.dxf$/i, "");
      }
    });

    function setStatus(message) {
      statusBox.textContent = message;
    }

    function updateProviderKeyHint() {
      const provider = providerInput.value;
      apiKeyLabel.textContent = keyLabels[provider] || "Map API key";
      apiKeyInput.placeholder = keyPlaceholders[provider] || "API key";
    }

    function arrayBufferToBase64(buffer) {
      const bytes = new Uint8Array(buffer);
      let binary = "";
      const chunkSize = 0x8000;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
      }
      return btoa(binary);
    }

    async function convert() {
      const file = dxfInput.files[0];
      if (!file) {
        setStatus("DXF 파일을 선택하세요.");
        return;
      }

      button.disabled = true;
      resultBox.classList.remove("visible");
      resultBox.innerHTML = "";
      setStatus("DXF 읽는 중...");

      try {
        const buffer = await file.arrayBuffer();
        const payload = {
          provider: providerInput.value,
          filename: file.name,
          dxfBase64: arrayBufferToBase64(buffer),
          outputName: outputNameInput.value.trim(),
          crs: document.getElementById("crs").value,
          axisOrder: document.getElementById("axisOrder").value,
          unitScale: document.getElementById("unitScale").value,
          maxSagitta: document.getElementById("maxSagitta").value,
          layers: document.getElementById("layers").value,
          apiKey: apiKeyInput.value.trim()
        };

        setStatus("변환 중...");
        const response = await fetch("/convert", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "변환 실패");
        }

        setStatus(
          "완료\\n" +
          "선형: " + data.featureCount + "개\\n" +
          "점: " + data.pointCount + "개\\n" +
          "HTML: " + data.htmlPath + "\\n" +
          "GeoJSON: " + data.geojsonPath
        );

        resultBox.innerHTML =
          '<a class="button" target="_blank" href="' + data.openUrl + '">' + (providerNames[data.provider] || data.providerName || "Map") + ' 열기</a>';
        resultBox.classList.add("visible");
        window.open(data.openUrl, "_blank");
      } catch (error) {
        setStatus("오류: " + error.message);
      } finally {
        button.disabled = false;
      }
    }

    providerInput.addEventListener("change", updateProviderKeyHint);
    button.addEventListener("click", convert);
    updateProviderKeyHint();
  </script>
</body>
</html>
"""


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "DxfMapViewer/0.2"

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"", "/"}:
            self.send_text(INDEX_HTML, "text/html; charset=utf-8")
            return

        if parsed.path.startswith("/results/"):
            relative = unquote(parsed.path.removeprefix("/results/"))
            parts = [part for part in relative.split("/") if part]
            if len(parts) == 1:
                provider = "naver"
                filename = parts[0]
            elif len(parts) == 2:
                provider, filename = parts
            else:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self.send_output_file(provider, filename)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/convert":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("요청 본문이 비어 있습니다.")
            if length > 250 * 1024 * 1024:
                raise ValueError("DXF 파일이 너무 큽니다. 250MB 이하 파일만 처리합니다.")

            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = convert_payload(payload)
            self.send_json(result)
        except Exception as exc:
            self.send_json({"error": str(exc), "trace": traceback.format_exc()}, status=HTTPStatus.BAD_REQUEST)

    def send_output_file(self, provider: str, filename: str) -> None:
        if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        try:
            output_dir = output_dir_for_provider(provider)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        path = output_dir / filename
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = "text/html; charset=utf-8" if path.suffix.lower() == ".html" else "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, text: str, content_type: str) -> None:
        data = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def convert_payload(payload: dict) -> dict:
    provider = naver_map_from_dxf.normalize_provider(str(payload.get("provider") or "naver"))
    filename = sanitize_filename(str(payload.get("filename") or "alignment.dxf"))
    if not filename.lower().endswith(".dxf"):
        raise ValueError("DXF 파일만 지원합니다.")

    dxf_base64 = str(payload.get("dxfBase64") or "")
    if not dxf_base64:
        raise ValueError("DXF 데이터가 없습니다.")

    output_dir = output_dir_for_provider(provider)
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = output_dir / "_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    input_path = upload_dir / f"{timestamp}_{filename}"
    input_path.write_bytes(base64.b64decode(dxf_base64))

    layers = parse_layers(str(payload.get("layers") or ""))
    output_name = sanitize_output_name(str(payload.get("outputName") or Path(filename).stem))

    result = naver_map_from_dxf.convert_dxf_to_naver_map(
        input_path=input_path,
        source_crs=str(payload.get("crs") or "EPSG:5186"),
        axis_order=str(payload.get("axisOrder") or "xy"),
        unit_scale=float(payload.get("unitScale") or "1.0"),
        layer_names=layers,
        max_sagitta=float(payload.get("maxSagitta") or "1.0"),
        output_dir=output_dir,
        output_name=output_name,
        api_key=str(payload.get("apiKey") or "") or None,
        provider=provider,
    )

    return {
        "provider": provider,
        "providerName": provider.title(),
        "featureCount": result.feature_count,
        "pointCount": result.point_count,
        "htmlPath": str(result.html_path),
        "geojsonPath": str(result.geojson_path),
        "openUrl": f"/results/{provider}/{quote(result.html_path.name)}",
    }


def output_dir_for_provider(provider: str) -> Path:
    normalized = naver_map_from_dxf.normalize_provider(provider)
    return OUTPUT_ROOT / PROVIDER_OUTPUT_DIRS[normalized]


def parse_layers(value: str) -> set[str] | None:
    layers = {part.strip().upper() for part in re.split(r"[,;]", value) if part.strip()}
    return layers or None


def sanitize_filename(value: str) -> str:
    name = Path(value).name.strip() or "alignment.dxf"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def sanitize_output_name(value: str) -> str:
    name = Path(value).stem.strip() or "alignment"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def find_port(preferred: int) -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        if sock.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred

    for port in range(preferred + 1, preferred + 50):
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("사용 가능한 로컬 포트를 찾지 못했습니다.")


def self_test() -> int:
    with contextlib.redirect_stderr(io.StringIO()):
        import ezdxf

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dxf_path = tmp_path / "self-test.dxf"
        out_dir = tmp_path / "out"
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_line((200_000.0, 600_000.0), (200_010.0, 600_000.0), dxfattribs={"layer": "ALIGN"})
        doc.saveas(dxf_path)

        for provider in ("naver", "kakao", "google"):
            result = naver_map_from_dxf.convert_dxf_to_naver_map(
                input_path=dxf_path,
                source_crs="EPSG:5186",
                layer_names={"ALIGN"},
                output_dir=out_dir / provider,
                output_name="self-test",
                provider=provider,
            )
            if not result.html_path.exists() or result.feature_count != 1:
                return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    port = find_port(PORT)
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    url = f"http://localhost:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    webbrowser.open(url)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
