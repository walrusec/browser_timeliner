"""Rule evaluation engine for Browser Timeliner."""

from __future__ import annotations

import importlib.resources as resources
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for rule parsing. Install with the pinned version from requirements.") from exc

from .categories import Category
from .logging_config import get_logger
from .models import HistoryData, RuleCondition, RuleDefinition, RuleMatch


logger = get_logger(__name__)


@dataclass(slots=True)
class RuleSet:
    rules: Sequence[RuleDefinition]
    version: int
    metadata: Dict[str, str]


class RuleEngine:
    """Evaluate rules against history data."""

    def __init__(self, rules: RuleSet) -> None:
        self.rules = [rule for rule in rules.rules if rule.enabled]

    def evaluate(self, history: HistoryData) -> Dict[int, List[RuleMatch]]:
        matches: Dict[int, List[RuleMatch]] = {}
        for visit in history.visits:
            url = history.urls.get(visit.url_id)
            if url is None:
                continue
            url_matches: List[RuleMatch] = []
            search_terms = history.search_terms_for_url(visit.url_id)
            for rule in self.rules:
                match = rule.matches(url, visit, search_terms)
                if match:
                    url_matches.append(match)
                    url.categories.add(rule.category)
            if url_matches:
                matches[visit.id] = url_matches
        return matches


def load_rules_from_file(path: Path) -> RuleSet:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Rules file must be a mapping")
    version = int(data.get("version", 1))
    metadata = {str(k): str(v) for k, v in (data.get("metadata") or {}).items()}
    rule_defs: List[RuleDefinition] = []
    for entry in data.get("rules", []):
        rule_defs.append(_parse_rule_entry(entry))
    return RuleSet(rules=tuple(rule_defs), version=version, metadata=metadata)


def load_default_rules() -> RuleSet:
    with resources.files("browser_timeliner.rules").joinpath("default_rules.yaml").open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Default rules file is malformed")
    version = int(data.get("version", 1))
    metadata = {str(k): str(v) for k, v in (data.get("metadata") or {}).items()}
    rule_defs = [_parse_rule_entry(entry) for entry in data.get("rules", [])]
    return RuleSet(rules=tuple(rule_defs), version=version, metadata=metadata)


def _parse_rule_entry(entry: dict) -> RuleDefinition:
    if not isinstance(entry, dict):
        raise ValueError("Rule entries must be mappings")
    name = str(entry.get("name"))
    category_raw = entry.get("category")
    if category_raw is None:
        raise ValueError(f"Rule '{name}' is missing required 'category'")
    category = str(category_raw)
    if not Category.has_value(category):
        logger.error(
            "Rule references unknown category",
            extra={"rule": name, "category": category},
        )
        raise ValueError(
            f"Rule '{name}' references unknown category '{category}'. "
            "Update browser_timeliner/categories.py or fix the rule definition."
        )
    severity = str(entry.get("severity", "medium"))
    description = str(entry.get("description", ""))
    enabled = bool(entry.get("enabled", True))
    tags = [str(tag) for tag in entry.get("tags", [])]
    conditions_raw = entry.get("conditions", {})
    condition = _parse_conditions(conditions_raw)
    return RuleDefinition(
        name=name,
        category=category,
        severity=severity,
        description=description,
        conditions=condition,
        enabled=enabled,
        tags=tags,
    )


def _parse_conditions(raw: dict) -> RuleCondition:
    if not isinstance(raw, dict):
        raise ValueError("conditions must be a mapping")
    return RuleCondition(
        tlds={_lower(x) for x in raw.get("tlds", [])},
        hostname_suffixes={_lower(x) for x in raw.get("hostname_suffixes", [])},
        hostname_exact={_lower(x) for x in raw.get("hostname_exact", [])},
        hostname_contains={_lower(x) for x in raw.get("hostname_contains", [])},
        path_prefixes={_normalize_prefix(x) for x in raw.get("path_prefixes", [])},
        path_extensions={_lower(x) for x in raw.get("path_extensions", [])},
        path_contains={_lower(x) for x in raw.get("path_contains", [])},
        url_contains={_lower(x) for x in raw.get("url_contains", [])},
        query_contains={_lower(x) for x in raw.get("query_contains", [])},
        search_terms={_lower(x) for x in raw.get("search_terms", [])},
        require_ip=bool(raw.get("require_ip", False)),
        exclude_local=bool(raw.get("exclude_local", False)),
        schemes={_lower(x) for x in raw.get("schemes", [])},
        contains_unicode=bool(raw.get("contains_unicode", False)),
        mixed_scripts=bool(raw.get("mixed_scripts", False)),
        ip_ranges=tuple(str(x).strip() for x in raw.get("ip_ranges", [])),
    )


def _lower(value: str) -> str:
    return value.lower().strip()


def _normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip()
    if not prefix.startswith("/"):
        return "/" + prefix
    return prefix
