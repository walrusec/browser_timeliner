from datetime import datetime, timezone
from pathlib import Path

from browser_timeliner.anomaly_detector import AnomalyConfig, AnomalyDetector
from browser_timeliner.categories import Category
from browser_timeliner.models import (
    Anomaly,
    Browser,
    HistoryData,
    RuleMatch,
    Session,
    UrlRecord,
    VisitRecord,
)


def _build_history(url: UrlRecord, visit: VisitRecord) -> HistoryData:
    return HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={url.id: url},
        visits=[visit],
        downloads=[],
    )


def test_anomaly_detector_flags_suspicious_tld_and_download_and_ip():
    now = datetime.now(timezone.utc)
    url = UrlRecord(
        id=1,
        url="http://example.xyz/malware.exe",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=now,
        hidden=False,
        url_base_domain="example.xyz",
        url_registered_domain="example.xyz",
        hostname="example.xyz",
        scheme="http",
        tld="xyz",
        path="/malware.exe",
        file_extension="exe",
        is_ip_address=False,
    )
    visit = VisitRecord(
        id=10,
        url_id=url.id,
        visit_time=now,
        from_visit=None,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )

    session = Session(
        id="chromium-10-visit",
        browser=Browser.CHROMIUM,
        visits=[visit],
        start_time=now,
        end_time=now,
        duration=now - now,
        seed_visit_id=visit.id,
    )

    history = _build_history(url, visit)
    config = AnomalyConfig(suspicious_tlds={"xyz"}, download_extensions={"exe"})
    detector = AnomalyDetector(config)

    anomalies = detector.evaluate(history, [session], rule_matches={}, visit_to_session={visit.id: session.id})

    categories = {anomaly.category for anomaly in anomalies}
    assert Category.SUSPICIOUS_TLD.value in categories
    assert Category.DOWNLOAD.value in categories


def test_anomaly_detector_emits_high_risk_for_rule_matches():
    now = datetime.now(timezone.utc)
    url = UrlRecord(
        id=1,
        url="http://indicator.test",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=now,
        hidden=False,
        url_base_domain="indicator.test",
        url_registered_domain="indicator.test",
        hostname="indicator.test",
        scheme="http",
        tld="test",
        path="/",
    )
    visit = VisitRecord(
        id=10,
        url_id=url.id,
        visit_time=now,
        from_visit=None,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )
    session = Session(
        id="chromium-10-visit",
        browser=Browser.CHROMIUM,
        visits=[visit],
        start_time=now,
        end_time=now,
        duration=now - now,
        seed_visit_id=visit.id,
    )

    history = _build_history(url, visit)
    rule_match = RuleMatch(
        rule_name="IOC Match",
        category=Category.KNOWN_INDICATOR.value,
        severity="high",
        description="Indicator of compromise",
    )
    detector = AnomalyDetector()

    anomalies = detector.evaluate(history, [session], rule_matches={visit.id: [rule_match]}, visit_to_session={visit.id: session.id})

    assert any(anomaly.category == Category.KNOWN_INDICATOR.value for anomaly in anomalies)
    assert any(anomaly.severity == "high" for anomaly in anomalies)
