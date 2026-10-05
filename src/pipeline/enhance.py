from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from src.core.config import EnhancementConfig


class FrameEnhancer:
    def __init__(self, config: EnhancementConfig) -> None:
        self.config = config

    @property
    def active(self) -> bool:
        config = self.config
        if not config.enabled:
            return False
        return config.denoise or config.clahe or (
            config.sharpen and config.sharpen_amount > 0.0
        )

    def apply(self, image: Any) -> Any:
        if not self.active:
            return image

        _require_bgr(image)
        output = image
        if self.config.denoise:
            output = cv2.bilateralFilter(
                output,
                self.config.denoise_diameter,
                self.config.denoise_sigma_color,
                self.config.denoise_sigma_space,
            )
        if self.config.clahe:
            output = _apply_clahe(
                output,
                self.config.clahe_clip_limit,
                (self.config.clahe_grid, self.config.clahe_grid),
            )
        if self.config.sharpen and self.config.sharpen_amount > 0.0:
            output = _unsharp_mask(output, self.config.sharpen_radius, self.config.sharpen_amount)
        return output


def _apply_clahe(image: np.ndarray, clip_limit: float, grid_size: tuple[int, int]) -> np.ndarray:
    if clip_limit <= 0.0:
        return image
    lightness, a_channel, b_channel = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2LAB))
    operator = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    return cv2.cvtColor(
        cv2.merge((operator.apply(lightness), a_channel, b_channel)),
        cv2.COLOR_LAB2BGR,
    )


def _unsharp_mask(image: np.ndarray, radius: float, amount: float) -> np.ndarray:
    if radius <= 0.0:
        return image
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=radius, sigmaY=radius)
    return cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0.0)


def _require_bgr(image: Any) -> None:
    if not isinstance(image, np.ndarray):
        raise TypeError(f"frame must be a numpy array, got {type(image).__name__}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"frame must be a 3-channel BGR image, got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"frame must be uint8, got dtype {image.dtype}")
