"""Anomaly detection heuristics for Browser Timeliner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Dict, List, Optional, Sequence, Set
from uuid import uuid4

from .categories import Category
from .logging_config import get_logger
from .models import Anomaly, HistoryData, RuleMatch, Session, UrlRecord, VisitRecord


@dataclass(slots=True)
class AnomalyConfig:
    suspicious_tlds: Set[str] = frozenset()
    off_hours_start: time = time(hour=0)
    off_hours_end: time = time(hour=6)
    high_session_visit_threshold: int = 25
    high_session_duration_threshold: timedelta = timedelta(minutes=5)
    download_extensions: Set[str] = frozenset({
        "exe",
        "msi",
        "dmg",
        "pkg",
        "ps1",
        "bat",
        "sh",
        "apk",
    })
    high_severity_categories: Set[str] = frozenset({
        Category.REMOTE_ACCESS.value,
        Category.MALWARE.value,
        Category.UNKNOWN.value,
        Category.DOWNLOAD.value,
    })
    ip_address_category: str = Category.IP_ADDRESS.value


class AnomalyDetector:
    """Evaluate visits and sessions to produce anomaly alerts."""

    def __init__(self, config: Optional[AnomalyConfig] = None) -> None:
        self.config = config or AnomalyConfig()
        self.logger = get_logger(__name__)

    def evaluate(
        self,
        history: HistoryData,
        sessions: Sequence[Session],
        rule_matches: Dict[int, List[RuleMatch]],
        visit_to_session: Dict[int, str],
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        # Visit-level heuristics
        for visit in history.visits:
            url = history.urls.get(visit.url_id)
            if url is None:
                continue

            matches = rule_matches.get(visit.id, [])

            if url.tld and url.tld.lower() in self.config.suspicious_tlds:
                anomalies.append(
                    self._create_anomaly(
                        visit_id=visit.id,
                        session_id=visit_to_session.get(visit.id),
                        severity="medium",
                        category=Category.SUSPICIOUS_TLD.value,
                        description=f"URL uses suspicious TLD: {url.tld}",
                        data={"url": url.url},
                    )
                )

            if url.is_ip_address:
                anomalies.append(
                    self._create_anomaly(
                        visit_id=visit.id,
                        session_id=visit_to_session.get(visit.id),
                        severity="medium",
                        category=self.config.ip_address_category,
                        description="Visit to raw IP address",
                        data={"url": url.url},
                    )
                )

            if url.file_extension and url.file_extension.lower() in self.config.download_extensions:
                anomalies.append(
                    self._create_anomaly(
                        visit_id=visit.id,
                        session_id=visit_to_session.get(visit.id),
                        severity="high",
                        category=Category.DOWNLOAD.value,
                        description="Potential file download detected",
                        data={"url": url.url, "extension": url.file_extension.lower()},
                    )
                )

            for match in matches:
                if not Category.has_value(match.category):
                    self.logger.warning(
                        "Encountered rule match with unknown category",
                        extra={
                            "category": match.category,
                            "rule": match.rule_name,
                            "visit_id": visit.id,
                        },
                    )
                    continue
                if match.category == Category.KNOWN_INDICATOR.value:
                    anomalies.append(
                        self._create_anomaly(
                            visit_id=visit.id,
                            session_id=visit_to_session.get(visit.id),
                            severity="high",
                            category=match.category,
                            description="Visit matched known indicator of compromise",
                            data={"rule": match.rule_name},
                        )
                    )
                if match.category in self.config.high_severity_categories:
                    anomalies.append(
                        self._create_anomaly(
                            visit_id=visit.id,
                            session_id=visit_to_session.get(visit.id),
                            severity="high",
                            category=match.category,
                            description="High-risk category triggered",
                            data={"rule": match.rule_name},
                        )
                    )

        # Session-level heuristics
        for session in sessions:
            if any(url.is_ip_address for url in self._session_urls(session, history)):
                anomalies.append(
                    self._create_anomaly(
                        visit_id=None,
                        session_id=session.id,
                        severity="medium",
                        category=self.config.ip_address_category,
                        description="Session includes visits to IP addresses",
                        data={"session_id": session.id},
                    )
                )

        return anomalies

    def _session_urls(self, session: Session, history: HistoryData) -> List[UrlRecord]:
        urls: List[UrlRecord] = []
        for visit in session.visits:
            url = history.urls.get(visit.url_id)
            if url is not None:
                urls.append(url)
        return urls

    def _is_off_hours(self, visit: VisitRecord) -> bool:
        visit_time = visit.visit_time.astimezone()
        visit_clock = visit_time.time()
        start = self.config.off_hours_start
        end = self.config.off_hours_end
        if start <= end:
            return start <= visit_clock < end
        return visit_clock >= start or visit_clock < end

    def _create_anomaly(
        self,
        *,
        visit_id: Optional[int],
        session_id: Optional[str],
        severity: str,
        category: str,
        description: str,
        data: Optional[Dict[str, str]] = None,
    ) -> Anomaly:
        return Anomaly(
            id=str(uuid4()),
            visit_id=visit_id,
            session_id=session_id,
            severity=severity,
            category=category,
            description=description,
            data=data or {},
        )
