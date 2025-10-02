"""Session reconstruction utilities for Browser Timeliner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .constants import DEFAULT_SESSION_IDLE_GAP
from .models import Session, VisitRecord


@dataclass(slots=True, frozen=True)
class SessionizerConfig:
    idle_gap_seconds: int = DEFAULT_SESSION_IDLE_GAP


class Sessionizer:
    """Deterministically group visits into sessions."""

    def __init__(self, config: Optional[SessionizerConfig] = None) -> None:
        self.config = config or SessionizerConfig()

    def build_sessions(self, visits: Iterable[VisitRecord]) -> Tuple[List[Session], Dict[int, str]]:
        visits_sorted = sorted(visits, key=lambda v: v.visit_time)
        sessions: List[Session] = []
        session_map: Dict[str, Session] = {}
        visit_to_session: Dict[int, str] = {}

        for visit in visits_sorted:
            assigned_session_id: Optional[str] = None

            if visit.from_visit and visit.from_visit in visit_to_session:
                assigned_session_id = visit_to_session[visit.from_visit]
            elif visit.referring_visit_id and visit.referring_visit_id in visit_to_session:
                assigned_session_id = visit_to_session[visit.referring_visit_id]

            if assigned_session_id is None:
                if sessions and self._within_idle_gap(visit, sessions[-1].end_time):
                    assigned_session_id = sessions[-1].id
                else:
                    assigned_session_id = self._create_session_id(visit)
                    session = Session(
                        id=assigned_session_id,
                        browser=visit.browser,
                        visits=[],
                        start_time=visit.visit_time,
                        end_time=visit.visit_time,
                        duration=timedelta(seconds=0),
                        seed_visit_id=visit.id,
                    )
                    sessions.append(session)
                    session_map[assigned_session_id] = session

            visit_to_session[visit.id] = assigned_session_id
            session = session_map[assigned_session_id]
            session.visits.append(visit)
            session.end_time = visit.visit_time
            session.duration = session.end_time - session.start_time

        return sessions, visit_to_session

    def _within_idle_gap(self, visit: VisitRecord, last_end: datetime) -> bool:
        return (visit.visit_time - last_end).total_seconds() <= self.config.idle_gap_seconds

    def _create_session_id(self, visit: VisitRecord) -> str:
        timestamp = int(visit.visit_time.timestamp())
        return f"{visit.browser.value}-{timestamp}-{visit.id}"
