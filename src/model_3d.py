from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from measurement import ObjectMeasurement


def _cuboid_vertices(length: float, width: float, height: float) -> np.ndarray:
    return np.array(
        [
            [0, 0, 0],
            [length, 0, 0],
            [length, width, 0],
            [0, width, 0],
            [0, 0, height],
            [length, 0, height],
            [length, width, height],
            [0, width, height],
        ],
        dtype=np.float32,
    )


def render_box_model(measurement: ObjectMeasurement, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"object_3d_model_{ts}.png"

    length = max(measurement.length_mm, 1.0)
    width = max(measurement.width_mm, 1.0)
    height = max(measurement.height_mm, 1.0)

    vertices = _cuboid_vertices(length, width, height)
    faces_idx = [
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]
    faces = [[vertices[i] for i in f] for f in faces_idx]

    fig = plt.figure(figsize=(8, 6), dpi=160)
    ax = fig.add_subplot(111, projection="3d")

    poly = Poly3DCollection(faces, alpha=0.5, facecolor="#2f6690", edgecolor="#0d1b2a", linewidth=1.2)
    ax.add_collection3d(poly)

    max_dim = max(length, width, height)
    ax.set_xlim(0, max_dim)
    ax.set_ylim(0, max_dim)
    ax.set_zlim(0, max_dim)

    ax.set_xlabel("Length (mm)")
    ax.set_ylabel("Width (mm)")
    ax.set_zlabel("Height (mm)")
    ax.set_title(
        f"Measured Box: {length:.1f} x {width:.1f} x {height:.1f} mm",
        pad=18,
    )
    ax.view_init(elev=24, azim=40)

    plt.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)

    return out_path
