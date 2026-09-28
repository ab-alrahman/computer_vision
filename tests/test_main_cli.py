from __future__ import annotations

import argparse
from unittest import TestCase

from src.main import positive_int, resolve_max_frames


class MainCliTests(TestCase):
    def test_resolve_max_frames_prefers_cli_value(self) -> None:
        self.assertEqual(resolve_max_frames(5, 20, False), 20)

    def test_resolve_max_frames_can_process_all_frames(self) -> None:
        self.assertIsNone(resolve_max_frames(5, 20, True))

    def test_resolve_max_frames_defaults_to_smoke_run(self) -> None:
        self.assertEqual(resolve_max_frames(None, None, False), 5)

    def test_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

