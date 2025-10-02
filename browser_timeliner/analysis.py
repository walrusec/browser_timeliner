"""End-to-end analysis pipeline for Browser Timeliner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .anomaly_detector import AnomalyConfig, AnomalyDetector
from .logging_config import get_logger
from .ingest import load_inputs
from .models import (
    AnalysisResult,
    Anomaly,
    HistoryData,
    PreferencesData,
    RuleMatch,
    Session,
)
from .rule_engine import RuleEngine, RuleSet, load_default_rules
from .sessionizer import Sessionizer, SessionizerConfig


logger = get_logger(__name__)


@dataclass(slots=True)
class AnalysisOptions:
    copy_before_read: bool = True
    sessionizer_config: SessionizerConfig = field(default_factory=SessionizerConfig)
    anomaly_config: AnomalyConfig = field(default_factory=AnomalyConfig)
    rule_set: Optional[RuleSet] = None


def analyze_artifacts(
    *,
    history: Optional[HistoryData],
    preferences: Optional[PreferencesData],
    options: Optional[AnalysisOptions] = None,
) -> AnalysisResult:
    opts = options or AnalysisOptions()
    logger.debug(
        "Starting artifact analysis",
        extra={
            "history_present": history is not None,
            "preferences_present": preferences is not None,
            "rule_set_provided": opts.rule_set is not None,
        },
    )
    sessions: List[Session] = []
    visit_to_session: Dict[int, str] = {}
    rule_matches: Dict[int, List[RuleMatch]] = {}
    anomalies: List[Anomaly] = []

    if history:
        sessionizer = Sessionizer(opts.sessionizer_config)
        sessions, visit_to_session = sessionizer.build_sessions(history.visits)

        if opts.rule_set is None:
            rule_set = load_default_rules()
        else:
            rule_set = opts.rule_set
        rule_engine = RuleEngine(rule_set)
        rule_matches = rule_engine.evaluate(history)

        anomaly_detector = AnomalyDetector(opts.anomaly_config)
        anomalies = anomaly_detector.evaluate(history, sessions, rule_matches, visit_to_session)
    else:
        rule_set = opts.rule_set or load_default_rules()

    result = AnalysisResult(
        history=history,
        sessions=sessions,
        anomalies=anomalies,
        visit_to_session=visit_to_session,
        rule_matches=rule_matches,
        rules=rule_set.rules,
        preferences=preferences,
    )

    logger.info(
        "Artifact analysis completed",
        extra={
            "session_count": len(sessions),
            "anomaly_count": len(anomalies),
            "rule_count": len(result.rules),
        },
    )
    return result


def analyze_history(path: Path, *, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
    logger.info("Analyzing input path", extra={"input_path": str(path)})
    history, preferences = load_inputs(Path(path))
    if history is None and preferences is None:
        logger.warning("No artifacts detected at path", extra={"input_path": str(path)})
        raise ValueError("No supported history or preferences artifacts found at provided path")
    logger.debug(
        "Artifacts loaded",
        extra={
            "history_present": history is not None,
            "preferences_present": preferences is not None,
        },
    )
    return analyze_artifacts(history=history, preferences=preferences, options=options)
