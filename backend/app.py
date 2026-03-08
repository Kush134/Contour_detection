from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import cv2
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from calibration import load_calibration
from database import compare_with_reference, init_db
from main import process_frame
from model_3d import render_box_model
from realsense_capture import RealSenseCamera
from report import save_json_report, save_pdf_report


class StartRequest(BaseModel):
    reference_name: str | None = None
    calibration_file: str | None = None
    reference_plane_depth_mm: float | None = None


class CommandRequest(BaseModel):
    command: Literal["s", "q"]


class IdentificationService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = self._load_config()

        self.lock = threading.Lock()
        self.running = False
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()

        self.camera: RealSenseCamera | None = None
        self.calib_data = None
        self.reference_name: str | None = None
        self.reference_plane_depth_mm: float | None = None

        self.latest_original_jpg: bytes | None = None
        self.latest_workspace_jpg: bytes | None = None
        self.latest_result = None
        self.latest_error: str | None = None

        init_db(Path(self.config["database"]["path"]))

    def _load_config(self) -> dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _encode_jpg(self, image) -> bytes:
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            raise RuntimeError("Failed to encode frame as JPEG.")
        return encoded.tobytes()

    def start(
        self,
        reference_name: str | None,
        calibration_file: str | None,
        reference_plane_depth_mm: float | None,
    ) -> None:
        with self.lock:
            if self.running:
                raise RuntimeError("Identification is already running.")

            self.config = self._load_config()
            self.reference_name = reference_name
            self.reference_plane_depth_mm = reference_plane_depth_mm
            self.latest_error = None
            self.latest_result = None

            calibration_path = Path(calibration_file or "data/calibration/camera_calibration.npz")
            self.calib_data = load_calibration(calibration_path)

            rs_cfg = self.config["realsense"]
            self.camera = RealSenseCamera(
                width=int(rs_cfg["width"]),
                height=int(rs_cfg["height"]),
                fps=int(rs_cfg["fps"]),
                align_depth_to_color=bool(rs_cfg["align_depth_to_color"]),
            )
            self.camera.start()

            self.stop_event.clear()
            self.running = True
            self.worker = threading.Thread(target=self._loop, daemon=True)
            self.worker.start()

    def _loop(self) -> None:
        assert self.camera is not None
        while not self.stop_event.is_set():
            try:
                frame = self.camera.get_frames()
                result = process_frame(
                    frame=frame,
                    calib_data=self.calib_data,
                    config=self.config,
                    reference_plane_depth_mm=self.reference_plane_depth_mm,
                )

                original_jpg = self._encode_jpg(result.overlay_original)
                workspace_jpg = self._encode_jpg(result.overlay_workspace)

                with self.lock:
                    self.latest_result = result
                    self.latest_original_jpg = original_jpg
                    self.latest_workspace_jpg = workspace_jpg
                    self.latest_error = None
            except Exception as exc:
                with self.lock:
                    self.latest_error = str(exc)

        if self.camera is not None:
            self.camera.stop()

    def stop(self) -> None:
        with self.lock:
            if not self.running:
                return
            self.running = False
            self.stop_event.set()
            worker = self.worker

        if worker is not None and worker.is_alive():
            worker.join(timeout=3.0)

        with self.lock:
            self.worker = None

    def _save_report(self, trigger: str) -> dict[str, Any]:
        with self.lock:
            if self.latest_result is None:
                raise RuntimeError("No valid frame yet. Keep markers/object visible and try again.")
            result = self.latest_result
            config = self.config
            reference_name = self.reference_name

        db_path = Path(config["database"]["path"])
        comparison = None
        if reference_name:
            comparison = compare_with_reference(db_path, reference_name, result.measurement)

        report_dir = Path(config["report"]["output_dir"])
        model_path = render_box_model(result.measurement, report_dir)

        metadata = dict(result.metadata)
        metadata["trigger"] = trigger
        metadata["model_image"] = str(model_path)

        json_report = save_json_report(report_dir, result.measurement, comparison, metadata)
        pdf_report = save_pdf_report(report_dir, result.measurement, comparison, metadata, model_image_path=model_path)

        entry = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "trigger": trigger,
            "measurement": asdict(result.measurement),
            "comparison": asdict(comparison) if comparison else None,
            "json_report": json_report.name,
            "pdf_report": pdf_report.name,
            "model_image": model_path.name,
        }
        return entry

    def command(self, command: str) -> dict[str, Any]:
        if command == "s":
            return self._save_report(trigger="s")
        if command == "q":
            entry = self._save_report(trigger="q")
            self.stop()
            return entry
        raise RuntimeError(f"Unsupported command: {command}")

    def status(self) -> dict[str, Any]:
        with self.lock:
            measurement = asdict(self.latest_result.measurement) if self.latest_result else None
            metadata = dict(self.latest_result.metadata) if self.latest_result else None
            return {
                "running": self.running,
                "error": self.latest_error,
                "measurement": measurement,
                "metadata": metadata,
                "reference_name": self.reference_name,
            }

    def latest_frame(self, view: str) -> bytes:
        with self.lock:
            if view == "original":
                frame = self.latest_original_jpg
            elif view == "workspace":
                frame = self.latest_workspace_jpg
            else:
                frame = None

        if frame is None:
            raise RuntimeError("No frame available yet.")
        return frame

    def list_reports(self) -> list[dict[str, Any]]:
        report_dir = Path(self.config["report"]["output_dir"])
        report_dir.mkdir(parents=True, exist_ok=True)

        reports: list[dict[str, Any]] = []
        for json_file in sorted(report_dir.glob("measurement_report_*.json"), reverse=True):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            model_path = payload.get("metadata", {}).get("model_image")
            model_name = Path(model_path).name if model_path else None
            stem = json_file.stem
            pdf_file = report_dir / f"{stem}.pdf"

            reports.append(
                {
                    "timestamp": payload.get("timestamp"),
                    "measurement": payload.get("measurement"),
                    "comparison": payload.get("comparison"),
                    "metadata": payload.get("metadata"),
                    "json_url": f"/reports/{json_file.name}",
                    "pdf_url": f"/reports/{pdf_file.name}" if pdf_file.exists() else None,
                    "model_url": f"/reports/{model_name}" if model_name and (report_dir / model_name).exists() else None,
                }
            )
        return reports


app = FastAPI(title="AWTO Identification Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = IdentificationService(config_path=ROOT_DIR / "config.yaml")

report_dir_abs = (ROOT_DIR / service.config["report"]["output_dir"]).resolve()
report_dir_abs.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(report_dir_abs)), name="reports")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/identification/status")
def identification_status() -> dict[str, Any]:
    return service.status()


@app.post("/api/identification/start")
def identification_start(req: StartRequest) -> dict[str, Any]:
    try:
        service.start(
            reference_name=req.reference_name,
            calibration_file=req.calibration_file,
            reference_plane_depth_mm=req.reference_plane_depth_mm,
        )
        return {"status": "started"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/identification/command")
def identification_command(req: CommandRequest) -> dict[str, Any]:
    try:
        report = service.command(req.command)
        return {"status": "ok", "report": report}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/identification/stop")
def identification_stop() -> dict[str, Any]:
    service.stop()
    return {"status": "stopped"}


@app.get("/api/identification/frame/{view}")
def identification_frame(view: str) -> Response:
    try:
        frame = service.latest_frame(view)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/reports")
def reports_list() -> JSONResponse:
    return JSONResponse(service.list_reports())


@app.on_event("shutdown")
def on_shutdown() -> None:
    service.stop()
