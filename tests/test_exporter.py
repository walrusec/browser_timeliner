from datetime import datetime, timedelta, timezone
from pathlib import Path

from browser_timeliner.exporter import RESULT_EXPORT_COLUMNS, build_result_rows, result_to_dict
from browser_timeliner.models import (
    AnalysisResult,
    Anomaly,
    Browser,
    DownloadRecord,
    HistoryData,
    RuleMatch,
    Session,
    UrlRecord,
    VisitRecord,
)


def _build_sample_analysis_result() -> AnalysisResult:
    visit_time = datetime(2024, 5, 1, 15, 30)
    url = UrlRecord(
        id=1,
        url="https://example.com/path",
        title="Example",
        visit_count=1,
        typed_count=0,
        last_visit_time=visit_time,
        hidden=False,
    )

    visit = VisitRecord(
        id=100,
        url_id=url.id,
        visit_time=visit_time,
        from_visit=None,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )

    session = Session(
        id="session-1",
        browser=Browser.CHROMIUM,
        visits=[visit],
        start_time=visit_time,
        end_time=visit_time + timedelta(minutes=1),
        duration=timedelta(minutes=1),
        seed_visit_id=visit.id,
    )

    anomaly = Anomaly(
        id="anomaly-1",
        visit_id=visit.id,
        session_id=session.id,
        severity="medium",
        category="test-category",
        description="Test anomaly",
    )

    rule_match = RuleMatch(
        rule_name="Test Rule",
        category="test-category",
        severity="medium",
        description="Rule match",
        metadata={"example": "value"},
    )

    history = HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={url.id: url},
        visits=[visit],
        downloads=[],
    )

    return AnalysisResult(
        history=history,
        sessions=[session],
        anomalies=[anomaly],
        visit_to_session={visit.id: session.id},
        rule_matches={visit.id: [rule_match]},
        rules=(),
        preferences=None,
    )


def test_result_to_dict_includes_sessions_anomalies_and_mapping():
    result = _build_sample_analysis_result()

    payload = result_to_dict(result)

    assert "history" in payload
    history_payload = payload["history"]
    assert history_payload is not None
    assert history_payload["sessions"][0]["visits"][0]["visit_id"] == 100
    assert history_payload["anomalies"][0]["id"] == "anomaly-1"
    assert history_payload["visit_to_session"] == {100: "session-1"}
    assert payload["preferences"] is None
    assert payload["rules"] == []


def test_result_export_columns_schema_matches_spec():
    expected = (
        "visit_time",
        "visit_title",
        "visit_url",
        "record_type",
        "download_received_bytes",
        "download_total_bytes",
        "download_tab_url",
        "download_referrer_url",
        "rule_names",
        "rule_severities",
        "rule_categories",
        "rule_tags",
        "rule_descriptions",
        "anomaly_ids",
        "anomaly_severities",
        "anomaly_categories",
        "anomaly_descriptions",
        "session_id",
        "session_browser",
        "session_start",
        "session_end",
        "session_duration_minutes",
        "session_tags",
        "session_notes",
        "visit_id",
        "host",
        "path",
        "query",
        "tld",
        "registered_domain",
        "was_ip",
    )
    assert RESULT_EXPORT_COLUMNS == expected


def test_build_result_rows_includes_visits_and_downloads():
    visit_time = datetime(2024, 5, 1, 15, 30, tzinfo=timezone.utc)
    download_time = datetime(2024, 5, 1, 15, 45, tzinfo=timezone.utc)

    url = UrlRecord(
        id=1,
        url="https://example.com/path",
        title="Example",
        visit_count=1,
        typed_count=0,
        last_visit_time=visit_time,
        hidden=False,
    )

    visit = VisitRecord(
        id=100,
        url_id=url.id,
        visit_time=visit_time,
        from_visit=None,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )

    session = Session(
        id="session-1",
        browser=Browser.CHROMIUM,
        visits=[visit],
        start_time=visit_time,
        end_time=visit_time + timedelta(minutes=1),
        duration=timedelta(minutes=1),
        seed_visit_id=visit.id,
    )

    download = DownloadRecord(
        id=200,
        url="https://example.com/download.bin",
        tab_url=None,
        tab_referrer_url=None,
        target_path="/tmp/download.bin",
        start_time=download_time,
        end_time=download_time,
        danger_type=None,
        interrupt_reason=None,
        received_bytes=50,
        total_bytes=100,
    )

    history = HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={url.id: url},
        visits=[visit],
        downloads=[download],
    )

    result = AnalysisResult(
        history=history,
        sessions=[session],
        anomalies=[],
        visit_to_session={visit.id: session.id},
        rule_matches={visit.id: []},
        rules=(),
        preferences=None,
    )

    rows = build_result_rows(result)

    assert len(rows) == 2

    visit_row = next(row for row in rows if row["record_type"] == "visit")
    download_row = next(row for row in rows if row["record_type"] == "download")

    assert visit_row["session_id"] == "session-1"
    assert visit_row["download_received_bytes"] == ""
    assert visit_row["visit_id"] == "100"
    assert visit_row["download_tab_url"] == ""
    assert visit_row["download_referrer_url"] == ""

    assert download_row["session_id"] == ""
    assert download_row["download_received_bytes"] == "50"
    assert download_row["download_total_bytes"] == "100"
    assert download_row["visit_id"] == "200"
    assert download_row["download_tab_url"] == ""
    assert download_row["download_referrer_url"] == ""
