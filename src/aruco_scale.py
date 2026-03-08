from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class ArucoScaleResult:
    mm_per_px: float
    detected_ids: List[int]
    corners: Dict[int, np.ndarray]
    centers: Dict[int, np.ndarray]


@dataclass
class WorkspaceTransform:
    homography: np.ndarray
    homography_inv: np.ndarray
    width_px: int
    height_px: int
    px_per_mm: float
    mm_per_px: float


def _dict_from_name(name: str) -> int:
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"Unknown ArUco dictionary name: {name}")
    return getattr(cv2.aruco, name)


def detect_aruco_scale(
    image: np.ndarray,
    marker_size_mm: float,
    marker_ids_expected: Sequence[int],
    dict_name: str = "DICT_4X4_50",
) -> ArucoScaleResult:
    dictionary = cv2.aruco.getPredefinedDictionary(_dict_from_name(dict_name))
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)

    corners, ids, _ = detector.detectMarkers(image)
    if ids is None or len(ids) == 0:
        raise RuntimeError("No ArUco markers detected.")

    id_list = [int(i[0]) for i in ids]
    missing = sorted(set(marker_ids_expected) - set(id_list))
    if missing:
        raise RuntimeError(f"Missing required ArUco IDs: {missing}. Detected IDs: {id_list}")

    px_per_marker = []
    corners_map: Dict[int, np.ndarray] = {}
    centers_map: Dict[int, np.ndarray] = {}

    for c, id_val in zip(corners, id_list):
        c2 = c.reshape(4, 2)
        corners_map[id_val] = c2
        centers_map[id_val] = np.mean(c2, axis=0)
        edges = [
            np.linalg.norm(c2[0] - c2[1]),
            np.linalg.norm(c2[1] - c2[2]),
            np.linalg.norm(c2[2] - c2[3]),
            np.linalg.norm(c2[3] - c2[0]),
        ]
        px_per_marker.append(float(np.mean(edges)))

    mean_px = float(np.mean(px_per_marker))
    mm_per_px = marker_size_mm / mean_px

    return ArucoScaleResult(
        mm_per_px=mm_per_px,
        detected_ids=id_list,
        corners=corners_map,
        centers=centers_map,
    )


def build_workspace_transform(
    aruco_result: ArucoScaleResult,
    marker_ids_order: Sequence[int],
    marker_spacing_mm: float,
    px_per_mm: float,
) -> WorkspaceTransform:
    if len(marker_ids_order) != 4:
        raise ValueError("marker_ids_order must have exactly 4 IDs.")

    src_points = []
    for marker_id in marker_ids_order:
        center = aruco_result.centers.get(int(marker_id))
        if center is None:
            raise RuntimeError(f"Marker ID {marker_id} not detected for workspace transform.")
        src_points.append(center)

    src = np.array(src_points, dtype=np.float32)

    width_px = int(round(marker_spacing_mm * px_per_mm))
    height_px = int(round(marker_spacing_mm * px_per_mm))

    dst = np.array(
        [
            [0, 0],
            [width_px - 1, 0],
            [width_px - 1, height_px - 1],
            [0, height_px - 1],
        ],
        dtype=np.float32,
    )

    homography = cv2.getPerspectiveTransform(src, dst)
    homography_inv = cv2.getPerspectiveTransform(dst, src)

    return WorkspaceTransform(
        homography=homography,
        homography_inv=homography_inv,
        width_px=width_px,
        height_px=height_px,
        px_per_mm=px_per_mm,
        mm_per_px=1.0 / px_per_mm,
    )


def warp_to_workspace(
    image: np.ndarray,
    transform: WorkspaceTransform,
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    return cv2.warpPerspective(
        image,
        transform.homography,
        (transform.width_px, transform.height_px),
        flags=interpolation,
    )


def estimate_plane_depth_mm_from_markers(
    depth_frame: np.ndarray,
    depth_scale_m_per_unit: float,
    aruco_result: ArucoScaleResult,
    sample_radius_px: int = 6,
) -> float:
    samples_mm = []

    for center in aruco_result.centers.values():
        x = int(round(center[0]))
        y = int(round(center[1]))

        x0 = max(0, x - sample_radius_px)
        x1 = min(depth_frame.shape[1], x + sample_radius_px + 1)
        y0 = max(0, y - sample_radius_px)
        y1 = min(depth_frame.shape[0], y + sample_radius_px + 1)

        patch = depth_frame[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        patch_mm = patch.astype(np.float32) * depth_scale_m_per_unit * 1000.0
        valid = patch_mm[(patch_mm > 0) & np.isfinite(patch_mm)]
        if len(valid) > 0:
            samples_mm.append(float(np.median(valid)))

    if not samples_mm:
        raise RuntimeError("Could not estimate plane depth from ArUco marker zones.")

    return float(np.median(np.array(samples_mm, dtype=np.float32)))


def draw_markers(image: np.ndarray, aruco_result: ArucoScaleResult) -> np.ndarray:
    out = image.copy()
    for marker_id, c in aruco_result.corners.items():
        c_int = c.astype(int)
        for i in range(4):
            p1 = tuple(c_int[i])
            p2 = tuple(c_int[(i + 1) % 4])
            cv2.line(out, p1, p2, (0, 255, 0), 2)
        center = tuple(np.mean(c_int, axis=0).astype(int))
        cv2.putText(out, f"ID {marker_id}", center, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.circle(out, center, 3, (0, 255, 0), -1)
    return out
