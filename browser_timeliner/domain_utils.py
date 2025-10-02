"""Domain and URL parsing utilities for Browser Timeliner."""

from __future__ import annotations

import ipaddress
from typing import Optional, Tuple
from urllib.parse import urlparse


def parse_url_components(url: str) -> Tuple[Optional[str], Optional[str], Optional[str], bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Parse a URL into structured components.

    Returns (hostname, scheme, tld, is_ip, path, query, base_domain, file_extension).
    """

    try:
        parsed = urlparse(url)
    except ValueError:
        return (None, None, None, False, None, None, None, None)

    hostname = parsed.hostname
    scheme = parsed.scheme or None
    path = parsed.path or None
    query = parsed.query or None
    file_extension = None
    if path and "." in path.rsplit("/", 1)[-1]:
        segment = path.rsplit("/", 1)[-1]
        if "." in segment:
            file_extension = segment.rsplit(".", 1)[-1].lower()

    is_ip = False
    tld = None
    base_domain = None
    if hostname:
        try:
            ipaddress.ip_address(hostname)
            is_ip = True
        except ValueError:
            labels = hostname.split(".")
            if labels:
                tld = labels[-1].lower()
            if len(labels) >= 2:
                base_domain = ".".join(labels[-2:])
            else:
                base_domain = hostname
    return (hostname, scheme, tld, is_ip, path, query, base_domain, file_extension)
