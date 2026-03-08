from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from contour_detection import ContourResult, bbox_side_lengths_px


@dataclass
class ObjectMeasurement:
    length_mm: float
    width_mm: float
    height_mm: float
    area_mm2: float
    volume_mm3: float


def _safe_depth_stats(depth_mm_values: np.ndarray) -> float:
    valid = depth_mm_values[(depth_mm_values > 0) & np.isfinite(depth_mm_values)]
    if len(valid) == 0:
        raise RuntimeError("No valid depth points available for object.")
    return float(np.median(valid))


def estimate_dimensions(
    contour_result: ContourResult,
    depth_frame: np.ndarray,
    depth_scale_m_per_unit: float,
    mm_per_px: float,
    reference_plane_depth_mm: float | None = None,
) -> ObjectMeasurement:
    length_px, width_px = bbox_side_lengths_px(contour_result.bbox)
    length_mm = length_px * mm_per_px
    width_mm = width_px * mm_per_px

    mask = np.zeros(depth_frame.shape, dtype=np.uint8)
    import cv2  # local import to keep module load lightweight

    cv2.drawContours(mask, [contour_result.contour], -1, 255, thickness=-1)
    object_depth_raw = depth_frame[mask == 255]
    object_depth_mm = object_depth_raw.astype(np.float32) * depth_scale_m_per_unit * 1000.0

    object_depth_median_mm = _safe_depth_stats(object_depth_mm)

    if reference_plane_depth_mm is None:
        reference_plane_depth_mm = object_depth_median_mm

    height_mm = max(0.0, reference_plane_depth_mm - object_depth_median_mm)

    area_mm2 = contour_result.area_px * (mm_per_px**2)
    volume_mm3 = area_mm2 * max(height_mm, 1.0)

    return ObjectMeasurement(
        length_mm=float(length_mm),
        width_mm=float(width_mm),
        height_mm=float(height_mm),
        area_mm2=float(area_mm2),
        volume_mm3=float(volume_mm3),
    )
