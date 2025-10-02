"""Utility helpers for Browser Timeliner."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Iterable, Mapping, Sequence

from . import constants


SQLITE_HEADER_PREFIX = b"SQLite format 3\x00"


def chromium_timestamp_to_datetime(microseconds: int) -> datetime:
    """Convert Chromium/Webkit timestamp to timezone-aware datetime."""

    unix_us = microseconds - constants.CHROMIUM_EPOCH_OFFSET_MICROSECONDS
    return datetime.fromtimestamp(unix_us / 1_000_000, tz=timezone.utc)


def firefox_timestamp_to_datetime(microseconds: int) -> datetime:
    """Firefox history uses microseconds since UNIX epoch."""

    return datetime.fromtimestamp(microseconds / 1_000_000, tz=timezone.utc)


def validate_sqlite_file(path: Path) -> None:
    """Ensure the provided path appears to be a SQLite database."""

    if not path.exists():
        raise FileNotFoundError(f"History database not found: {path}")
    if not path.is_file():
        raise ValueError(f"Expected a file but found directory: {path}")
    with path.open("rb") as handle:
        header = handle.read(len(SQLITE_HEADER_PREFIX))
    if header != SQLITE_HEADER_PREFIX:
        raise ValueError(f"File does not appear to be a SQLite database: {path}")


def ensure_copy(source_path: Path, target_dir: Path) -> Path:
    """Return a safe copy of the database file to avoid locking issues."""

    validate_sqlite_file(source_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source_path.name
    shutil.copy2(source_path, target_path)
    wal = source_path.with_name(source_path.name + "-wal")
    if wal.exists():
        shutil.copy2(wal, target_path.with_name(target_path.name + "-wal"))
    shm = source_path.with_name(source_path.name + "-shm")
    if shm.exists():
        shutil.copy2(shm, target_path.with_name(target_path.name + "-shm"))
    return target_path


def serialize_dataclass(obj) -> dict:
    """Serialize dataclass to plain dict for JSON exports."""

    return asdict(obj)
