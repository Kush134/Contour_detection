from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import cv2
import yaml

from aruco_scale import (
    build_workspace_transform,
    detect_aruco_scale,
    draw_markers,
    estimate_plane_depth_mm_from_markers,
    warp_to_workspace,
)
from calibration import CameraCalibrator, load_calibration, save_calibration
from contour_detection import detect_primary_object_contour, draw_contour
from database import compare_with_reference, init_db, upsert_reference
from measurement import ObjectMeasurement, estimate_dimensions
from model_3d import render_box_model
from realsense_capture import FrameBundle, RealSenseCamera
from report import save_json_report, save_pdf_report


@dataclass
class FrameProcessResult:
    measurement: ObjectMeasurement
    metadata: Dict[str, Any]
    overlay_original: Any
    overlay_workspace: Any
    plane_depth_mm: float


def load_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_calibration(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    image_dir = Path(args.calibration_images)
    images = sorted(image_dir.glob("*.png")) + sorted(image_dir.glob("*.jpg"))
    if not images:
        raise RuntimeError(f"No calibration images found in {image_dir}")

    calibrator = CameraCalibrator(
        board_size=(args.chess_cols, args.chess_rows),
        square_size_mm=args.square_size_mm,
    )
    calib_data = calibrator.calibrate_from_images(images)

    out_path = Path(args.calibration_output)
    save_calibration(out_path, calib_data)
    print(f"Calibration saved: {out_path}")


def process_frame(
    frame: FrameBundle,
    calib_data,
    config: Dict[str, Any],
    reference_plane_depth_mm: float | None,
) -> FrameProcessResult:
    undistorted = cv2.undistort(frame.color, calib_data.camera_matrix, calib_data.dist_coeffs)

    ar_cfg = config["aruco"]
    ar_result = detect_aruco_scale(
        undistorted,
        marker_size_mm=float(ar_cfg["marker_size_mm"]),
        marker_ids_expected=ar_cfg["marker_ids"],
        dict_name=ar_cfg["dictionary"],
    )

    workspace = build_workspace_transform(
        aruco_result=ar_result,
        marker_ids_order=ar_cfg["workspace_id_order"],
        marker_spacing_mm=float(ar_cfg["marker_spacing_mm"]),
        px_per_mm=float(ar_cfg["workspace_px_per_mm"]),
    )

    warped_color = warp_to_workspace(undistorted, workspace, interpolation=cv2.INTER_LINEAR)
    warped_depth = warp_to_workspace(frame.depth, workspace, interpolation=cv2.INTER_NEAREST)

    c_cfg = config["contour"]
    contour_result = detect_primary_object_contour(
        warped_color,
        blur_kernel=int(c_cfg["blur_kernel"]),
        canny_low=int(c_cfg["canny_low"]),
        canny_high=int(c_cfg["canny_high"]),
        min_area_px=int(c_cfg["min_area_px"]),
        exclude_border_px=int(c_cfg.get("exclude_border_px", 8)),
        max_area_ratio=float(c_cfg.get("max_area_ratio", 0.85)),
    )

    plane_depth_mm = reference_plane_depth_mm
    if plane_depth_mm is None:
        plane_depth_mm = estimate_plane_depth_mm_from_markers(
            depth_frame=frame.depth,
            depth_scale_m_per_unit=frame.depth_scale,
            aruco_result=ar_result,
            sample_radius_px=int(ar_cfg.get("plane_depth_sample_radius_px", 6)),
        )

    measurement = estimate_dimensions(
        contour_result=contour_result,
        depth_frame=warped_depth,
        depth_scale_m_per_unit=frame.depth_scale,
        mm_per_px=workspace.mm_per_px,
        reference_plane_depth_mm=plane_depth_mm,
    )

    overlay_original = draw_markers(undistorted, ar_result)
    overlay_workspace = draw_contour(warped_color, contour_result)
    cv2.putText(
        overlay_workspace,
        f"L:{measurement.length_mm:.1f} W:{measurement.width_mm:.1f} H:{measurement.height_mm:.1f} mm",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (20, 20, 230),
        2,
        cv2.LINE_AA,
    )

    metadata = {
        "aruco_detected_ids": ar_result.detected_ids,
        "aruco_marker_size_mm": float(ar_cfg["marker_size_mm"]),
        "aruco_marker_spacing_mm": float(ar_cfg["marker_spacing_mm"]),
        "workspace_mm_per_px": round(workspace.mm_per_px, 6),
        "plane_depth_mm": round(plane_depth_mm, 3),
        "camera": "Intel RealSense D435",
        "background": "flat plane",
    }

    return FrameProcessResult(
        measurement=measurement,
        metadata=metadata,
        overlay_original=overlay_original,
        overlay_workspace=overlay_workspace,
        plane_depth_mm=plane_depth_mm,
    )


def _save_outputs(
    config: Dict[str, Any],
    result: FrameProcessResult,
    reference_name: str | None,
) -> None:
    db_path = Path(config["database"]["path"])
    comparison = None
    if reference_name:
        comparison = compare_with_reference(db_path, reference_name, result.measurement)

    report_dir = Path(config["report"]["output_dir"])
    model_path = render_box_model(result.measurement, report_dir)

    metadata = dict(result.metadata)
    metadata["model_image"] = str(model_path)

    json_report = save_json_report(report_dir, result.measurement, comparison, metadata)
    pdf_report = save_pdf_report(report_dir, result.measurement, comparison, metadata, model_image_path=model_path)

    print("Measurement complete")
    print(f"Length: {result.measurement.length_mm:.2f} mm")
    print(f"Width: {result.measurement.width_mm:.2f} mm")
    print(f"Height: {result.measurement.height_mm:.2f} mm")
    if comparison:
        print(f"Database check: {'PASS' if comparison.passed else 'FAIL'}")
    print(f"JSON report: {json_report}")
    print(f"PDF report: {pdf_report}")
    print(f"3D model image: {model_path}")

    if config["runtime"].get("save_debug_images", False):
        debug_dir = Path(config["runtime"].get("debug_dir", report_dir))
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "debug_original_markers.png"), result.overlay_original)
        cv2.imwrite(str(debug_dir / "debug_workspace_contour.png"), result.overlay_workspace)
        print(f"Debug images saved to: {debug_dir}")


