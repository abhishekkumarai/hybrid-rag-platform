from __future__ import annotations

import os
from pathlib import Path

import pytesseract
from dotenv import load_dotenv
from pytesseract import TesseractNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def configure_tesseract() -> str:
    """Load the project .env and point pytesseract at the installed binary."""
    load_dotenv(PROJECT_ROOT / ".env")

    configured_path = os.getenv("TESSERACT_CMD")
    candidate_paths = [Path(configured_path)] if configured_path else []
    candidate_paths.extend(DEFAULT_TESSERACT_PATHS)

    for candidate in candidate_paths:
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return str(candidate)

    searched_paths = ", ".join(str(path) for path in candidate_paths) or "PATH"
    raise TesseractNotFoundError(
        f"Tesseract executable was not found. Checked: {searched_paths}"
    )


def get_tesseract_version() -> str:
    """Return the installed Tesseract version after configuration."""
    configure_tesseract()
    return str(pytesseract.get_tesseract_version())
