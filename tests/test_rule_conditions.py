from datetime import datetime

from browser_timeliner.models import Browser, RuleCondition, UrlRecord, VisitRecord


def _build_visit(url_id: int) -> VisitRecord:
    return VisitRecord(
        id=1,
        url_id=url_id,
        visit_time=datetime(2024, 1, 1, 12, 0, 0),
        from_visit=None,
        transition=None,
        visit_source=None,
        browser=Browser.CHROMIUM,
    )


def test_unicode_rule_requires_unicode_domain():
    condition = RuleCondition(contains_unicode=True, mixed_scripts=True)

    ascii_url = UrlRecord(
        id=1,
        url="https://example.com",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=datetime(2024, 1, 1, 12, 0, 0),
        hidden=False,
        hostname="example.com",
        scheme="https",
    )

    unicode_url = UrlRecord(
        id=2,
        url="https://例example.com",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=datetime(2024, 1, 1, 12, 0, 0),
        hidden=False,
        hostname="例example.com",
        scheme="https",
    )

    assert condition.matches(ascii_url, _build_visit(ascii_url.id), []) is None

    unicode_match = condition.matches(unicode_url, _build_visit(unicode_url.id), [])
    assert unicode_match is not None
    assert unicode_match["contains_unicode"] == "true"
    assert unicode_match["mixed_scripts"] == "true"


def test_ip_range_rule_matches_only_included_ranges():
    condition = RuleCondition(ip_ranges=("192.168.0.0/16",))

    lan_url = UrlRecord(
        id=3,
        url="http://192.168.1.10",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=datetime(2024, 1, 1, 12, 0, 0),
        hidden=False,
        hostname="192.168.1.10",
        scheme="http",
        is_ip_address=True,
    )

    public_ip_url = UrlRecord(
        id=4,
        url="http://8.8.8.8",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=datetime(2024, 1, 1, 12, 0, 0),
        hidden=False,
        hostname="8.8.8.8",
        scheme="http",
        is_ip_address=True,
    )

    lan_match = condition.matches(lan_url, _build_visit(lan_url.id), [])
    assert lan_match is not None
    assert lan_match["ip_range"] == "192.168.0.0/16"

    assert condition.matches(public_ip_url, _build_visit(public_ip_url.id), []) is None
