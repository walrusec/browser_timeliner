"""Parser for Chromium-based browser Preferences files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from .models import ExtensionInfo, PreferencesData
from .utils import chromium_timestamp_to_datetime


_DEFAULT_EXTENSION_MAP: Dict[str, str] = {
    "nmmhkkegccagdldgiimedpiccmgmieda": "Google Wallet",
    "mhjfbmdgcfjbbpaeojofohoefgiehjai": "Chrome PDF Viewer",
    "pkedcjkdefgpdelpbcmbmeomcjbeemfm": "Chrome Cast",
    "gmbmikajjgmnabiglmofgnnjllnmclfh": "Google Hangouts",
    "aapocclcgogkmnckokdflcdmpbhphlcb": "Google Slides",
    "aohghmighlieiainnegkcijnfilokake": "Google Docs",
    "felcaaldnbdncclmgdcncolpebgiejap": "Google Sheets",
    "ghbmnnjooekpmoecnnnilnnbdlolhkhi": "Google Docs Offline",
}


class PreferencesParseError(ValueError):
    """Raised when the preferences file cannot be parsed."""


def _safe_get(data: dict, path: Iterable) -> Optional[object]:
    current = data
    for key in path:
        try:
            current = current[key]
        except (KeyError, TypeError, IndexError):
            return None
    return current


def _parse_recent_sessions(raw_sessions: Optional[List[object]]) -> List[datetime]:
    results: List[datetime] = []
    if not raw_sessions:
        return results
    for value in raw_sessions:
        if value is None:
            continue
        try:
            microseconds = int(value)
        except (ValueError, TypeError):
            continue
        try:
            results.append(chromium_timestamp_to_datetime(microseconds))
        except (OverflowError, ValueError):
            continue
    return results


def _parse_notification_exceptions(raw: Optional[dict]) -> List[str]:
    if not isinstance(raw, dict):
        return []
    allowed = []
    for host, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("setting") == 1:
            allowed.append(host)
    return allowed


def _build_webstore_url(extension_id: str) -> str:
    return f"https://chrome.google.com/webstore/detail/{extension_id}"


def _parse_extension_permissions(entry: dict) -> List[str]:
    permissions: Set[str] = set()
    for key in ("granted_permissions", "granted_optional_permissions"):
        granted = entry.get(key)
        if not isinstance(granted, dict):
            continue
        for list_key in ("api", "manifest_permissions"):
            values = granted.get(list_key)
            if isinstance(values, list):
                permissions.update(str(value) for value in values if value)
        for list_key in ("explicit_hosts", "scriptable_host"):
            values = granted.get(list_key)
            if isinstance(values, list):
                permissions.update(str(value) for value in values if value)
    return sorted(permissions)


def _parse_install_time(raw_value: object) -> Optional[datetime]:
    if isinstance(raw_value, str):
        try:
            return chromium_timestamp_to_datetime(int(raw_value, 0))
        except (ValueError, OverflowError):
            return None
    if isinstance(raw_value, (int, float)):
        try:
            return chromium_timestamp_to_datetime(int(raw_value))
        except (ValueError, OverflowError):
            return None
    return None


LOCATION_LABELS = {
    0: "UNKNOWN",
    1: "INTERNAL",
    2: "EXTERNAL",
    3: "UNPACKED",
    4: "COMPONENT",
    5: "POLICY",
}


def _parse_extensions(settings: Optional[dict], fallback_ids: Optional[List[str]]) -> List[ExtensionInfo]:
    extensions: List[ExtensionInfo] = []
    seen_ids: Set[str] = set()

    if isinstance(settings, dict):
        for ext_id, entry in settings.items():
            if not isinstance(ext_id, str) or not isinstance(entry, dict):
                continue

            manifest = entry.get("manifest") if isinstance(entry.get("manifest"), dict) else {}
            name = manifest.get("name")
            if not name:
                name = entry.get("name")
            if not isinstance(name, str) or not name:
                name = _DEFAULT_EXTENSION_MAP.get(ext_id, "Unknown Extension")

            version = manifest.get("version") if isinstance(manifest, dict) else None
            if not isinstance(version, str):
                version = entry.get("version") if isinstance(entry.get("version"), str) else None

            enabled = False
            state = entry.get("state")
            if isinstance(state, int):
                enabled = state == 1
            else:
                enabled = bool(entry.get("enabled", False))

            from_webstore = entry.get("from_webstore")
            if not isinstance(from_webstore, bool):
                from_webstore = None

            install_location = entry.get("location")
            if isinstance(install_location, int):
                install_location_label = LOCATION_LABELS.get(install_location, str(install_location))
            elif isinstance(install_location, str):
                install_location_label = install_location
            else:
                install_location_label = None

            install_time = _parse_install_time(entry.get("install_time"))

            permissions = _parse_extension_permissions(entry)

            webstore_url: Optional[str] = None
            update_url = entry.get("update_url")
            if isinstance(update_url, str) and update_url:
                webstore_url = update_url
            if from_webstore or not webstore_url:
                webstore_url = _build_webstore_url(ext_id)

            extensions.append(
                ExtensionInfo(
                    extension_id=ext_id,
                    name=name,
                    webstore_url=webstore_url,
                    enabled=enabled,
                    version=version,
                    install_time=install_time,
                    from_webstore=from_webstore,
                    install_location=install_location_label,
                    permissions=permissions,
                )
            )
            seen_ids.add(ext_id)

    if isinstance(fallback_ids, list):
        for ext_id in fallback_ids:
            if not isinstance(ext_id, str) or ext_id in seen_ids:
                continue
            name = _DEFAULT_EXTENSION_MAP.get(ext_id, "Unknown Extension")
            extensions.append(
                ExtensionInfo(
                    extension_id=ext_id,
                    name=name,
                    webstore_url=_build_webstore_url(ext_id),
                )
            )
            seen_ids.add(ext_id)

    extensions.sort(key=lambda ext: (ext.name.lower(), ext.extension_id))
    return extensions


def load_preferences(path: Path) -> PreferencesData:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Preferences file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PreferencesParseError(f"Invalid JSON preferences file: {path}") from exc

    if not isinstance(data, dict) or "profile" not in data:
        raise PreferencesParseError("File does not appear to be a Chromium Preferences file")

    recent_sessions = _parse_recent_sessions(
        _safe_get(data, ["in_product_help", "recent_session_start_times"])
    )

    extensions = _parse_extensions(
        _safe_get(data, ["extensions", "settings"]),
        _safe_get(data, ["extensions", "install_signature", "ids"]),
    )

    preferences = PreferencesData(
        source_path=path,
        full_name=_safe_get(data, ["account_info", 0, "full_name"]),
        email=_safe_get(data, ["account_info", 0, "email"]),
        language=_safe_get(data, ["spellcheck", "dictionaries", 0]),
        download_directory=_safe_get(data, ["download", "default_directory"]),
        last_selected_directory=_safe_get(data, ["selectfile", "last_directory"]),
        account_passwords=_safe_get(data, ["total_passwords_available_for_account"]),
        profile_passwords=_safe_get(data, ["total_passwords_available_for_profile"]),
        recent_session_times=recent_sessions,
        allowed_notification_hosts=_parse_notification_exceptions(
            _safe_get(data, ["profile", "content_settings", "exceptions", "notifications"])
        ),
        extensions=extensions,
        proxy_server=_safe_get(data, ["proxy", "server"]),
        credential_logins_enabled=_safe_get(data, ["profile", "credentials_enable_service"]),
        last_session_exit_type=_safe_get(data, ["profile", "last_session_exit_type"]),
    )

    return preferences
