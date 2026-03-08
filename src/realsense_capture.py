from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:  # pragma: no cover - hardware dependency
    rs = None


@dataclass
class FrameBundle:
    color: np.ndarray
    depth: np.ndarray
    depth_scale: float


class RealSenseCamera:
    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        align_depth_to_color: bool = True,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.align_depth_to_color = align_depth_to_color

        self.pipeline: Optional[rs.pipeline] = None
        self.config: Optional[rs.config] = None
        self.align: Optional[rs.align] = None
        self.depth_scale: float = 0.001

    def start(self) -> None:
        if rs is None:
            raise ImportError(
                "pyrealsense2 is required for camera capture. Install Intel RealSense SDK and `pip install pyrealsense2`."
            )
        self.pipeline = rs.pipeline()
        self.config = rs.config()

        self.config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        self.config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)

        profile = self.pipeline.start(self.config)
        depth_sensor = profile.get_device().first_depth_sensor()
        self.depth_scale = depth_sensor.get_depth_scale()

        if self.align_depth_to_color:
            self.align = rs.align(rs.stream.color)

    def get_frames(self) -> FrameBundle:
        if self.pipeline is None:
            raise RuntimeError("Camera not started. Call start() first.")

        frames = self.pipeline.wait_for_frames()

        if self.align is not None:
            frames = self.align.process(frames)

        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError("Failed to retrieve color/depth frames.")

        color = np.asanyarray(color_frame.get_data())
        depth = np.asanyarray(depth_frame.get_data())

        return FrameBundle(color=color, depth=depth, depth_scale=self.depth_scale)

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None