def run_measurement(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    db_path = Path(config["database"]["path"])
    init_db(db_path)

    if args.add_reference:
        name, l, w, h, tol = args.add_reference
        upsert_reference(db_path, name, float(l), float(w), float(h), float(tol))
        print(f"Reference '{name}' inserted/updated in {db_path}")
        return

    calib = load_calibration(Path(args.calibration_file))

    rs_cfg = config["realsense"]
    camera = RealSenseCamera(
        width=rs_cfg["width"],
        height=rs_cfg["height"],
        fps=rs_cfg["fps"],
        align_depth_to_color=rs_cfg["align_depth_to_color"],
    )

    camera.start()
    try:
        if args.live:
            run_live_loop(camera, calib, args, config)
        else:
            frame = camera.get_frames()
            result = process_frame(frame, calib, config, args.reference_plane_depth_mm)
            _save_outputs(config, result, args.reference_name)
    finally:
        camera.stop()


def run_live_loop(
    camera: RealSenseCamera,
    calib,
    args: argparse.Namespace,
    config: Dict[str, Any],
) -> None:
    last_result: FrameProcessResult | None = None

    print("Live mode started. Press 's' to save current report, 'q' to quit.")

    while True:
        frame = camera.get_frames()

        try:
            result = process_frame(frame, calib, config, args.reference_plane_depth_mm)
            last_result = result
            workspace_view = result.overlay_workspace
            original_view = result.overlay_original
        except Exception as exc:
            original_view = frame.color.copy()
            workspace_view = cv2.resize(frame.color, (700, 700))
            cv2.putText(
                original_view,
                f"Waiting for stable detection: {exc}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        cv2.imshow("original_markers", original_view)
        cv2.imshow("workspace_contour", workspace_view)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            if last_result is None:
                print("No valid measurement frame yet. Keep markers/object visible and try again.")
            else:
                _save_outputs(config, last_result, args.reference_name)

    cv2.destroyAllWindows()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="3D object measurement with RealSense + ArUco + contour")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")

    sub = parser.add_subparsers(dest="command", required=True)

    p_calib = sub.add_parser("calibrate", help="Run camera calibration from chessboard images")
    p_calib.add_argument("--calibration-images", required=True, help="Folder with chessboard images")
    p_calib.add_argument("--calibration-output", default="data/calibration/camera_calibration.npz")
    p_calib.add_argument("--chess-cols", type=int, default=9)
    p_calib.add_argument("--chess-rows", type=int, default=6)
    p_calib.add_argument("--square-size-mm", type=float, default=25.0)

    p_run = sub.add_parser("run", help="Capture and measure object")
    p_run.add_argument("--calibration-file", default="data/calibration/camera_calibration.npz")
    p_run.add_argument("--reference-name", default=None, help="Reference object name for DB comparison")
    p_run.add_argument("--reference-plane-depth-mm", type=float, default=None)
    p_run.add_argument("--live", action="store_true", help="Live preview mode, press 's' to save report")
    p_run.add_argument(
        "--add-reference",
        nargs=5,
        metavar=("NAME", "LENGTH_MM", "WIDTH_MM", "HEIGHT_MM", "TOLERANCE_MM"),
        help="Insert/update a reference object and exit",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(args.config))

    if args.command == "calibrate":
        run_calibration(args, config)
    elif args.command == "run":
        run_measurement(args, config)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
