# Contributing to Browser Timeliner

This project welcomes contributions from threat analysts and investigators who want to extend detection coverage. This guide focuses on analyst workflows (rule tuning, taxonomy updates, validation) rather than software engineering internals.

## Prerequisites
- Python 3.11+ available as `python3`
- Local checkout of this repository
- (Optional) Virtual environment with project dependencies installed:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e .
  ```

## Core Concepts
- **Rule YAML** (`browser_timeliner/rules/default_rules.yaml`): Declarative detection logic. Each entry supplies `name`, `category`, severity metadata, and `conditions`.
- **Categories** (`browser_timeliner/categories.py`): Canonical vocabulary enforced across rules, anomaly detection, and exports. Add new values only when necessary; keep names lowercase with underscores (e.g., `threat_indicator`).
- **Rule Engine** (`browser_timeliner/rule_engine.py`): Converts YAML into executable checks. When adding new condition types, ensure both the YAML and `RuleCondition` support them.
- **Anomaly Detection** (`browser_timeliner/anomaly_detector.py`): Additional heuristics that emit alerts based on sessions, downloads, or rule matches.

## Updating Rules
1. **Pick the right category**
   - Use an existing enum from `categories.py` whenever possible.
   - If a new category is unavoidable, add it to the enum and document the intent in the file’s docstring.
2. **Define precise conditions**
   - Prefer `hostname_suffixes`, `path_extensions`, `url_contains`, or `ip_ranges` over broad free-text matches.
   - Avoid overlapping rules that trigger on every visit; include exclusions (`exclude_local`, IP network ranges, etc.) as needed.
3. **Severity & metadata**
   - `severity`: `informational`, `low`, `medium`, `high`, or `critical`.
   - `risk_score`: Integer 0–100 reflecting analyst urgency.
   - `false_positive_rate`: One of `very_low`, `low`, `medium`, `high`, `very_high`.
   - Optional fields (`tags`, `ioc_type`) should convey additional context, not duplicate the category.
4. **Validation**
   - Run targeted tests where applicable:
     ```bash
     python3 -m pytest tests/test_rule_conditions.py
     python3 -m pytest tests/test_exporter.py
     python3 -m pytest tests/test_preferences_parser.py
     ```
   - Execute sample exports to confirm behavior:
     - Timeline export with filters:
       ```bash
       python3 -m browser_timeliner.cli "$HOME/Downloads/History" \
         --summary-only \
         --export timeline.csv \
         --filter anomalies --filter rules
       ```
     - Preferences export:
       ```bash
       python3 -m browser_timeliner.cli "$HOME/Downloads/History" \
         --summary-only \
         --export timeline.csv \
         --export-preferences preferences.csv
       ```
     - Zip profile ingestion:
       ```bash
       python3 -m browser_timeliner.cli "$HOME/Downloads/profile.zip" \
         --summary-only \
         --export timeline.csv \
         --export-preferences preferences.csv
       ```
   - Inspect generated CSV/JSON exports for new `rule_names`, `rule_categories`, and anomaly fields.

## Adding/Modifying Categories
- Update `browser_timeliner/categories.py`.
- Review `anomaly_detector.py` and `AnalysisConfig` to ensure new categories are handled (e.g., include in `high_severity_categories` if appropriate).
- Update documentation and tests referencing categories (e.g., exporter schema tests).

## Workflow Tips
- Keep rule names human-readable; they appear in exports and CLI output.
- Use version control branches for rule changes. Include before/after evidence (sample URLs, reasoning) in commit messages or pull request descriptions.
- When in doubt, add comments in YAML using `#` to explain detection context for other analysts.
- Leverage CLI filters (`--filter anomalies`, `--filter downloads`, etc.) and `--summary-only` to quickly validate changes on large datasets.
- For Chromium preferences, review enriched extension metadata (enabled state, version, permissions) via the preferences export to verify parser updates.

## Submitting Changes
1. Run the full test suite: `python3 -m pytest`.
2. Ensure CLI exports succeed without errors.
3. Open a pull request summarizing:
   - New or modified rules
   - Category additions or taxonomy changes
   - Testing performed and sample findings

Thank you for helping improve Browser Timeliner’s analytic coverage!
