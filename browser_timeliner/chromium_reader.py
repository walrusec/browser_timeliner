"""Chromium history database reader for Browser Timeliner."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional

from .domain_utils import parse_url_components
from .logging_config import get_logger
from .models import Browser, DownloadRecord, HistoryData, SearchTerm, UrlRecord, VisitRecord
from .utils import chromium_timestamp_to_datetime, ensure_copy


def _normalize_download_field(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            value = repr(value)
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


@dataclass(slots=True, frozen=True)
class ChromiumHistoryOptions:
    copy_before_read: bool = True


TRANSITION_CORE_TYPES = {
    0: "LINK",
    1: "TYPED",
    2: "AUTO_BOOKMARK",
    3: "AUTO_SUBFRAME",
    4: "MANUAL_SUBFRAME",
    5: "GENERATED",
    6: "START_PAGE",
    7: "FORM_SUBMIT",
    8: "RELOAD",
    9: "KEYWORD",
    10: "KEYWORD_GENERATED",
}


logger = get_logger(__name__)

TRANSITION_QUALIFIERS = {
    0x01000000: "FORWARD_BACK",
    0x02000000: "FROM_ADDRESS_BAR",
    0x04000000: "HOME_PAGE",
    0x08000000: "FROM_API",
    0x10000000: "CHAIN_START",
    0x20000000: "CHAIN_END",
    0x40000000: "CLIENT_REDIRECT",
    0x80000000: "SERVER_REDIRECT",
}

VISIT_SOURCE_TYPES = {
    0: "BROWSED",
    1: "SYNCED",
    2: "EXTENSION",
    3: "FIREFOX_IMPORTED",
    4: "IE_IMPORTED",
    5: "SAFARI_IMPORTED",
    6: "CHROME_IMPORTED",
}


def decode_transition(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    base = value & 0xFF
    core = TRANSITION_CORE_TYPES.get(base, f"UNKNOWN_{base}")
    flags = [name for mask, name in TRANSITION_QUALIFIERS.items() if value & mask]
    if flags:
        return core + "|" + "|".join(sorted(flags))
    return core


def _read_history(db_path: Path) -> HistoryData:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        urls = _fetch_urls(con)
        visit_sources = _fetch_visit_sources(con)
        visits = _fetch_visits(con, visit_sources)
        downloads = _fetch_downloads(con)
        search_terms = _fetch_search_terms(con)
    return HistoryData(
        browser=Browser.CHROMIUM,
        source_path=db_path,
        urls=urls,
        visits=visits,
        downloads=downloads,
        search_terms=search_terms,
    )


def load_history(source: Path, *, options: Optional[ChromiumHistoryOptions] = None) -> HistoryData:
    source = Path(source)
    opts = options or ChromiumHistoryOptions()

    if opts.copy_before_read:
        with TemporaryDirectory(prefix="browser_timeliner_chromium_") as tmp:
            working_path = ensure_copy(source, Path(tmp))
            history = _read_history(working_path)
            # Preserve the original path so downstream consumers know the source artifact
            history.source_path = source
            return history
    return _read_history(source)


def _fetch_urls(con: sqlite3.Connection) -> Dict[int, UrlRecord]:
    cursor = con.execute(
        """
        SELECT id, url, title, visit_count, typed_count, last_visit_time, hidden
        FROM urls
        """
    )
    results: Dict[int, UrlRecord] = {}
    for row in cursor:
        ts = row["last_visit_time"]
        last_visit = None
        if ts:
            last_visit = chromium_timestamp_to_datetime(ts)
        hostname, scheme, tld, is_ip, path, query, base_domain, file_ext = parse_url_components(row["url"])
        results[row["id"]] = UrlRecord(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            visit_count=row["visit_count"],
            typed_count=row["typed_count"],
            last_visit_time=last_visit,
            hidden=bool(row["hidden"]),
            url_base_domain=base_domain,
            url_registered_domain=base_domain,
            hostname=hostname,
            scheme=scheme,
            tld=tld,
            is_ip_address=is_ip,
            path=path,
            query=query,
            file_extension=file_ext,
        )
    return results


def _fetch_downloads(con: sqlite3.Connection) -> List[DownloadRecord]:
    try:
        cursor = con.execute(
            """
            SELECT id, tab_url, tab_referrer_url, target_path, start_time, end_time, danger_type,
                   interrupt_reason, received_bytes, total_bytes
            FROM downloads
            ORDER BY start_time ASC
            """
        )
    except sqlite3.OperationalError:
        logger.debug("Chromium history missing downloads table; skipping downloads")
        return []
    downloads: List[DownloadRecord] = []
    for row in cursor:
        start = chromium_timestamp_to_datetime(row["start_time"]) if row["start_time"] else None
        end = chromium_timestamp_to_datetime(row["end_time"]) if row["end_time"] else None
        danger_type = _normalize_download_field(row["danger_type"])
        interrupt_reason = _normalize_download_field(row["interrupt_reason"])
        downloads.append(
            DownloadRecord(
                id=row["id"],
                target_path=row["target_path"],
                url=row["tab_url"],
                tab_url=row["tab_url"],
                tab_referrer_url=row["tab_referrer_url"],
                start_time=start,
                end_time=end,
                danger_type=danger_type,
                interrupt_reason=interrupt_reason,
                received_bytes=row["received_bytes"],
                total_bytes=row["total_bytes"],
            )
        )
    return downloads


def _fetch_visit_sources(con: sqlite3.Connection) -> Dict[int, str]:
    try:
        cursor = con.execute("SELECT id, source FROM visit_source")
    except sqlite3.OperationalError:
        logger.debug("Chromium history missing visit_source table; defaulting to empty map")
        return {}
    mapping: Dict[int, str] = {}
    for row in cursor:
        source_value = row["source"]
        mapping[row["id"]] = VISIT_SOURCE_TYPES.get(source_value, f"UNKNOWN_{source_value}")
    return mapping


def _fetch_visits(con: sqlite3.Connection, visit_sources: Dict[int, str]) -> List[VisitRecord]:
    cursor = con.execute(
        """
        SELECT id, url, visit_time, from_visit, transition, visit_duration,
               external_referrer_url, opener_visit
        FROM visits
        ORDER BY visit_time ASC
        """
    )
    visits: List[VisitRecord] = []
    for row in cursor:
        visit_time = chromium_timestamp_to_datetime(row["visit_time"])
        duration_value = row["visit_duration"] or 0
        duration = None
        if duration_value:
            duration = timedelta(microseconds=duration_value)
        visits.append(
            VisitRecord(
                id=row["id"],
                url_id=row["url"],
                visit_time=visit_time,
                from_visit=row["from_visit"],
                transition=decode_transition(row["transition"]),
                visit_source=visit_sources.get(row["id"]),
                browser=Browser.CHROMIUM,
                visit_duration=duration,
                referring_visit_id=row["opener_visit"],
                external_referrer_url=row["external_referrer_url"],
            )
        )
    return visits


def _fetch_search_terms(con: sqlite3.Connection) -> Dict[int, List[SearchTerm]]:
    try:
        cursor = con.execute(
            """
            SELECT url_id, term, normalized_term
            FROM keyword_search_terms
            ORDER BY url_id
            """
        )
    except sqlite3.OperationalError:
        logger.debug("Chromium history missing keyword_search_terms table; skipping search terms")
        return {}
    results: Dict[int, List[SearchTerm]] = {}
    for row in cursor:
        terms = results.setdefault(row["url_id"], [])
        terms.append(
            SearchTerm(
                url_id=row["url_id"],
                term=row["term"],
                normalized_term=row["normalized_term"],
            )
        )
    return results
