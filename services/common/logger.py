"""Centralized structured logging engine for the SOA Hybrid RAG platform.

Provides colorized console output and rotating file logging with structured
metadata support (service name, document ID, duration_ms, and status).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Ensure logs directory exists
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ANSI Color Codes for Windows / POSIX terminals
COLOR_RESET = "\033[0m"
COLOR_DEBUG = "\033[36m"     # Cyan
COLOR_INFO = "\033[32m"      # Green
COLOR_WARNING = "\033[33m"   # Yellow
COLOR_ERROR = "\033[31m"     # Red
COLOR_CRITICAL = "\033[1;31m" # Bold Red
COLOR_GREY = "\033[90m"      # Grey for timestamp & metadata


class ColoredFormatter(logging.Formatter):
    """Custom formatter providing ANSI colors for terminal log outputs."""

    LEVEL_COLORS = {
        logging.DEBUG: COLOR_DEBUG,
        logging.INFO: COLOR_INFO,
        logging.WARNING: COLOR_WARNING,
        logging.ERROR: COLOR_ERROR,
        logging.CRITICAL: COLOR_CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.LEVEL_COLORS.get(record.levelno, COLOR_RESET)
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        record_msg = record.getMessage()

        # Extra metadata if provided via extra={"extra_meta": ...}
        extra_info = getattr(record, "extra_meta", None)
        meta_str = f" {COLOR_GREY}[{extra_info}]{COLOR_RESET}" if extra_info else ""

        return (
            f"{COLOR_GREY}[{timestamp}]{COLOR_RESET} "
            f"{level_color}[{record.levelname:<8}]{COLOR_RESET} "
            f"[{record.name}] {record_msg}{meta_str}"
        )


def setup_logger(
    name: str = "rag",
    log_level: int = logging.INFO,
    service_log_filename: str | None = None,
) -> logging.Logger:
    """Configures and returns a logger instance with console and rotating file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup is called repeatedly
    if logger.handlers:
        return logger

    # 1. Console Handler (Colored)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # 2. Global Rotating File Handler (10 MB per file, max 5 backups)
    global_log_path = LOGS_DIR / "rag_system.log"
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    global_file_handler = RotatingFileHandler(
        global_log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    global_file_handler.setLevel(log_level)
    global_file_handler.setFormatter(file_formatter)
    logger.addHandler(global_file_handler)

    # 3. Optional Service-Specific File Handler
    if service_log_filename:
        service_log_path = LOGS_DIR / service_log_filename
        service_file_handler = RotatingFileHandler(
            service_log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        service_file_handler.setLevel(log_level)
        service_file_handler.setFormatter(file_formatter)
        logger.addHandler(service_file_handler)

    return logger


def get_logger(service_name: str) -> logging.Logger:
    """Convenience getter for a scoped service logger."""
    return setup_logger(f"rag.{service_name}", service_log_filename=f"{service_name}.log")
