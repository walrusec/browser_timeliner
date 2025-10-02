from datetime import datetime, timezone
from pathlib import Path

import pytest

from browser_timeliner.categories import Category
from browser_timeliner.models import (
    Browser,
    HistoryData,
    RuleCondition,
    RuleDefinition,
    RuleMatch,
    UrlRecord,
    VisitRecord,
)
from browser_timeliner.rule_engine import RuleEngine, RuleSet, _parse_rule_entry


def _build_history(url: UrlRecord, visit: VisitRecord) -> HistoryData:
    return HistoryData(
        browser=Browser.CHROMIUM,
        source_path=Path("history.db"),
        urls={url.id: url},
        visits=[visit],
        downloads=[],
    )


def test_rule_engine_matches_visit_when_condition_satisfied():
    now = datetime.now(timezone.utc)
    url = UrlRecord(
        id=1,
        url="https://example.com/phishing",
        title=None,
        visit_count=1,
        typed_count=0,
        last_visit_time=now,
        hidden=False,
        url_base_domain="example.com",
        url_registered_domain="example.com",
        hostname="example.com",
        scheme="https",
        tld="com",
        path="/phishing",
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

    rule = RuleDefinition(
        name="Phishing URL",
        category=Category.THREAT_INDICATOR.value,
        severity="high",
        description="URLs containing phishing keyword",
        conditions=RuleCondition(url_contains={"phishing"}),
    )

    history = _build_history(url, visit)
    engine = RuleEngine(RuleSet(rules=(rule,), version=1, metadata={}))

    matches = engine.evaluate(history)

    assert visit.id in matches
    assert isinstance(matches[visit.id][0], RuleMatch)
    assert matches[visit.id][0].rule_name == "Phishing URL"


def test_parse_rule_entry_raises_for_unknown_category():
    with pytest.raises(ValueError):
        _parse_rule_entry(
            {
                "name": "Bad Category",
                "category": "nonexistent_category",
                "conditions": {},
            }
        )
