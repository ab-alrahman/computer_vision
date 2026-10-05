from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

import numpy as np

from src.core.config import load_config
from src.pipeline.enhance import FrameEnhancer


def _config(**overrides) -> object:
    config = load_config("configs/default.yaml").enhancement
    return replace(config, **overrides)


class FrameEnhancerTests(TestCase):
    def test_preserves_shape_and_dtype(self) -> None:
        frame = np.random.default_rng(7).integers(0, 256, (48, 64, 3), dtype=np.uint8)

        enhanced = FrameEnhancer(_config()).apply(frame)

        self.assertEqual(enhanced.shape, frame.shape)
        self.assertEqual(enhanced.dtype, np.uint8)

    def test_does_not_mutate_the_source_frame(self) -> None:
        frame = np.random.default_rng(11).integers(0, 256, (32, 32, 3), dtype=np.uint8)
        original = frame.copy()

        FrameEnhancer(_config()).apply(frame)

        self.assertTrue(np.array_equal(frame, original))

    def test_dark_frame_gains_contrast(self) -> None:
        dark = np.full((64, 64, 3), 60, dtype=np.uint8)
        dark[24:40, 24:40] = 75

        enhanced = FrameEnhancer(_config(sharpen=False)).apply(dark)
        spread_before = float(dark.max()) - float(dark.min())
        spread_after = float(enhanced.max()) - float(enhanced.min())

        self.assertGreater(spread_after, spread_before)

    def test_sharpen_increases_local_edge_strength(self) -> None:
        flat = np.full((64, 64, 3), 120, dtype=np.uint8)
        flat[:, 32:] = 130

        soft = FrameEnhancer(_config(sharpen=False)).apply(flat)
        sharp = FrameEnhancer(_config(sharpen=True)).apply(flat)

        def edge_strength(image: np.ndarray) -> float:
            return float(np.abs(np.diff(image[:, :, 0].astype(int), axis=1)).max())

        self.assertGreater(edge_strength(sharp), edge_strength(soft))

    def test_disabled_enhancer_returns_the_same_object(self) -> None:
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        enhanced = FrameEnhancer(_config(enabled=False)).apply(frame)

        self.assertIs(enhanced, frame)

    def test_all_stages_off_is_inactive(self) -> None:
        enhancer = FrameEnhancer(_config(denoise=False, clahe=False, sharpen=False))

        self.assertFalse(enhancer.active)

    def test_rejects_non_bgr_frames(self) -> None:
        enhancer = FrameEnhancer(_config())

        with self.assertRaises(ValueError):
            enhancer.apply(np.zeros((16, 16), dtype=np.uint8))
