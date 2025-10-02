"""Command-line interface for Browser Timeliner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from time import perf_counter
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from . import __version__
from .analysis import AnalysisOptions, analyze_artifacts
from .ingest import load_inputs
from .exporter import write_result_export, write_preferences_export
from .logging_config import (
    LogContext,
    configure_logging,
    generate_correlation_id,
    get_logger,
)
from .models import PreferencesData
from .rule_engine import load_rules_from_file, load_default_rules

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browser Timeliner CLI")
    parser.add_argument("input_path", type=Path, help="Path to history database, preferences file, or directory")
    parser.add_argument("--rules", type=Path, help="Optional custom rules YAML file")
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--anomaly-only",
        action="store_true",
        help="Show only anomaly entries",
    )
    parser.add_argument(
        "--session",
        type=str,
        help="Filter output to a specific session ID",
    )
    parser.add_argument(
        "--export",
        type=Path,
        help="Export timeline data to file (format inferred from extension unless --export-format is set)",
    )
    parser.add_argument(
        "--export-format",
        choices=("csv", "json", "json-min", "html", "xlsx"),
        help="Export file format (overrides inference from file extension)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Suppress detailed session output and show only a summary",
    )
    parser.add_argument(
        "--filter",
        action="append",
        choices=("anomalies", "downloads", "visits", "rules"),
        help="Limit exported rows (multiple allowed): anomalies, downloads, visits, rules",
    )
    parser.add_argument(
        "--export-preferences",
        type=Path,
        help="Optional path to export preferences data (CSV, JSON, or HTML)",
    )
    parser.add_argument(
        "--export-preferences-format",
        choices=("csv", "json", "html"),
        help="Format for preferences export (defaults to extension)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        help="Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument(
        "--log-format",
        choices=("json", "console"),
        help="Log output format",
    )
    parser.add_argument(
        "--correlation-id",
        type=str,
        help="Correlation identifier to include with log records",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(level=args.log_level, log_format=args.log_format)

    exit_code = 0
    resolved_input, temp_dir = _prepare_input_path(Path(args.input_path))

    with LogContext(args.correlation_id) as correlation_id:
        context_extra = {"correlation_id": correlation_id}
        _print_banner(
            input_path=args.input_path,
            correlation_id=correlation_id,
            log_level=args.log_level,
            log_format=args.log_format,
        )
        logger.info("Browser Timeliner CLI starting", extra={"input_path": str(args.input_path), **context_extra})

        if args.rules:
            logger.debug("Loading custom rules", extra={"rules_path": str(args.rules), **context_extra})
            rule_set = load_rules_from_file(args.rules)
        else:
            logger.debug("Loading default rule set", extra=context_extra)
            rule_set = load_default_rules()

        options = AnalysisOptions(rule_set=rule_set)

        history = None
        preferences = None
        result = None
        ingest_duration = None
        analysis_duration = None
        export_duration = None
        export_format = None
        export_status = "skipped"

        ingest_start = perf_counter()
        try:
            history, preferences = load_inputs(resolved_input)
            ingest_duration = perf_counter() - ingest_start
        except Exception as exc:
            logger.exception("Ingestion failure", extra={"input_path": str(args.input_path), **context_extra})
            print(f"ERROR: Browser Timeliner failed to ingest artifacts: {exc}", file=sys.stderr)
            exit_code = 1
        else:
            if history is None and preferences is None:
                logger.warning("No artifacts detected at path", extra={"input_path": str(args.input_path), **context_extra})
                print("No supported history or preferences artifacts found at provided path.")
                exit_code = 1
            else:
                analysis_start = perf_counter()
                try:
                    result = analyze_artifacts(history=history, preferences=preferences, options=options)
                    analysis_duration = perf_counter() - analysis_start
                except Exception as exc:
                    logger.exception("Analysis failure", extra={"input_path": str(args.input_path), **context_extra})
                    print(f"ERROR: Browser Timeliner failed to analyze artifacts: {exc}", file=sys.stderr)
                    exit_code = 1

        if result is not None:
            if args.export:
                export_format = args.export_format or _infer_export_format(args.export)
                filters = args.filter or []
                export_path = _build_timestamped_export_path(
                    base_path=args.export,
                    artifact_label=_artifact_label(result),
                    export_format=export_format,
                )
                export_start = perf_counter()
                try:
                    write_result_export(result, export_path, export_format, filters=filters)
                except ValueError as exc:
                    export_status = "failed"
                    logger.error(
                        "Unsupported export format",
                        extra={
                            "export_path": str(export_path),
                            "export_format": export_format,
                            "error": str(exc),
                            **context_extra,
                        },
                    )
                    print(f"ERROR: Unsupported export format: {exc}", file=sys.stderr)
                    exit_code = 1
                else:
                    export_duration = perf_counter() - export_start
                    export_status = export_format or "unknown"
                    logger.info(
                        "Export completed",
                        extra={
                            "export_path": str(export_path),
                            "export_format": export_format,
                            "export_duration": export_duration,
                            **context_extra,
                        },
                    )
                    print(f"Browser Timeliner exported analysis to {export_path}")

            _print_summary(
                input_path=args.input_path,
                result=result,
                ingest_duration=ingest_duration,
                analysis_duration=analysis_duration,
                export_duration=export_duration,
                export_target=export_path if args.export else None,
                export_status=export_status,
            )

            if result.preferences and args.export_preferences:
                pref_format = args.export_preferences_format or _infer_export_format(args.export_preferences)
                pref_path = _build_timestamped_export_path(
                    base_path=args.export_preferences,
                    artifact_label="preferences",
                    export_format=pref_format,
                )
                try:
                    write_preferences_export(result.preferences, pref_path, pref_format)
                except ValueError as exc:
                    logger.error(
                        "Unsupported preferences export format",
                        extra={
                            "export_path": str(pref_path),
                            "export_format": pref_format,
                            "error": str(exc),
                            **context_extra,
                        },
                    )
                    print(f"ERROR: Unsupported preferences export format: {exc}", file=sys.stderr)
                else:
                    print(f"Browser Timeliner exported preferences to {pref_path}")
                    logger.info(
                        "Preferences export completed",
                        extra={
                            "export_path": str(pref_path),
                            "export_format": pref_format,
                            **context_extra,
                        },
                    )

            rendered_sessions = 0
            if exit_code == 0 and not args.summary_only:
                output_sessions = result.sessions
                if args.session:
                    logger.debug(
                        "Session filter applied",
                        extra={"session": args.session, "matched": len(output_sessions), **context_extra},
                    )

                if args.format == "json":
                    payload = _build_json_payload(result, output_sessions)
                    print(json.dumps(payload, indent=2))
                    rendered_sessions = len(output_sessions)
                else:
                    rendered_sessions = _render_sessions(result, output_sessions, anomaly_only=args.anomaly_only)
            elif exit_code == 0 and args.summary_only and result.preferences:
                _render_preferences(result.preferences)

            logger.info(
                "Browser Timeliner CLI completed",
                extra={
                    "sessions_total": len(result.sessions),
                    "sessions_rendered": rendered_sessions,
                    "anomaly_count": len(result.anomalies),
                    "output_mode": "summary_only" if args.summary_only else args.format,
                    "ingest_seconds": ingest_duration,
                    "analysis_seconds": analysis_duration,
                    "export_seconds": export_duration,
                    "export_status": export_status,
                    **context_extra,
                },
            )

        logger.debug("Browser Timeliner CLI exiting", extra={"exit_code": exit_code, **context_extra})

    if temp_dir is not None:
        temp_dir.cleanup()

    return exit_code


def _build_json_payload(result, sessions):
    history_data = None
    history = result.history
    if history:
        history_data = {
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
        }

    data: Dict[str, Any] = {
        "history": history_data,
        "preferences": _preferences_to_dict(result.preferences) if result.preferences else None,
        "rules": [rule.name for rule in result.rules],
    }
    return data


def _render_sessions(result, sessions, *, anomaly_only: bool) -> int:
    if not result.history or not sessions:
        if not sessions:
            if result.history:
                print("No browsing history sessions were detected.")
        else:
            print("No browsing history sessions were detected.")
        if result.preferences:
            _render_preferences(result.preferences)
        elif not result.history:
            print("No supported artifacts were rendered.")
        return 0

    anomaly_lookup: Dict[str, int] = {}
    for anomaly in result.anomalies:
        if anomaly.session_id:
            anomaly_lookup[anomaly.session_id] = anomaly_lookup.get(anomaly.session_id, 0) + 1

    rendered = 0
    for session in sessions:
        if anomaly_only and anomaly_lookup.get(session.id, 0) == 0:
            continue

        rendered += 1
        print("-" * 80)
        print(f"Session {session.id}")
        print(f"Browser   : {session.browser.value}")
        print(f"Start     : {session.start_time.isoformat()}")
        print(f"End       : {session.end_time.isoformat()}")
        print(f"Visits    : {len(session.visits)}")
        print(f"Anomalies : {anomaly_lookup.get(session.id, 0)}")

        for visit in session.visits:
            url = result.history.urls.get(visit.url_id) if result.history else None
            rules = ", ".join(match.rule_name for match in result.rule_matches.get(visit.id, []))
            print(f"  Visit {visit.id} | {visit.visit_time.isoformat()} | {url.url if url else '[missing]'} | {visit.transition or ''} | {rules}")

        session_anomalies = [a for a in result.anomalies if a.session_id == session.id]
        if session_anomalies:
            print("  Anomalies:")
            for anomaly in session_anomalies:
                print(
                    f"    - {anomaly.severity.upper()} {anomaly.category}: {anomaly.description} (visit={anomaly.visit_id})"
                )
    if result.preferences:
        _render_preferences(result.preferences)
    elif not result.history:
        print("No supported artifacts were rendered.")

    return rendered


def _infer_export_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mapping = {
        "csv": "csv",
        "json": "json",
        "html": "html",
        "htm": "html",
        "xlsx": "xlsx",
    }
    if suffix in mapping:
        return mapping[suffix]
    return "json"


def _print_summary(
    *,
    input_path: Path,
    result,
    ingest_duration: Optional[float],
    analysis_duration: Optional[float],
    export_duration: Optional[float],
    export_target: Optional[Path],
    export_status: str,
) -> None:
    total_visits = len(result.history.visits) if result.history else 0
    total_sessions = len(result.sessions)
    total_anomalies = len(result.anomalies)
    total_downloads = len(result.history.downloads) if result.history else 0
    download_bytes_received = sum((d.received_bytes or 0) for d in result.history.downloads) if result.history else 0
    download_bytes_total = sum((d.total_bytes or 0) for d in result.history.downloads) if result.history else 0

    summary_items = [
        ("Input", str(input_path)),
        ("History present", "yes" if result.history else "no"),
        ("Preferences present", "yes" if result.preferences else "no"),
        ("Sessions", str(total_sessions)),
        ("Visits", str(total_visits)),
        ("Anomalies", str(total_anomalies)),
        ("Downloads", str(total_downloads)),
        ("Download bytes (received)", str(download_bytes_received)),
        ("Download bytes (total)", str(download_bytes_total)),
    ]
    if ingest_duration is not None:
        summary_items.append(("Ingest (s)", f"{ingest_duration:.2f}"))
    if analysis_duration is not None:
        summary_items.append(("Analysis (s)", f"{analysis_duration:.2f}"))
    if export_target:
        if export_duration is not None:
            summary_items.append(("Export (s)", f"{export_duration:.2f}"))
        summary_items.append(("Export path", str(export_target)))
        summary_items.append(("Export status", export_status))

    width = max(len(label) for label, _ in summary_items)
    print("\nBrowser Timeliner Summary")
    print("=" * (width + 25))
    for label, value in summary_items:
        print(f"{label:<{width}} : {value}")
    print()


def _print_summary_text(result) -> None:
    total_visits = len(result.history.visits) if result.history else 0
    total_sessions = len(result.sessions)
    total_anomalies = len(result.anomalies)
    print(
        f"Summary: sessions={total_sessions}, visits={total_visits}, anomalies={total_anomalies}"
    )


def _print_banner(
    *,
    input_path: Path,
    correlation_id: Optional[str],
    log_level: Optional[str],
    log_format: Optional[str],
) -> None:
    lines = [
        "=" * 80,
        f"Browser Timeliner v{__version__}",
        f"Input: {input_path}",
    ]
    if correlation_id:
        lines.append(f"Correlation: {correlation_id}")
    if log_level:
        lines.append(f"Log level: {log_level.upper()}")
    if log_format:
        lines.append(f"Log format: {log_format}")
    lines.append("=" * 80)
    print("\n".join(lines))


def _build_timestamped_export_path(*, base_path: Path, artifact_label: str, export_format: str) -> Path:
    """Return new export path with timestamp to avoid clobbering previous runs."""

    base_path = Path(base_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    artifact_slug = artifact_label.replace(" ", "_") if artifact_label else "analysis"
    extension = base_path.suffix
    if not extension:
        extension = f".{export_format}"
    new_name = f"browser_{artifact_slug}_result_{timestamp}{extension}"
    return base_path.with_name(new_name)


def _artifact_label(result) -> str:
    if result.history and result.history.browser:
        return result.history.browser.value
    if result.preferences:
        return "preferences"
    return "analysis"


def _prepare_input_path(path: Path) -> tuple[Path, Optional[TemporaryDirectory]]:
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        temp_dir = TemporaryDirectory(prefix="browser_timeliner_zip_")
        with ZipFile(path, "r") as archive:
            archive.extractall(temp_dir.name)
        extracted_root = Path(temp_dir.name)
        resolved = _locate_artifact_root(extracted_root)
        return resolved, temp_dir
    return path, None


def _locate_artifact_root(root: Path) -> Path:
    history_candidates = {child.name.lower() for child in root.iterdir() if child.is_file()}
    if "history" in history_candidates:
        return root
    if "preferences" in history_candidates:
        return root

    subdirs = [child for child in root.iterdir() if child.is_dir()]
    if len(subdirs) == 1:
        return _locate_artifact_root(subdirs[0])
    for subdir in subdirs:
        nested = list(subdir.iterdir())
        names = {child.name.lower() for child in nested if child.is_file()}
        if "history" in names or "preferences" in names:
            return subdir
    return root


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


def _render_preferences(preferences: PreferencesData) -> None:
    print("Preferences Summary")
    print("-" * 60)
    fields = [
        ("Source", preferences.source_path),
        ("Full name", preferences.full_name or "—"),
        ("Email", preferences.email or "—"),
        ("Language", preferences.language or "—"),
        ("Download directory", preferences.download_directory or "—"),
        ("Last directory", preferences.last_selected_directory or "—"),
        ("Account passwords", preferences.account_passwords if preferences.account_passwords is not None else "—"),
        ("Profile passwords", preferences.profile_passwords if preferences.profile_passwords is not None else "—"),
        ("Proxy server", preferences.proxy_server or "—"),
        (
            "Credentials enabled",
            preferences.credential_logins_enabled if preferences.credential_logins_enabled is not None else "—",
        ),
        ("Last exit type", preferences.last_session_exit_type or "—"),
        (
            "Recent sessions",
            ", ".join(dt.isoformat() for dt in preferences.recent_session_times) or "—",
        ),
        (
            "Allowed notifications",
            ", ".join(preferences.allowed_notification_hosts) or "—",
        ),
    ]
    width = max(len(label) for label, _ in fields)
    for label, value in fields:
        print(f"{label:<{width}} : {value}")

    if preferences.extensions:
        print("Extensions:")
        for ext in preferences.extensions:
            web_url = ext.webstore_url or "—"
            enabled_marker = "ENABLED" if ext.enabled else "DISABLED"
            version = ext.version or "unknown"
            install_time = ext.install_time.isoformat() if ext.install_time else "unknown"
            location = ext.install_location or "unknown"
            source = "webstore" if ext.from_webstore else "side-loaded"
            permissions = ", ".join(ext.permissions) if ext.permissions else "none"
            print(
                "  - "
                f"{ext.name} ({ext.extension_id})\n"
                f"      status: {enabled_marker}, version: {version}, installed: {install_time}, "
                f"location: {location}, source: {source}\n"
                f"      permissions: {permissions}\n"
                f"      webstore: {web_url}"
            )
    print()


if __name__ == "__main__":
    raise SystemExit(main())
