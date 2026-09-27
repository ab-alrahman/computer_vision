from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import cv2
import numpy as np

from src.pipeline.source import VideoSource


class VideoSourceTests(TestCase):
    def test_reads_frames_with_index_and_timestamp(self) -> None:
        with TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "sample.mp4"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                10.0,
                (32, 24),
            )
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
            writer.write(np.full((24, 32, 3), 255, dtype=np.uint8))
            writer.release()

            with VideoSource(video_path) as source:
                frames = list(source.frames(max_frames=2))

            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0].frame_index, 0)
            self.assertEqual(frames[1].frame_index, 1)
            self.assertEqual(frames[0].image.shape, (24, 32, 3))

