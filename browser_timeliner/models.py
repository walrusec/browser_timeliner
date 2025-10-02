"""Core data models for Browser Timeliner."""

from __future__ import annotations

import ipaddress
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


class Browser(str, Enum):
    """Supported browser families."""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"


@dataclass(slots=True)
class UrlRecord:
    """Represents a URL entry from the browser history."""

    id: int
    url: str
    title: Optional[str]
    visit_count: int
    typed_count: int
    last_visit_time: Optional[datetime]
    hidden: bool = False
    url_base_domain: Optional[str] = None
    url_registered_domain: Optional[str] = None
    hostname: Optional[str] = None
    scheme: Optional[str] = None
    tld: Optional[str] = None
    is_ip_address: bool = False
    path: Optional[str] = None
    query: Optional[str] = None
    file_extension: Optional[str] = None
    categories: Set[str] = field(default_factory=set)


@dataclass(slots=True)
class VisitRecord:
    """Represents an individual visit (navigation event)."""

    id: int
    url_id: int
    visit_time: datetime
    from_visit: Optional[int]
    transition: Optional[str]
    visit_source: Optional[str]
    browser: Browser
    visit_duration: Optional[timedelta] = None
    referring_visit_id: Optional[int] = None
    external_referrer_url: Optional[str] = None


@dataclass(slots=True)
class SearchTerm:
    """Associates keyword search terms with URL visits."""

    url_id: int
    term: str
    normalized_term: str


