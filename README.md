# RealSense D435 3D Measurement Pipeline

End-to-end project for:

`webcam -> camera calibration -> ArUco scale detection -> contour object detection -> pixel-mm conversion -> dimension extraction -> database comparison -> output report`

This implementation uses:
- Intel RealSense D435 (`pyrealsense2`)
- OpenCV ArUco (`DICT_4X4_50`, marker IDs `0,1,2,3`)
- 50 mm physical marker size and 200 mm marker-to-marker spacing
- SQLite for reference-dimension comparison
- JSON + PDF output reports with 3D model image

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 1.1) Full-stack setup (React + FastAPI)

Backend:

```bash
source .venv/bin/activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Or run both with one command:

```bash
./run_fullstack.sh
```

## 2) Generate ArUco markers (IDs 0-3)

```bash
PYTHONPATH=src python src/generate_aruco_markers.py
```

Markers are saved to `data/aruco_markers/`.

Important: print each marker so its black square side is exactly **50.0 mm**.

## 3) Camera calibration

Capture chessboard images and put them in `data/calibration/images/`.

Then run:

```bash
PYTHONPATH=src python src/main.py calibrate \
  --calibration-images data/calibration/images \
  --calibration-output data/calibration/camera_calibration.npz \
  --chess-cols 9 --chess-rows 6 --square-size-mm 25
```

## 4) Add reference object (for comparison)

```bash
PYTHONPATH=src python src/main.py run \
  --add-reference BOX_A 120 80 40 1.0
```

Format:

`--add-reference NAME LENGTH_MM WIDTH_MM HEIGHT_MM TOLERANCE_MM`

## 5) Run live measurement

```bash
PYTHONPATH=src python src/main.py run \
  --calibration-file data/calibration/camera_calibration.npz \
  --reference-name BOX_A \
  --live
```

Notes:
- Place ArUco IDs 0,1,2,3 around the measurement zone in this order:
  - ID 0: top-left
  - ID 1: top-right
  - ID 2: bottom-right
  - ID 3: bottom-left
- Keep adjacent marker centers at **200 mm (20 cm)** spacing.
- Place object inside marker area.
- Keep object base on a flat plane background.
- In live mode:
  - Press `s` to save report for current stable frame
  - Press `q` to quit

Single-frame mode (no preview) is also supported:

```bash
PYTHONPATH=src python src/main.py run \
  --calibration-file data/calibration/camera_calibration.npz \
  --reference-name BOX_A
```

## Outputs

Saved in `data/reports/`:
- `measurement_report_<timestamp>.json`
- `measurement_report_<timestamp>.pdf`
- `object_3d_model_<timestamp>.png`
- `debug_original_markers.png`
- `debug_workspace_contour.png`

## React Dashboard Flow

- Click **Part Identification**
- Click **Run Identification** (starts backend live loop)
- Live feed appears in the dashboard (`workspace` or `original` view)
- Click **Press S** (or keyboard `S`) to generate report
- Click **Press Q** (or keyboard `Q`) to generate report and stop session
- Generated reports appear in dashboard report history with:
  - PDF link
  - JSON link
  - 3D model image link

## Project structure

```text
.
├── config.yaml
├── requirements.txt
├── data/
│   ├── calibration/
│   ├── db/
│   └── reports/
├── backend/
│   └── app.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       └── AWTOApp.jsx
├── run_fullstack.sh
└── src/
    ├── main.py
    ├── calibration.py
    ├── realsense_capture.py
    ├── aruco_scale.py
    ├── contour_detection.py
    ├── measurement.py
    ├── model_3d.py
    ├── database.py
    ├── report.py
    └── generate_aruco_markers.py
```

## Practical accuracy tips

- Use stable diffuse lighting and avoid shadows on markers.
- Keep marker plane and object base on the same flat surface.
- Use multiple frames and average if you need sub-mm stability.
- Keep camera fixed (tripod/rig) after calibration.
