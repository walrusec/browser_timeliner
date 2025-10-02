"""Utilities for exporting analysis results."""

from __future__ import annotations

import csv
import json
from html import escape as html_escape
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZipFile, ZIP_DEFLATED

from .logging_config import get_logger
from .models import AnalysisResult, PreferencesData, Session
from .domain_utils import parse_url_components


logger = get_logger(__name__)


def result_to_dict(result: AnalysisResult, *, sessions: Optional[Sequence[Session]] = None) -> Dict[str, Any]:
    sessions = list(sessions) if sessions is not None else list(result.sessions)
    history = result.history

    logger.debug(
        "Serializing analysis result",
        extra={
            "session_count": len(sessions),
            "anomaly_count": len(result.anomalies),
            "rule_count": len(result.rules),
        },
    )

    history_payload = None
    if history:
        history_payload = {
            "sessions": [
                {
                    "id": session.id,
                    "browser": session.browser.value,
                    "start": session.start_time.isoformat(),
                    "end": session.end_time.isoformat(),
                    "duration_seconds": session.duration.total_seconds(),
                    "visit_count": len(session.visits),
                    "visits": [
                        {
                            "visit_id": visit.id,
                            "url": (history.urls.get(visit.url_id).url if visit.url_id in history.urls else None),
                            "timestamp": visit.visit_time.isoformat(),
                            "transition": visit.transition,
                            "rule_matches": [match.rule_name for match in result.rule_matches.get(visit.id, [])],
                        }
                        for visit in session.visits
                    ],
                }
                for session in sessions
            ],
            "anomalies": [
                {
                    "id": anomaly.id,
                    "severity": anomaly.severity,
                    "category": anomaly.category,
                    "description": anomaly.description,
                    "visit_id": anomaly.visit_id,
                    "session_id": anomaly.session_id,
                    "data": anomaly.data,
                }
                for anomaly in result.anomalies
            ],
            "visit_to_session": dict(result.visit_to_session),
        }

    return {
        "history": history_payload,
        "preferences": _preferences_to_dict(result.preferences) if result.preferences else None,
        "rules": [rule.name for rule in result.rules],
    }


def _preferences_to_dict(preferences: PreferencesData) -> Dict[str, Any]:
    return {
        "source_path": str(preferences.source_path),
        "full_name": preferences.full_name,
        "email": preferences.email,
        "language": preferences.language,
        "download_directory": preferences.download_directory,
        "last_selected_directory": preferences.last_selected_directory,
        "account_passwords": preferences.account_passwords,
        "profile_passwords": preferences.profile_passwords,
        "recent_session_times": [dt.isoformat() for dt in preferences.recent_session_times],
        "allowed_notification_hosts": preferences.allowed_notification_hosts,
        "extensions": [
            {
                "extension_id": ext.extension_id,
                "name": ext.name,
                "webstore_url": ext.webstore_url,
            }
            for ext in preferences.extensions
        ],
        "proxy_server": preferences.proxy_server,
        "credential_logins_enabled": preferences.credential_logins_enabled,
        "last_session_exit_type": preferences.last_session_exit_type,
    }


