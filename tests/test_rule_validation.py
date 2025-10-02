import logging
from pathlib import Path

import pytest

from browser_timeliner.anomaly_detector import AnomalyConfig, AnomalyDetector
from browser_timeliner.models import (
    AnalysisResult,
    Browser,
    HistoryData,
    RuleMatch,
    Session,
    UrlRecord,
    VisitRecord,
)
from browser_timeliner.rule_engine import load_rules_from_file


def _write_tmp_rules(tmp_path: Path, rule_body: str) -> Path:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(rule_body, encoding="utf-8")
    return rules_path


def test_loading_rules_with_unknown_category_raises(tmp_path: Path):
    rules_yaml = """
version: 1
rules:
  - name: Bad Rule
    category: not_a_category
    severity: medium
    description: Test rule
    conditions: {}
"""
    path = _write_tmp_rules(tmp_path, rules_yaml)

    with pytest.raises(ValueError) as exc_info:
        load_rules_from_file(path)

    message = str(exc_info.value)
    assert "unknown category" in message
    assert "not_a_category" in message


def test_anomaly_detector_logs_unknown_category(caplog):
    visit = VisitRecord(
        id=1,
        url_id=1,
        visit_time=None,
        from_visit=None,
        transition=None,
        visit_source=None,
        browser=Browser.CHROMIUM,
    )
    url = UrlRecord(
        id=1,
        url="https://example.com",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=None,
        hidden=False,
        hostname="example.com",
    )
    history = HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={1: url},
        visits=[visit],
    )

    match = RuleMatch(
        rule_name="Test",
        category="unknown_category",
        severity="medium",
        description="",
    )

    detector = AnomalyDetector(AnomalyConfig())

    with caplog.at_level(logging.WARNING):
        anomalies = detector.evaluate(history, sessions=[], rule_matches={1: [match]}, visit_to_session={})

    assert anomalies == []
    assert any("unknown category" in record.message for record in caplog.records)
