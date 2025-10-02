from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from browser_timeliner import cli
from browser_timeliner.models import (
    AnalysisResult,
    Browser,
    HistoryData,
    PreferencesData,
    Session,
)


def _make_history(source_path: Path) -> HistoryData:
    return HistoryData(browser=Browser.CHROMIUM, source_path=source_path, urls={}, visits=[], downloads=[])


def _make_preferences(source_path: Path) -> PreferencesData:
    return PreferencesData(
        source_path=source_path,
        full_name=None,
        email=None,
        language="en-US",
        download_directory=None,
        last_selected_directory=None,
        account_passwords=0,
        profile_passwords=0,
        recent_session_times=[],
        allowed_notification_hosts=[],
        extensions=[],
        proxy_server=None,
        credential_logins_enabled=None,
        last_session_exit_type=None,
    )


def _make_result(history: HistoryData, preferences: PreferencesData) -> AnalysisResult:
    return AnalysisResult(
        history=history,
        sessions=[],
        anomalies=[],
        visit_to_session={},
        rule_matches={},
        rules=(),
        preferences=preferences,
    )


def test_cli_filters_passed_to_export(monkeypatch, tmp_path):
    input_dir = tmp_path / "profile"
    input_dir.mkdir()
    prefs_path = input_dir / "Preferences"
    prefs_path.write_text("{}", encoding="utf-8")

    history = _make_history(input_dir)
    preferences = _make_preferences(prefs_path)

    def fake_load_inputs(path: Path):
        assert path == input_dir
        return history, preferences

    def fake_analyze_artifacts(*, history, preferences, options):
        return _make_result(history, preferences)

    captured = {}

    def fake_write_result_export(result, path, format_key, *, filters=None):
        captured["filters"] = filters

    monkeypatch.setattr(cli, "load_inputs", fake_load_inputs)
    monkeypatch.setattr(cli, "analyze_artifacts", fake_analyze_artifacts)
    monkeypatch.setattr(cli, "write_result_export", fake_write_result_export)
    monkeypatch.setattr(cli, "write_preferences_export", lambda *args, **kwargs: None)

    export_target = tmp_path / "timeline.csv"
    exit_code = cli.main([
        str(input_dir),
        "--summary-only",
        "--export",
        str(export_target),
        "--filter",
        "anomalies",
    ])

    assert exit_code == 0
    assert captured["filters"] == ["anomalies"]


def test_cli_accepts_zip_input(monkeypatch, tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "Preferences").write_text("{}", encoding="utf-8")

    zip_path = tmp_path / "profile.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(profile_dir / "Preferences", arcname="Preferences")

    expected_history = _make_history(profile_dir)
    expected_preferences = _make_preferences(profile_dir / "Preferences")

    captured = {}

    def fake_load_inputs(path: Path):
        captured["path"] = path
        return expected_history, expected_preferences

    def fake_analyze_artifacts(*, history, preferences, options):
        return _make_result(history, preferences)

    monkeypatch.setattr(cli, "load_inputs", fake_load_inputs)
    monkeypatch.setattr(cli, "analyze_artifacts", fake_analyze_artifacts)
    monkeypatch.setattr(cli, "write_result_export", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "write_preferences_export", lambda *args, **kwargs: None)

    exit_code = cli.main([
        str(zip_path),
        "--summary-only",
        "--export",
        str(tmp_path / "timeline.csv"),
    ])

    assert exit_code == 0
    extracted_path = captured["path"]
    assert extracted_path != zip_path
    assert extracted_path.name.startswith("browser_timeliner_zip_")
