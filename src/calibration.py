from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


@dataclass
class CalibrationData:
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray


class CameraCalibrator:
    def __init__(self, board_size: Tuple[int, int] = (9, 6), square_size_mm: float = 25.0) -> None:
        self.board_size = board_size
        self.square_size_mm = square_size_mm

    def calibrate_from_images(self, image_paths: List[Path]) -> CalibrationData:
        objp = np.zeros((self.board_size[0] * self.board_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0 : self.board_size[0], 0 : self.board_size[1]].T.reshape(-1, 2)
        objp *= self.square_size_mm

        obj_points = []
        img_points = []
        image_size = None

        for image_path in image_paths:
            img = cv2.imread(str(image_path))
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            found, corners = cv2.findChessboardCorners(gray, self.board_size, None)
            if found:
                corners_refined = cv2.cornerSubPix(
                    gray,
                    corners,
                    winSize=(11, 11),
                    zeroZone=(-1, -1),
                    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
                )
                obj_points.append(objp)
                img_points.append(corners_refined)
                image_size = gray.shape[::-1]

        if not obj_points or image_size is None:
            raise RuntimeError("No valid chessboard detections for calibration.")

        _, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
            obj_points, img_points, image_size, None, None
        )

        return CalibrationData(camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)


def save_calibration(path: Path, calib: CalibrationData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(path), camera_matrix=calib.camera_matrix, dist_coeffs=calib.dist_coeffs)


def load_calibration(path: Path) -> CalibrationData:
    if not path.exists():
        raise FileNotFoundError(
            f"Calibration file not found at {path}. Run calibration first or provide --calibration path."
        )
    data = np.load(str(path))
    return CalibrationData(camera_matrix=data["camera_matrix"], dist_coeffs=data["dist_coeffs"])
