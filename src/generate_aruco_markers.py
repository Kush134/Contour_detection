from __future__ import annotations

from pathlib import Path

import cv2


def main() -> None:
    out_dir = Path("data/aruco_markers")
    out_dir.mkdir(parents=True, exist_ok=True)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    px_size = 600
    for marker_id in [0, 1, 2, 3]:
        img = cv2.aruco.generateImageMarker(dictionary, marker_id, px_size)
        out_path = out_dir / f"aruco_4x4_50_id_{marker_id}.png"
        cv2.imwrite(str(out_path), img)
        print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
