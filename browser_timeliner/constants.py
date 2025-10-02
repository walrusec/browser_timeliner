"""Shared constants for Browser Timeliner."""

CHROMIUM_EPOCH_OFFSET_MICROSECONDS = 11644473600000000
"""Difference between Windows FILETIME epoch (1601-01-01 UTC) and UNIX epoch in microseconds."""

FIREFOX_EPOCH_OFFSET_MICROSECONDS = 0
"""Firefox stores microseconds since UNIX epoch."""

DEFAULT_SESSION_IDLE_GAP = 30 * 60
"""Seconds of inactivity before starting a new session when referrer chain breaks."""
