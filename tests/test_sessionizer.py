from datetime import datetime, timedelta

from browser_timeliner.models import Browser, Session
from browser_timeliner.sessionizer import Sessionizer, SessionizerConfig
from browser_timeliner.models import VisitRecord


_BASE_TIME = datetime(2024, 1, 1, 12, 0, 0)


def _visit(visit_id: int, *, seconds: int, from_visit=None, referring_visit_id=None) -> VisitRecord:
    return VisitRecord(
        id=visit_id,
        url_id=visit_id,
        visit_time=_BASE_TIME + timedelta(seconds=seconds),
        from_visit=from_visit,
        referring_visit_id=referring_visit_id,
        transition="LINK",
        visit_source=None,
        browser=Browser.CHROMIUM,
    )


def test_sessionizer_splits_sessions_on_idle_gap():
    config = SessionizerConfig(idle_gap_seconds=60)
    sessionizer = Sessionizer(config)
    visits = [
        _visit(1, seconds=0),
        _visit(2, seconds=30, from_visit=1),
        _visit(3, seconds=200),
    ]

    sessions, visit_map = sessionizer.build_sessions(visits)

    assert len(sessions) == 2
    assert visit_map[1] == visit_map[2]
    assert visit_map[3] != visit_map[1]

    first_session = next(session for session in sessions if session.seed_visit_id == 1)
    assert first_session.start_time == visits[0].visit_time
    assert first_session.end_time == visits[1].visit_time

    second_session = next(session for session in sessions if session.seed_visit_id == 3)
    assert second_session.start_time == visits[2].visit_time
    assert second_session.end_time == visits[2].visit_time


def test_sessionizer_uses_referrer_to_link_across_gap():
    config = SessionizerConfig(idle_gap_seconds=60)
    sessionizer = Sessionizer(config)
    visits = [
        _visit(1, seconds=0),
        _visit(2, seconds=30, from_visit=1),
        _visit(3, seconds=400, from_visit=2),
    ]

    sessions, visit_map = sessionizer.build_sessions(visits)

    assert len(sessions) == 1
    session = sessions[0]
    assert {visit.id for visit in session.visits} == {1, 2, 3}
    assert visit_map[3] == visit_map[1]
