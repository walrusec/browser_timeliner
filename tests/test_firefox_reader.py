import sqlite3
from datetime import datetime, timezone

from browser_timeliner.firefox_reader import FirefoxHistoryOptions, load_history


def _firefox_timestamp(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


def test_load_history_reads_places_visits_and_search_terms(tmp_path):
    db_path = tmp_path / "places.sqlite"
    visit_time = datetime(2024, 5, 1, 15, 30, tzinfo=timezone.utc)

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER,
                typed INTEGER,
                last_visit_date INTEGER,
                hidden INTEGER
            );

            CREATE TABLE moz_historyvisits (
                id INTEGER PRIMARY KEY,
                from_visit INTEGER,
                place_id INTEGER,
                visit_date INTEGER,
                visit_type INTEGER,
                session INTEGER,
                source INTEGER
            );

            CREATE TABLE moz_inputhistory (
                place_id INTEGER,
                input TEXT
            );
            """
        )
        cur.execute(
            "INSERT INTO moz_places VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "https://example.org/path",
                "Example",
                3,
                2,
                _firefox_timestamp(visit_time),
                0,
            ),
        )
        cur.execute(
            "INSERT INTO moz_historyvisits VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                10,
                None,
                1,
                _firefox_timestamp(visit_time),
                1,
                99,
                None,
            ),
        )
        cur.execute(
            "INSERT INTO moz_inputhistory VALUES (?, ?)",
            (1, "Example query"),
        )
        con.commit()

    history = load_history(db_path)

    assert history.browser.value == "firefox"
    assert 1 in history.urls
    url = history.urls[1]
    assert url.hostname == "example.org"
    assert url.tld == "org"
    assert url.last_visit_time == visit_time

    visit = history.visits[0]
    assert visit.id == 10
    assert visit.url_id == 1
    assert visit.transition == "LINK"
    assert visit.referring_visit_id == 99
    assert visit.visit_time == visit_time

    search_terms = history.search_terms_for_url(1)
    assert len(search_terms) == 1
    assert search_terms[0].term == "Example query"


def test_load_history_without_copy_uses_original_path(tmp_path):
    db_path = tmp_path / "places_no_copy.sqlite"
    visit_time = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER,
                typed INTEGER,
                last_visit_date INTEGER,
                hidden INTEGER
            );

            CREATE TABLE moz_historyvisits (
                id INTEGER PRIMARY KEY,
                from_visit INTEGER,
                place_id INTEGER,
                visit_date INTEGER,
                visit_type INTEGER,
                session INTEGER,
                source INTEGER
            );
            """
        )
        cur.execute(
            "INSERT INTO moz_places VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "https://example.com",
                "Example",
                1,
                0,
                _firefox_timestamp(visit_time),
                0,
            ),
        )
        cur.execute(
            "INSERT INTO moz_historyvisits VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                5,
                None,
                1,
                _firefox_timestamp(visit_time),
                9,
                None,
                None,
            ),
        )
        con.commit()

    options = FirefoxHistoryOptions(copy_before_read=False)
    history = load_history(db_path, options=options)

    assert history.source_path == db_path
    assert len(history.search_terms_for_url(1)) == 0
    assert history.visits[0].transition == "RELOAD"
