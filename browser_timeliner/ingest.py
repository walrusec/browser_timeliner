"""History and preferences ingestion helpers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional, Tuple

from .chromium_reader import load_history as load_chromium_history
from .firefox_reader import load_history as load_firefox_history
from .logging_config import get_logger
from .models import Browser, HistoryData, PreferencesData
from .preferences_parser import load_preferences
from .utils import validate_sqlite_file


logger = get_logger(__name__)


class UnsupportedHistoryError(Exception):
    """Raised when a database cannot be mapped to a supported browser."""


def detect_browser(path: Path) -> Browser:
    validate_sqlite_file(path)
    logger.debug("Detecting browser", extra={"path": str(path)})
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        cursor = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] if isinstance(row, sqlite3.Row) else row[0] for row in cursor}
    if {"urls", "visits"}.issubset(tables):
        logger.debug("Detected Chromium schema", extra={"path": str(path)})
        return Browser.CHROMIUM
    if {"moz_places", "moz_historyvisits"}.issubset(tables):
        logger.debug("Detected Firefox schema", extra={"path": str(path)})
        return Browser.FIREFOX
    logger.warning("Unrecognized history schema", extra={"path": str(path), "tables": sorted(tables)})
    raise UnsupportedHistoryError(f"Unrecognized history schema for file: {path}")


def load_history_any(path: Path) -> HistoryData:
    browser = detect_browser(path)
    logger.info("Loading history", extra={"path": str(path), "browser": browser.value})
    if browser == Browser.CHROMIUM:
        return load_chromium_history(path)
    if browser == Browser.FIREFOX:
        return load_firefox_history(path)
    raise UnsupportedHistoryError(f"Unsupported browser: {browser}")


def detect_preferences(path: Path) -> bool:
    return path.is_file() and path.name.lower() == "preferences"


def load_inputs(path: Path) -> Tuple[Optional[HistoryData], Optional[PreferencesData]]:
    path = Path(path)
    logger.info("Loading inputs", extra={"path": str(path), "is_dir": path.is_dir()})
    if path.is_dir():
        history_path = None
        preferences_path = None
        for candidate in path.iterdir():
            if not candidate.is_file():
                continue
            if preferences_path is None and detect_preferences(candidate):
                preferences_path = candidate
                continue
            if history_path is None:
                try:
                    detect_browser(candidate)
                except (UnsupportedHistoryError, ValueError, FileNotFoundError):
                    continue
                else:
                    history_path = candidate
                    continue
        history = load_history_any(history_path) if history_path else None
        preferences = load_preferences(preferences_path) if preferences_path else None
        logger.debug(
            "Directory ingestion completed",
            extra={
                "history_found": history_path is not None,
                "preferences_found": preferences_path is not None,
            },
        )
        return history, preferences

    if detect_preferences(path):
        logger.debug("Detected preferences file", extra={"path": str(path)})
        return None, load_preferences(path)

    try:
        history = load_history_any(path)
    except UnsupportedHistoryError:
        logger.exception("Unsupported history file", extra={"path": str(path)})
        raise
    logger.debug("Loaded history file", extra={"path": str(path)})
    return history, None
