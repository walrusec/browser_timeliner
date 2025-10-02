"""Category definitions for Browser Timeliner rules and annotations."""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """Analytic categories for tagging visits and sessions."""

    SUSPICIOUS_TLD = "suspicious_tld"
    THREAT_INDICATOR = "threat_indicator"
    GEOPOLITICAL_RISK_TLD = "geopolitical_risk_tld"
    UNICODE_DOMAIN = "unicode_domain"
    LOCAL_NETWORK_ACTIVITY = "local_network_activity"
    DIRECT_IP_ACCESS = "direct_ip_access"
    DYNAMIC_DNS_FAST_FLUX = "dynamic_dns_fast_flux"
    URL_SHORTENER = "url_shortener"
    ANONYMIZATION_SERVICE = "anonymization_service"
    KNOWN_INDICATOR = "known_indicator"
    SEARCH_ENGINE = "search_engine"
    DOWNLOAD = "download"
    APPLICATION_DOWNLOAD = "application_download"
    ARCHIVE_DOWNLOAD = "archive_download"
    MEDIA_DOWNLOAD = "media_download"
    SYSTEMS_IT = "systems_it"
    PRODUCTIVITY = "productivity"
    EMAIL = "email"
    DISPOSABLE_EMAIL = "disposable_email"
    STAGING_PASTE_SERVICE = "staging_paste_service"
    SUSPICIOUS_URL = "suspicious_url"
    REMOTE_ACCESS = "remote_access"
    AD_TRACKING = "ad_tracking"
    IP_ADDRESS = "ip_address"
    MALWARE = "malware"
    CRYPTO = "crypto"
    GAMBLING = "gambling"
    SOCIAL_MEDIA = "social_media"
    ADULT_CONTENT = "adult_content"
    FINANCE = "finance"
    CLOUD_SERVICE = "cloud_service"
    DEV_TOOLS = "developer_tools"
    UNSAFE_EXTENSION = "unsafe_extension"
    UNKNOWN = "unknown"

    @classmethod
    def has_value(cls, value: str) -> bool:
        try:
            cls(value)
        except ValueError:
            return False
        return True
