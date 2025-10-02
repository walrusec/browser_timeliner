import json
from datetime import datetime
from pathlib import Path

from browser_timeliner.preferences_parser import load_preferences


def chromium_microseconds(dt: datetime) -> int:
    epoch = datetime(1601, 1, 1)
    delta = dt - epoch
    return int(delta.total_seconds() * 1_000_000)


def test_load_preferences_parses_expected_fields(tmp_path):
    preferences_path = tmp_path / "Preferences"
    recent_session_time = chromium_microseconds(datetime(2024, 1, 1, 12, 30))
    data = {
        "account_info": [{"full_name": "Analyst User", "email": "analyst@example.com"}],
        "spellcheck": {"dictionaries": ["en-US"]},
        "download": {"default_directory": "/tmp/downloads"},
        "selectfile": {"last_directory": "/tmp/last"},
        "total_passwords_available_for_account": 5,
        "total_passwords_available_for_profile": 2,
        "in_product_help": {"recent_session_start_times": [str(recent_session_time)]},
        "profile": {
            "content_settings": {
                "exceptions": {
                    "notifications": {
                        "https://alerts.example.com": {"setting": 1},
                        "https://deny.example.com": {"setting": 2},
                    }
                }
            },
            "credentials_enable_service": True,
            "last_session_exit_type": "Crashed",
        },
        "extensions": {
            "install_signature": {"ids": ["mhjfbmdgcfjbbpaeojofohoefgiehjai", "custom-ext"]},
            "settings": {
                "mhjfbmdgcfjbbpaeojofohoefgiehjai": {
                    "state": 1,
                    "from_webstore": True,
                    "location": 1,
                    "install_time": str(chromium_microseconds(datetime(2024, 1, 2, 8, 15))),
                    "update_url": "https://chrome.google.com/webstore/detail/mhjfbmdgcfjbbpaeojofohoefgiehjai",
                    "granted_permissions": {"api": ["tabs"], "explicit_hosts": ["https://example.com/*"]},
                    "manifest": {"name": "Chrome PDF Viewer", "version": "1.2.3"},
                },
                "custom-ext": {
                    "enabled": False,
                    "from_webstore": False,
                    "location": "UNPACKED",
                    "install_time": "0x1D4C0",  # hex string example
                    "granted_optional_permissions": {"api": ["bookmarks"]},
                    "manifest": {"name": "Custom Tool", "version": "0.9"},
                },
            },
        },
        "proxy": {"server": "proxy.example.com:8080"},
    }
    preferences_path.write_text(json.dumps(data), encoding="utf-8")

    preferences = load_preferences(preferences_path)

    assert preferences.full_name == "Analyst User"
    assert preferences.email == "analyst@example.com"
    assert preferences.language == "en-US"
    assert preferences.download_directory == "/tmp/downloads"
    assert preferences.last_selected_directory == "/tmp/last"
    assert preferences.account_passwords == 5
    assert preferences.profile_passwords == 2
    assert len(preferences.recent_session_times) == 1
    assert preferences.recent_session_times[0].year == 2024
    assert preferences.allowed_notification_hosts == ["https://alerts.example.com"]
    assert len(preferences.extensions) == 2
    pdf_ext = next(ext for ext in preferences.extensions if ext.extension_id == "mhjfbmdgcfjbbpaeojofohoefgiehjai")
    assert pdf_ext.name == "Chrome PDF Viewer"
    assert pdf_ext.enabled is True
    assert pdf_ext.version == "1.2.3"
    assert pdf_ext.install_location == "INTERNAL"
    assert pdf_ext.permissions == ["https://example.com/*", "tabs"]
    assert pdf_ext.from_webstore is True
    assert pdf_ext.install_time is not None

    custom_ext = next(ext for ext in preferences.extensions if ext.extension_id == "custom-ext")
    assert custom_ext.name == "Custom Tool"
    assert custom_ext.enabled is False
    assert custom_ext.from_webstore is False
    assert "bookmarks" in custom_ext.permissions
    assert preferences.proxy_server == "proxy.example.com:8080"
    assert preferences.credential_logins_enabled is True
    assert preferences.last_session_exit_type == "Crashed"
