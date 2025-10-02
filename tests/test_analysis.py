from datetime import datetime, timezone
from pathlib import Path

from browser_timeliner.analysis import AnalysisOptions, analyze_artifacts
from browser_timeliner.anomaly_detector import AnomalyConfig
from browser_timeliner.categories import Category
from browser_timeliner.models import (
    Browser,
    HistoryData,
    PreferencesData,
    RuleCondition,
    RuleDefinition,
    UrlRecord,
    VisitRecord,
)
from browser_timeliner.rule_engine import RuleSet


def _make_preferences(path: Path) -> PreferencesData:
    return PreferencesData(
        source_path=path,
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


def test_analyze_artifacts_integrates_components(tmp_path):
    visit_time = datetime(2024, 5, 1, 15, 30, tzinfo=timezone.utc)
    url = UrlRecord(
        id=1,
        url="https://indicator.example.com/path",
        title="Indicator",
        visit_count=1,
        typed_count=0,
        last_visit_time=visit_time,
        hostname="indicator.example.com",
        scheme="https",
        tld="com",
        url_base_domain="example.com",
        url_registered_domain="example.com",
        path="/path",
    )
    visit = VisitRecord(
        id=10,
        url_id=url.id,
        visit_time=visit_time,
        from_visit=None,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )

    history = HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={url.id: url},
        visits=[visit],
        downloads=[],
    )
    preferences = _make_preferences(tmp_path / "Preferences")

    rule = RuleDefinition(
        name="IOC Rule",
        category=Category.KNOWN_INDICATOR.value,
        severity="high",
        description="Known indicator trigger",
        conditions=RuleCondition(url_contains={"indicator"}),
    )
    rule_set = RuleSet(rules=(rule,), version=1, metadata={})

    options = AnalysisOptions(rule_set=rule_set, anomaly_config=AnomalyConfig())

    result = analyze_artifacts(history=history, preferences=preferences, options=options)

    assert result.history is history
    assert result.preferences is preferences
    assert result.rules == rule_set.rules

    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert session.seed_visit_id == visit.id
    assert result.visit_to_session[visit.id] == session.id

    assert visit.id in result.rule_matches
    rule_match_names = [match.rule_name for match in result.rule_matches[visit.id]]
    assert "IOC Rule" in rule_match_names

    anomaly_categories = {anomaly.category for anomaly in result.anomalies}
    assert Category.KNOWN_INDICATOR.value in anomaly_categories


def test_analyze_artifacts_without_history_uses_provided_rules(tmp_path):
    rule_set = RuleSet(rules=(), version=1, metadata={})
    preferences = _make_preferences(tmp_path / "Preferences")
    options = AnalysisOptions(rule_set=rule_set, anomaly_config=AnomalyConfig())

    result = analyze_artifacts(history=None, preferences=preferences, options=options)

    assert result.history is None
    assert result.sessions == []
    assert result.anomalies == []
    assert result.rules == rule_set.rules
    assert result.preferences is preferences
