import sqlite3
from datetime import datetime, timezone

from browser_timeliner.chromium_reader import ChromiumHistoryOptions, load_history


def _chromium_timestamp(dt: datetime) -> int:
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 1_000_000)


def test_load_history_reads_core_tables(tmp_path):
    db_path = tmp_path / "History"
    visit_time = datetime(2024, 5, 1, 15, 30, tzinfo=timezone.utc)
    download_time = datetime(2024, 5, 1, 15, 45, tzinfo=timezone.utc)

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER,
                typed_count INTEGER,
                last_visit_time INTEGER,
                hidden INTEGER
            );

            CREATE TABLE visits (
                id INTEGER PRIMARY KEY,
                url INTEGER,
                visit_time INTEGER,
                from_visit INTEGER,
                transition INTEGER,
                visit_duration INTEGER,
                external_referrer_url TEXT,
                opener_visit INTEGER
            );

            CREATE TABLE visit_source (
                id INTEGER PRIMARY KEY,
                source INTEGER
            );

            CREATE TABLE downloads (
                id INTEGER PRIMARY KEY,
                tab_url TEXT,
                tab_referrer_url TEXT,
                target_path TEXT,
                start_time INTEGER,
                end_time INTEGER,
                danger_type BLOB,
                interrupt_reason BLOB,
                received_bytes INTEGER,
                total_bytes INTEGER
            );

            CREATE TABLE keyword_search_terms (
                url_id INTEGER,
                term TEXT,
                normalized_term TEXT
            );
            """
        )
        cur.execute(
            "INSERT INTO urls VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "https://indicator.example.com/path",
                "Indicator",
                1,
                0,
                _chromium_timestamp(visit_time),
                0,
            ),
        )
        cur.execute(
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                10,
                1,
                _chromium_timestamp(visit_time),
                None,
                0x10000000 | 0,
                5_000_000,
                "https://referrer.example.com",
                None,
            ),
        )
        cur.execute("INSERT INTO visit_source VALUES (?, ?)", (10, 2))
        cur.execute(
            "INSERT INTO downloads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                50,
                "https://indicator.example.com/download.bin",
                None,
                "/tmp/download.bin",
                _chromium_timestamp(download_time),
                _chromium_timestamp(download_time),
                1,
                None,
                512,
                1024,
            ),
        )
        cur.execute(
            "INSERT INTO keyword_search_terms VALUES (?, ?, ?)",
            (1, "Indicator", "indicator"),
        )
        con.commit()

    history = load_history(db_path)

    assert history.browser.value == "chromium"
    assert history.source_path == db_path
    assert 1 in history.urls

    url = history.urls[1]
    assert url.hostname == "indicator.example.com"
    assert url.tld == "com"
    assert url.file_extension is None

    visit = next(iter(history.visits))
    assert visit.id == 10
    assert visit.transition == "LINK|CHAIN_START"
    assert visit.visit_source == "EXTENSION"
    assert visit.visit_duration.total_seconds() == 5

    assert history.search_terms_for_url(1)[0].term == "Indicator"
    assert len(history.downloads) == 1
    download = history.downloads[0]
    assert download.danger_type == "1"
    assert download.received_bytes == 512
    assert download.total_bytes == 1024


def test_load_history_handles_missing_optional_tables(tmp_path):
    db_path = tmp_path / "HistoryNoExtras"
    visit_time = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER,
                typed_count INTEGER,
                last_visit_time INTEGER,
                hidden INTEGER
            );

            CREATE TABLE visits (
                id INTEGER PRIMARY KEY,
                url INTEGER,
                visit_time INTEGER,
                from_visit INTEGER,
                transition INTEGER,
                visit_duration INTEGER,
                external_referrer_url TEXT,
                opener_visit INTEGER
            );
            """
        )
        cur.execute(
            "INSERT INTO urls VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "https://example.com",
                "Example",
                1,
                0,
                _chromium_timestamp(visit_time),
                0,
            ),
        )
        cur.execute(
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                5,
                1,
                _chromium_timestamp(visit_time),
                None,
                0,
                None,
                None,
                None,
            ),
        )
        con.commit()

    options = ChromiumHistoryOptions(copy_before_read=False)
    history = load_history(db_path, options=options)

    assert history.visits[0].visit_source is None
    assert history.downloads == []
    assert history.search_terms == {}
