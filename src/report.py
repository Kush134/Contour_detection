from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from database import ComparisonResult
from measurement import ObjectMeasurement


def save_json_report(
    output_dir: Path,
    measurement: ObjectMeasurement,
    comparison: ComparisonResult | None,
    metadata: Dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"measurement_report_{ts}.json"

    payload = {
        "timestamp": ts,
        "measurement": asdict(measurement),
        "comparison": asdict(comparison) if comparison else None,
        "metadata": metadata,
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def save_pdf_report(
    output_dir: Path,
    measurement: ObjectMeasurement,
    comparison: ComparisonResult | None,
    metadata: Dict[str, Any],
    model_image_path: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"measurement_report_{ts}.pdf"

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "3D Measurement Report")

    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Timestamp: {ts}")

    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Measured Dimensions")

    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(60, y, f"Length: {measurement.length_mm:.2f} mm")
    y -= 16
    c.drawString(60, y, f"Width: {measurement.width_mm:.2f} mm")
    y -= 16
    c.drawString(60, y, f"Height: {measurement.height_mm:.2f} mm")
    y -= 16
    c.drawString(60, y, f"Area: {measurement.area_mm2:.2f} mm^2")
    y -= 16
    c.drawString(60, y, f"Volume: {measurement.volume_mm3:.2f} mm^3")

    if comparison:
        y -= 24
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Database Comparison")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(60, y, f"Reference: {comparison.reference_name}")
        y -= 16
        c.drawString(60, y, f"Tolerance: +/-{comparison.tolerance_mm:.2f} mm")
        y -= 16
        c.drawString(60, y, f"Length delta: {comparison.length_diff_mm:.2f} mm")
        y -= 16
        c.drawString(60, y, f"Width delta: {comparison.width_diff_mm:.2f} mm")
        y -= 16
        c.drawString(60, y, f"Height delta: {comparison.height_diff_mm:.2f} mm")
        y -= 16
        c.drawString(60, y, f"Result: {'PASS' if comparison.passed else 'FAIL'}")

    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Metadata")

    c.setFont("Helvetica", 10)
    for key, value in metadata.items():
        y -= 14
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)
        c.drawString(60, y, f"{key}: {value}")

    if model_image_path is not None and model_image_path.exists():
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, "3D Model Preview")
        img_reader = ImageReader(str(model_image_path))

        img_width = width - 100
        img_height = img_width * 0.75
        c.drawImage(img_reader, 50, height - img_height - 110, width=img_width, height=img_height, preserveAspectRatio=True)

    c.save()
    return out_path