@dataclass(slots=True)
class Session:
    """Grouped browsing activity based on deterministic rules."""

    id: str
    browser: Browser
    visits: List[VisitRecord]
    start_time: datetime
    end_time: datetime
    duration: timedelta
    seed_visit_id: int
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass(slots=True)
class Anomaly:
    """Represents an anomaly or noteworthy finding."""

    id: str
    visit_id: Optional[int]
    session_id: Optional[str]
    severity: str
    category: str
    description: str
    data: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadRecord:
    """Represents a download item captured from browser artifacts."""

    id: int
    url: Optional[str]
    tab_url: Optional[str]
    tab_referrer_url: Optional[str]
    target_path: Optional[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    danger_type: Optional[str]
    interrupt_reason: Optional[str]
    received_bytes: Optional[int]
    total_bytes: Optional[int]


@dataclass(slots=True)
class RuleMatch:
    """Represents a rule match against a URL or visit."""

    rule_name: str
    category: str
    severity: str
    description: str
    metadata: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    risk_score: Optional[int] = None
    false_positive_rate: Optional[float] = None
    ioc_types: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtensionInfo:
    """Metadata about a browser extension from preferences."""

    extension_id: str
    name: str
    webstore_url: Optional[str] = None
    enabled: bool = False
    version: Optional[str] = None
    install_time: Optional[datetime] = None
    from_webstore: Optional[bool] = None
    install_location: Optional[str] = None
    permissions: List[str] = field(default_factory=list)


@dataclass(slots=True)
class PreferencesData:
    """Parsed data from a browser preferences artifact."""

    source_path: Path
    full_name: Optional[str]
    email: Optional[str]
    language: Optional[str]
    download_directory: Optional[str]
    last_selected_directory: Optional[str]
    account_passwords: Optional[int]
    profile_passwords: Optional[int]
    recent_session_times: List[datetime]
    allowed_notification_hosts: List[str]
    extensions: List[ExtensionInfo]
    proxy_server: Optional[str]
    credential_logins_enabled: Optional[bool]
    last_session_exit_type: Optional[str]


@dataclass(slots=True)
class RuleCondition:
    """Conditions that determine if a rule matches."""

    tlds: Set[str] = field(default_factory=set)
    hostname_suffixes: Set[str] = field(default_factory=set)
    hostname_exact: Set[str] = field(default_factory=set)
    hostname_contains: Set[str] = field(default_factory=set)
    path_prefixes: Set[str] = field(default_factory=set)
    path_extensions: Set[str] = field(default_factory=set)
    path_contains: Set[str] = field(default_factory=set)
    url_contains: Set[str] = field(default_factory=set)
    query_contains: Set[str] = field(default_factory=set)
    search_terms: Set[str] = field(default_factory=set)
    require_ip: bool = False
    exclude_local: bool = False
    schemes: Set[str] = field(default_factory=set)
    contains_unicode: bool = False
    mixed_scripts: bool = False
    ip_ranges: Tuple[str, ...] = field(default_factory=tuple)

    def matches(self, url: UrlRecord, visit: VisitRecord, search_terms: Sequence[SearchTerm]) -> Optional[Dict[str, str]]:
        metadata: Dict[str, str] = {}

        hostname_lc = (url.hostname or "").lower()
        path_value = url.path or ""
        query_value = url.query or ""
        url_value = url.url or ""

        if self.tlds:
            tld = (url.tld or "").lower()
            if tld not in self.tlds:
                return None
            metadata["tld"] = tld

        if self.hostname_exact:
            if hostname_lc not in self.hostname_exact:
                return None
            metadata["hostname"] = hostname_lc

        if self.hostname_suffixes:
            if not any(hostname_lc.endswith(suffix) for suffix in self.hostname_suffixes if suffix):
                return None
            metadata["hostname_suffix"] = next(
                suffix for suffix in self.hostname_suffixes if suffix and hostname_lc.endswith(suffix)
            )

        if self.hostname_contains:
            if not hostname_lc:
                return None
            if not any(token in hostname_lc for token in self.hostname_contains if token):
                return None
            metadata["hostname_contains"] = next(
                token for token in self.hostname_contains if token and token in hostname_lc
            )

        if self.require_ip and not url.is_ip_address:
            return None
        ip_obj: Optional[ipaddress._BaseAddress] = None
        if url.is_ip_address and url.hostname:
            try:
                ip_obj = ipaddress.ip_address(url.hostname)
            except ValueError:
                ip_obj = None

        if self.exclude_local and ip_obj is not None:
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
                return None

        if self.ip_ranges:
            if ip_obj is None and hostname_lc != "localhost":
                return None
            matched_range: Optional[str] = None
            for range_spec in self.ip_ranges:
                if range_spec == "localhost" and hostname_lc == "localhost":
                    matched_range = range_spec
                    break
                if ip_obj is None:
                    continue
                try:
                    network = ipaddress.ip_network(range_spec, strict=False)
                except ValueError:
                    continue
                if ip_obj in network:
                    matched_range = range_spec
                    break
            if matched_range is None:
                return None
            metadata["ip_range"] = matched_range

        if self.schemes:
            scheme_value = (url.scheme or "").lower()
            if scheme_value not in self.schemes:
                return None
            metadata["scheme"] = scheme_value

        if self.path_prefixes:
            if not any(path_value.startswith(prefix) for prefix in self.path_prefixes if prefix):
                return None
            metadata["path_prefix"] = next(
                prefix for prefix in self.path_prefixes if prefix and path_value.startswith(prefix)
            )

        if self.path_extensions:
            ext = (url.file_extension or "").lower()
            if ext not in self.path_extensions:
                return None
            metadata["file_extension"] = ext

        if self.path_contains:
            path_lower = path_value.lower()
            if not any(token in path_lower for token in self.path_contains if token):
                return None
            metadata["path_contains"] = next(
                token for token in self.path_contains if token and token in path_lower
            )

        if self.url_contains:
            url_lc = (url.url or "").lower()
            if not any(token in url_lc for token in self.url_contains if token):
                return None
            metadata["url_contains"] = next(token for token in self.url_contains if token and token in url_lc)

        if self.query_contains:
            query_lc = query_value.lower()
            if not any(token in query_lc for token in self.query_contains if token):
                return None
            metadata["query_contains"] = next(
                token for token in self.query_contains if token and token in query_lc
            )

        if self.contains_unicode:
            if not _contains_unicode(url_value, hostname_lc):
                return None
            metadata["contains_unicode"] = "true"

        if self.mixed_scripts:
            if not _has_mixed_scripts(url.hostname or ""):
                return None
            metadata["mixed_scripts"] = "true"

        if self.search_terms:
            terms_lc = {term.term.lower() for term in search_terms}
            if not self.search_terms.intersection(terms_lc):
                return None
            metadata["search_term"] = next(iter(self.search_terms.intersection(terms_lc)))

        return metadata


def _contains_unicode(url_value: str, hostname_lc: str) -> bool:
    if not url_value:
        return False
    if any(ord(ch) > 127 for ch in url_value):
        return True
    return "xn--" in hostname_lc


def _has_mixed_scripts(value: str) -> bool:
    if not value:
        return False
    scripts: Set[str] = set()
    for ch in value:
        if ch == "-" or ch == ".":
            continue
        if unicodedata.category(ch).startswith("L"):
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            script = name.split()[0]
            scripts.add(script)
            if len(scripts) > 1:
                return True
    return False


@dataclass(slots=True)
class RuleDefinition:
    """Rule that can match against history entries."""

    name: str
    category: str
    severity: str
    description: str
    conditions: RuleCondition
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    risk_score: Optional[int] = None
    false_positive_rate: Optional[float] = None
    ioc_types: List[str] = field(default_factory=list)

    def matches(self, url: UrlRecord, visit: VisitRecord, search_terms: Sequence[SearchTerm]) -> Optional[RuleMatch]:
        if not self.enabled:
            return None
        metadata = self.conditions.matches(url, visit, search_terms)
        if metadata is None:
            return None
        return RuleMatch(
            rule_name=self.name,
            category=self.category,
            severity=self.severity,
            description=self.description,
            metadata={key: str(value) for key, value in metadata.items()},
            tags=list(self.tags),
            risk_score=self.risk_score,
            false_positive_rate=self.false_positive_rate,
            ioc_types=list(self.ioc_types),
        )


@dataclass(slots=True)
class AnalysisResult:
    """Aggregated analysis output."""

    history: Optional[HistoryData]
    sessions: List[Session]
    anomalies: List[Anomaly]
    visit_to_session: Dict[int, str]
    rule_matches: Dict[int, List[RuleMatch]]
    rules: Sequence[RuleDefinition]
    preferences: Optional[PreferencesData]


@dataclass(slots=True)
class HistoryData:
    """Normalized history payload from a browser database."""

    browser: Browser
    source_path: Path
    urls: Dict[int, UrlRecord]
    visits: List[VisitRecord]
    search_terms: Dict[int, List[SearchTerm]] = field(default_factory=dict)
    downloads: List[DownloadRecord] = field(default_factory=list)

    def search_terms_for_url(self, url_id: int) -> Sequence[SearchTerm]:
        return self.search_terms.get(url_id, [])