RESULT_EXPORT_COLUMNS: Tuple[str, ...] = (
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


PREFERENCES_EXPORT_COLUMNS: Tuple[str, ...] = (
    "field",
    "value",
)


def build_result_rows(result: AnalysisResult, filters: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    history = result.history
    if not history:
        logger.info("No history available for export")
        return []

    include_visits = True
    include_downloads = True
    require_anomaly = False
    require_rules = False
    if filters:
        filter_set = set(filters)
        include_visits = bool(filter_set & {"visits", "anomalies", "rules"}) or (not filter_set)
        include_downloads = "downloads" in filter_set or (not filter_set)
        require_anomaly = "anomalies" in filter_set
        require_rules = "rules" in filter_set
        if filter_set == {"downloads"}:
            include_visits = False
        if filter_set == {"visits"}:
            include_downloads = False

    rows: List[Dict[str, Any]] = []
    session_lookup: Dict[str, Session] = {session.id: session for session in result.sessions}
    anomalies_by_visit: Dict[int, List[Any]] = {}
    for anomaly in result.anomalies:
        if anomaly.visit_id is None:
            continue
        anomalies_by_visit.setdefault(anomaly.visit_id, []).append(anomaly)

    for visit in history.visits:
        url_record = history.urls.get(visit.url_id)
        session_id = result.visit_to_session.get(visit.id)
        session = session_lookup.get(session_id) if session_id else None
        matches = result.rule_matches.get(visit.id, [])
        visit_anomalies = anomalies_by_visit.get(visit.id, [])

        if not include_visits:
            continue
        if require_rules and not matches:
            continue
        if require_anomaly and not visit_anomalies:
            continue

        rule_names = "; ".join(match.rule_name for match in matches)
        rule_severities = "; ".join(match.severity for match in matches)
        rule_categories = "; ".join(match.category for match in matches)
        rule_tags = "; ".join(sorted({tag for match in matches for tag in match.tags})) if matches else ""
        rule_descriptions = "; ".join(match.description for match in matches)

        anomaly_ids = "; ".join(anomaly.id for anomaly in visit_anomalies)
        anomaly_severities = "; ".join(anomaly.severity for anomaly in visit_anomalies)
        anomaly_categories = "; ".join(anomaly.category for anomaly in visit_anomalies)
        anomaly_descriptions = "; ".join(anomaly.description for anomaly in visit_anomalies)

        session_duration_minutes = ""
        if session and session.duration:
            session_duration_minutes = f"{session.duration.total_seconds() / 60:.2f}"

        rows.append({
            "visit_time": visit.visit_time.isoformat(),
            "visit_title": (url_record.title if url_record and url_record.title else ""),
            "visit_url": url_record.url if url_record else "",
            "record_type": "visit",
            "download_received_bytes": "",
            "download_total_bytes": "",
            "download_tab_url": "",
            "download_referrer_url": "",
            "session_id": session_id or "",
            "session_browser": session.browser.value if session else (visit.browser.value if hasattr(visit.browser, "value") else ""),
            "session_start": session.start_time.isoformat() if session else "",
            "session_end": session.end_time.isoformat() if session else "",
            "session_duration_minutes": session_duration_minutes,
            "session_tags": ", ".join(session.tags) if session and session.tags else "",
            "session_notes": session.notes or "" if session else "",
            "visit_id": str(visit.id),
            "host": url_record.hostname if url_record and url_record.hostname else "",
            "path": url_record.path if url_record and url_record.path else "",
            "query": url_record.query if url_record and url_record.query else "",
            "tld": url_record.tld if url_record and url_record.tld else "",
            "registered_domain": url_record.url_registered_domain if url_record and url_record.url_registered_domain else "",
            "was_ip": str(url_record.is_ip_address).lower() if url_record else "",
            "rule_names": rule_names,
            "rule_severities": rule_severities,
            "rule_categories": rule_categories,
            "rule_tags": rule_tags,
            "rule_descriptions": rule_descriptions,
            "anomaly_ids": anomaly_ids,
            "anomaly_severities": anomaly_severities,
            "anomaly_categories": anomaly_categories,
            "anomaly_descriptions": anomaly_descriptions,
        })

    if include_downloads:
        for download in history.downloads:
            download_time = ""
            if download.start_time:
                download_time = download.start_time.isoformat()
            elif download.end_time:
                download_time = download.end_time.isoformat()

            host = path = query = tld = registered_domain = ""
            was_ip = ""
            if download.url:
                hostname, _, parsed_tld, is_ip, parsed_path, parsed_query, base_domain, _ = parse_url_components(download.url)
                host = hostname or ""
                path = parsed_path or ""
                query = parsed_query or ""
                tld = parsed_tld or ""
                registered_domain = base_domain or ""
                was_ip = str(is_ip).lower()

            rows.append({
                "visit_time": download_time,
                "visit_title": Path(download.target_path).name if download.target_path else "",
                "visit_url": download.url or "",
                "record_type": "download",
                "download_received_bytes": str(download.received_bytes) if download.received_bytes is not None else "",
                "download_total_bytes": str(download.total_bytes) if download.total_bytes is not None else "",
                "download_tab_url": download.tab_url or "",
                "download_referrer_url": download.tab_referrer_url or "",
                "session_id": "",
                "session_browser": "",
                "session_start": "",
                "session_end": "",
                "session_duration_minutes": "",
                "session_tags": "",
                "session_notes": "",
                "visit_id": str(download.id),
                "host": host,
                "path": path,
                "query": query,
                "tld": tld,
                "registered_domain": registered_domain,
                "was_ip": was_ip,
                "rule_names": "",
                "rule_severities": "",
                "rule_categories": "",
                "rule_tags": "",
                "rule_descriptions": "",
                "anomaly_ids": "",
                "anomaly_severities": "",
                "anomaly_categories": "",
                "anomaly_descriptions": "",
            })

    rows.sort(key=lambda r: r.get("visit_time", ""), reverse=True)
    logger.debug("Built result rows", extra={"row_count": len(rows)})
    return rows


def build_preferences_rows(preferences: PreferencesData) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    def add_row(label: str, value: Optional[Any]) -> None:
        rows.append({"field": label, "value": "" if value is None else str(value)})

    add_row("Source", preferences.source_path)
    add_row("Full name", preferences.full_name)
    add_row("Email", preferences.email)
    add_row("Language", preferences.language)
    add_row("Download directory", preferences.download_directory)
    add_row("Last selected directory", preferences.last_selected_directory)
    add_row("Proxy server", preferences.proxy_server)
    add_row("Credential logins enabled", preferences.credential_logins_enabled)
    add_row("Last session exit type", preferences.last_session_exit_type)
    add_row(
        "Recent session times",
        ", ".join(dt.isoformat() for dt in preferences.recent_session_times),
    )

    if preferences.extensions:
        for extension in preferences.extensions:
            ext_value = f"{extension.name} ({extension.extension_id})"
            if extension.webstore_url:
                ext_value += f" — {extension.webstore_url}"
            rows.append({"field": "Extension", "value": ext_value})

    if preferences.allowed_notification_hosts:
        rows.append({
            "field": "Allowed notification hosts",
            "value": ", ".join(preferences.allowed_notification_hosts),
        })

    logger.debug("Built preferences rows", extra={"row_count": len(rows)})
    return rows


def write_result_export(result: AnalysisResult, path: Path, format_key: str, *, filters: Optional[Sequence[str]] = None) -> None:
    format_key = format_key.lower()
    rows = build_result_rows(result, filters=filters)
    headers = list(RESULT_EXPORT_COLUMNS)

    if format_key == "csv":
        _write_csv(path, headers, rows)
    elif format_key == "json":
        payload = result_to_dict(result)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif format_key == "json-min":
        payload = result_to_dict(result)
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    elif format_key == "html":
        _write_html_table(path, "Timeline export", headers, rows)
    elif format_key == "xlsx":
        _write_xlsx(path, headers, rows)
    else:
        raise ValueError(f"Unsupported export format: {format_key}")
    logger.info(
        "Result export written",
        extra={"path": str(path), "format": format_key, "row_count": len(rows)},
    )


def write_preferences_export(preferences: PreferencesData, path: Path, format_key: str) -> None:
    rows = build_preferences_rows(preferences)
    headers = list(PREFERENCES_EXPORT_COLUMNS)

    if format_key == "csv":
        _write_csv(path, headers, rows)
    elif format_key == "json":
        payload = _preferences_to_dict(preferences)
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    elif format_key == "html":
        _write_html_table(path, "Preferences export", headers, rows)
    else:
        raise ValueError(f"Unsupported preferences export format: {format_key}")
    logger.info(
        "Preferences export written",
        extra={"path": str(path), "format": format_key, "row_count": len(rows)},
    )


def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def _write_html_table(path: Path, title: str, headers: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    buffer = StringIO()
    buffer.write("<html><head><meta charset='utf-8'>")
    buffer.write(
        "<style>body{font-family:Inter,Arial,sans-serif;background:#0b112d;color:#e2e8f0;padding:24px;}"
        "table{border-collapse:collapse;width:100%;margin-top:16px;}"
        "th,td{border:1px solid #334155;padding:8px;vertical-align:top;}"
        "th{background:#1e293b;text-transform:uppercase;font-size:12px;letter-spacing:0.05em;}"
        "tr:nth-child(even){background:#101a33;}"
        "caption{font-size:20px;font-weight:600;margin-bottom:12px;}"
        "</style></head><body>"
    )
    buffer.write(f"<caption>{html_escape(title)}</caption>")
    buffer.write("<table><thead><tr>")
    for header in headers:
        buffer.write(f"<th>{html_escape(str(header))}</th>")
    buffer.write("</tr></thead><tbody>")
    for row in rows:
        buffer.write("<tr>")
        for header in headers:
            value = row.get(header, "")
            buffer.write(f"<td>{html_escape(str(value))}</td>")
        buffer.write("</tr>")
    buffer.write("</tbody></table></body></html>")
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _write_xlsx(path: Path, headers: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types())
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("xl/workbook.xml", _xlsx_workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels())
        archive.writestr("xl/styles.xml", _xlsx_styles())
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(headers, rows))


def _xlsx_content_types() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
        "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
        "<Default Extension='xml' ContentType='application/xml'/>"
        "<Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>"
        "<Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/>"
        "<Override PartName='/xl/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'/>"
        "</Types>"
    )


def _xlsx_root_rels() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/>"
        "</Relationships>"
    )


