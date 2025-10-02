import json
import sqlite3
from pathlib import Path

import pytest

from browser_timeliner.ingest import detect_preferences, load_inputs


def _write_preferences(path: Path) -> Path:
    data = {
        "profile": {},
    }
    target = path / "Preferences"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def _write_chromium_history(path: Path) -> Path:
    db_path = path / "History"
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER,
                typed_count INTEGER,
                last_visit_time INTEGER,
                hidden INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE visits (
                id INTEGER PRIMARY KEY,
                url INTEGER,
                visit_time INTEGER,
                from_visit INTEGER,
                transition INTEGER,
                visit_duration INTEGER,
                external_referrer_url TEXT,
                opener_visit INTEGER
            )
            """
        )
        cur.execute(
            "INSERT INTO urls (id, url, title, visit_count, typed_count, last_visit_time, hidden) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "https://example.com", "Example", 1, 0, 0, 0),
        )
        cur.execute(
            "INSERT INTO visits (id, url, visit_time, from_visit, transition, visit_duration, external_referrer_url, opener_visit) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 1, 0, None, 1, 0, None, None),
        )
        con.commit()
    return db_path


def test_detect_preferences(tmp_path):
    pref_path = _write_preferences(tmp_path)
    assert detect_preferences(pref_path) is True
    assert detect_preferences(tmp_path / "Other") is False


def test_load_inputs_with_directory(tmp_path):
    history_path = _write_chromium_history(tmp_path)
    preferences_path = _write_preferences(tmp_path)

    history, preferences = load_inputs(tmp_path)

    assert history is not None
    assert preferences is not None
    assert history.source_path == history_path
    assert preferences.source_path == preferences_path


def test_load_inputs_preferences_only(tmp_path):
    pref_path = _write_preferences(tmp_path)
    history, preferences = load_inputs(pref_path)

    assert history is None
    assert preferences is not None
