from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from measurement import ObjectMeasurement


@dataclass
class ComparisonResult:
    reference_name: str
    tolerance_mm: float
    length_diff_mm: float
    width_diff_mm: float
    height_diff_mm: float
    passed: bool


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reference_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                length_mm REAL NOT NULL,
                width_mm REAL NOT NULL,
                height_mm REAL NOT NULL,
                tolerance_mm REAL NOT NULL DEFAULT 1.0
            )
            """
        )
    conn.close()


def upsert_reference(
    db_path: Path,
    name: str,
    length_mm: float,
    width_mm: float,
    height_mm: float,
    tolerance_mm: float = 1.0,
) -> None:
    conn = sqlite3.connect(str(db_path))
    with conn:
        conn.execute(
            """
            INSERT INTO reference_objects (name, length_mm, width_mm, height_mm, tolerance_mm)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                length_mm=excluded.length_mm,
                width_mm=excluded.width_mm,
                height_mm=excluded.height_mm,
                tolerance_mm=excluded.tolerance_mm
            """,
            (name, length_mm, width_mm, height_mm, tolerance_mm),
        )
    conn.close()


def compare_with_reference(
    db_path: Path,
    reference_name: str,
    measurement: ObjectMeasurement,
) -> ComparisonResult:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        """
        SELECT length_mm, width_mm, height_mm, tolerance_mm
        FROM reference_objects
        WHERE name = ?
        """,
        (reference_name,),
    ).fetchone()
    conn.close()

    if row is None:
        raise RuntimeError(f"Reference '{reference_name}' not found in database.")

    ref_len, ref_wid, ref_hgt, tol = row
    d_len = measurement.length_mm - ref_len
    d_wid = measurement.width_mm - ref_wid
    d_hgt = measurement.height_mm - ref_hgt

    passed = all(abs(d) <= tol for d in (d_len, d_wid, d_hgt))

    return ComparisonResult(
        reference_name=reference_name,
        tolerance_mm=float(tol),
        length_diff_mm=float(d_len),
        width_diff_mm=float(d_wid),
        height_diff_mm=float(d_hgt),
        passed=bool(passed),
    )