def _xlsx_workbook() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'"
        " xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
        "<sheets><sheet name='Export' sheetId='1' r:id='rId1'/></sheets></workbook>"
    )


def _xlsx_workbook_rels() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/>"
        "</Relationships>"
    )


def _xlsx_styles() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<styleSheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
        "<fonts count='1'><font><sz val='11'/><name val='Calibri'/></font></fonts>"
        "<fills count='1'><fill><patternFill patternType='none'/></fill></fills>"
        "<borders count='1'><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
        "<cellStyleXfs count='1'><xf numFmtId='0' fontId='0' fillId='0' borderId='0'/></cellStyleXfs>"
        "<cellXfs count='1'><xf numFmtId='0' fontId='0' fillId='0' borderId='0' xfId='0'/></cellXfs>"
        "</styleSheet>"
    )


def _xlsx_sheet(headers: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    def cell_ref(col_index: int, row_index: int) -> str:
        letters = ""
        col = col_index
        while col >= 0:
            letters = chr(ord('A') + (col % 26)) + letters
            col = col // 26 - 1
        return f"{letters}{row_index}"

    def inline_cell(col_index: int, row_index: int, value: Any) -> str:
        if value is None:
            value = ""
        return (
            f"<c r='{cell_ref(col_index, row_index)}' t='inlineStr'>"
            f"<is><t>{xml_escape(str(value))}</t></is></c>"
        )

    xml_rows = ["<?xml version='1.0' encoding='UTF-8'?>"
                "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                "<sheetData>"]
    header_cells = ''.join(inline_cell(idx, 1, header) for idx, header in enumerate(headers))
    xml_rows.append(f"<row r='1'>{header_cells}</row>")

    for ridx, row in enumerate(rows, start=2):
        cell_xml = ''.join(inline_cell(cidx, ridx, row.get(header, ""))
                           for cidx, header in enumerate(headers))
        xml_rows.append(f"<row r='{ridx}'>{cell_xml}</row>")

    xml_rows.append("</sheetData></worksheet>")
    return ''.join(xml_rows)
