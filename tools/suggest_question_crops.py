#!/usr/bin/env python
"""Compatibility wrapper for the package OCR crop suggestion CLI."""

from __future__ import annotations

from leet_practice.ocr_crops import *  # noqa: F403
from leet_practice.ocr_crops import main


if __name__ == "__main__":
    raise SystemExit(main())
