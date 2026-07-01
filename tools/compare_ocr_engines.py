#!/usr/bin/env python
"""Compatibility wrapper for the package OCR comparison CLI."""

from __future__ import annotations

from leet_practice.compare_ocr_engines import *  # noqa: F403
from leet_practice.compare_ocr_engines import main


if __name__ == "__main__":
    raise SystemExit(main())
