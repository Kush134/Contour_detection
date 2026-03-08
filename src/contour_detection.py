from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np


@dataclass
class ContourResult:
    contour: np.ndarray
    bbox: np.ndarray
    area_px: float


def detect_primary_object_contour(
    image: np.ndarray,
    blur_kernel: int = 5,
    canny_low: int = 60,
    canny_high: int = 150,
    min_area_px: int = 2000,
    exclude_border_px: int = 8,
    max_area_ratio: float = 0.85,
) -> ContourResult:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
    edges = cv2.Canny(blur, canny_low, canny_high)

    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.erode(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    valid = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area_px:
            continue
        if area > image_area * max_area_ratio:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        if (
            x <= exclude_border_px
            or y <= exclude_border_px
            or x + w >= image.shape[1] - exclude_border_px
            or y + h >= image.shape[0] - exclude_border_px
        ):
            continue
        valid.append(contour)

    if not valid:
        raise RuntimeError("No valid object contour found.")

    contour = max(valid, key=cv2.contourArea)
    area_px = float(cv2.contourArea(contour))
    bbox = cv2.boxPoints(cv2.minAreaRect(contour))

    return ContourResult(contour=contour, bbox=bbox, area_px=area_px)


def draw_contour(image: np.ndarray, result: ContourResult) -> np.ndarray:
    out = image.copy()
    cv2.drawContours(out, [result.contour], -1, (255, 0, 0), 2)
    cv2.drawContours(out, [result.bbox.astype(int)], -1, (0, 0, 255), 2)
    return out


def bbox_side_lengths_px(bbox: np.ndarray) -> Tuple[float, float]:
    pts = bbox.reshape(4, 2)
    sides = [
        float(np.linalg.norm(pts[0] - pts[1])),
        float(np.linalg.norm(pts[1] - pts[2])),
        float(np.linalg.norm(pts[2] - pts[3])),
        float(np.linalg.norm(pts[3] - pts[0])),
    ]
    s1 = (sides[0] + sides[2]) / 2.0
    s2 = (sides[1] + sides[3]) / 2.0
    return max(s1, s2), min(s1, s2)
