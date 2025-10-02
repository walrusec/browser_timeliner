"""Firefox history database reader for Browser Timeliner."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional

from .models import Browser, HistoryData, SearchTerm, UrlRecord, VisitRecord
from .domain_utils import parse_url_components
from .utils import ensure_copy, firefox_timestamp_to_datetime


@dataclass(slots=True, frozen=True)
class FirefoxHistoryOptions:
    copy_before_read: bool = True


VISIT_TYPE_MAP = {
    1: "LINK",
    2: "TYPED",
    3: "BOOKMARK",
    4: "EMBED",
    5: "REDIRECT_PERM",
    6: "REDIRECT_TEMP",
    7: "DOWNLOAD",
    8: "FRAMED_LINK",
    9: "RELOAD",
}


def decode_visit_type(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return VISIT_TYPE_MAP.get(value, f"UNKNOWN_{value}")


def load_history(source: Path, *, options: Optional[FirefoxHistoryOptions] = None) -> HistoryData:
    source = Path(source)
    opts = options or FirefoxHistoryOptions()

    if opts.copy_before_read:
        with TemporaryDirectory(prefix="browser_timeliner_firefox_") as tmp:
            working_path = ensure_copy(source, Path(tmp))
            return _read_history(working_path)
    return _read_history(source)


def _read_history(db_path: Path) -> HistoryData:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        urls = _fetch_places(con)
        visits = _fetch_visits(con)
        search_terms = _fetch_search_terms(con)
    return HistoryData(
        browser=Browser.FIREFOX,
        source_path=db_path,
        urls=urls,
        visits=visits,
        search_terms=search_terms,
    )


def _fetch_places(con: sqlite3.Connection) -> Dict[int, UrlRecord]:
    cursor = con.execute(
        """
        SELECT id, url, title, visit_count, typed, last_visit_date, hidden
        FROM moz_places
        """
    )
    results: Dict[int, UrlRecord] = {}
    for row in cursor:
        ts = row["last_visit_date"]
        last_visit = None
        if ts:
            last_visit = firefox_timestamp_to_datetime(ts)
        hostname, scheme, tld, is_ip, path, query, base_domain, file_ext = parse_url_components(row["url"])
        results[row["id"]] = UrlRecord(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            visit_count=row["visit_count"],
            typed_count=row["typed"],
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


def _fetch_visits(con: sqlite3.Connection) -> List[VisitRecord]:
    cursor = con.execute(
        """
        SELECT id, from_visit, place_id, visit_date, visit_type, session, source
        FROM moz_historyvisits
        ORDER BY visit_date ASC
        """
    )
    visits: List[VisitRecord] = []
    for row in cursor:
        visit_time = firefox_timestamp_to_datetime(row["visit_date"])
        visits.append(
            VisitRecord(
                id=row["id"],
                url_id=row["place_id"],
                visit_time=visit_time,
                from_visit=row["from_visit"],
                transition=decode_visit_type(row["visit_type"]),
                visit_source=None,
                browser=Browser.FIREFOX,
                visit_duration=None,
                referring_visit_id=row["session"],
                external_referrer_url=None,
            )
        )
    return visits


def _fetch_search_terms(con: sqlite3.Connection) -> Dict[int, List[SearchTerm]]:
    # Firefox stores search terms differently per search engine integration.
    try:
        cursor = con.execute(
            """
            SELECT place_id, input
            FROM moz_inputhistory
            ORDER BY place_id
            """
        )
    except sqlite3.OperationalError:
        return {}
    results: Dict[int, List[SearchTerm]] = {}
    for row in cursor:
        terms = results.setdefault(row["place_id"], [])
        term_value = row["input"]
        terms.append(
            SearchTerm(
                url_id=row["place_id"],
                term=term_value,
                normalized_term=term_value.lower(),
            )
        )
    return results
