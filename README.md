# Browser Timeliner

Browser Timeliner is a forensic toolkit for security analysts to ingest, inspect, and annotate browser history databases from Chromium-based browsers and Mozilla Firefox using a command-line workflow.

## Goals

- Deterministic session reconstruction using referrer chains.
- Unified timeline view with tagging, notes, and anomaly detection.
- Minimal, pinned dependencies for long-term reproducibility.
- Command-line workflow for artifact analysis.

## Repository Layout (work in progress)

- `browser_timeliner/` – Core Python package.
- `docs/` – Design notes and reference material.
- `tests/` – Automated checks using pytest.
- `browser_timeliner/cli.py` is the main entry point.

## Requirements

- Python 3.11
- Hatch 1.21.1 (or run within an isolated virtual environment using `pip`)

## Installation

### Local editable install (recommended for development)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python3.11 -m pip install --upgrade pip
python3.11 -m pip install -e '.[test]'
```

This installs Browser Timeliner in editable mode with the test extras (currently `pytest==8.2.2`). The `browser-timeliner` console entry point becomes available inside the virtual environment.

### Installing from an existing wheel

If you have a built wheel in `dist/`, install it into a clean environment:

```bash
python3.11 -m venv timeliner-env
source timeliner-env/bin/activate
python3.11 -m pip install dist/browser_timeliner-0.1.0-py3-none-any.whl
```

### Installing from PyPI (when published)

```bash
python3.11 -m pip install browser-timeliner
```

All distributions require Python 3.11.x because of the constraint in `pyproject.toml` (`requires-python = "==3.11.*"`).

### Building release artifacts

Create source and wheel artifacts for distribution:

```bash
python3.11 -m pip install build
python3.11 -m build
```

Generated files are placed in the `dist/` directory and can be uploaded to PyPI or shared internally.

## Packaging and CLI executable

The project exposes a console command via the entry point declared in `pyproject.toml`:

```toml
[project.scripts]
browser-timeliner = "browser_timeliner.cli:main"
```

- **Installable CLI**: After `pip install .`, the `browser-timeliner` console script becomes available. You can also invoke the module directly with `python -m browser_timeliner.cli`.
- **Input sources**: Point the CLI at:
  - A Chromium/Firefox history SQLite database.
  - A directory containing `History` and/or `Preferences` artifacts.
  - A standalone Chromium `Preferences` file.
  - A `.zip` archive containing any of the above (the CLI extracts and auto-detects the relevant files).
- **Key flags**:
  - `--rules <rules.yaml>` overrides the default rule pack.
  - `--format {table,json}` switches between table output and raw JSON.
  - `--summary-only` prints the ingest/export summary without rendering full session tables.
  - `--session <session-id>` narrows output to a specific session.
  - `--filter anomalies|downloads|visits|rules` (repeatable) restricts exported rows to matching categories.
  - `--export <file>` writes the unified timeline (CSV/JSON/HTML/XLSX based on extension or `--export-format`).
  - `--export-preferences <file>` emits a dedicated preferences export (CSV/JSON/HTML based on extension or `--export-preferences-format`).
  - `--log-level`, `--log-format`, and `--correlation-id` control structured logging (see below).

### Running the CLI

Activate your environment (if using a venv) and provide an input artifact path:

```bash
source .venv/bin/activate
browser-timeliner /path/to/profile --summary-only
```

Examples:

- **Analyze a Chromium profile directory**

  ```bash
  browser-timeliner ~/Evidence/ChromeProfile --export timeline.csv
  ```

- **Process a single history database**

  ```bash
  browser-timeliner ~/Evidence/History --format json
  ```

- **Handle a zipped artifact bundle**

  ```bash
  browser-timeliner ~/Evidence/profile.zip --summary-only
  ```

- **Use a custom rules pack and filter anomalies**

  ```bash
  browser-timeliner ~/Evidence/FirefoxProfile \
    --rules custom_rules.yaml \
    --filter anomalies \
    --export anomalies.csv
  ```

Run `browser-timeliner --help` to review all supported flags.

### Logging controls

- **Environment overrides**: `BROWSER_TIMELINER_LOG_LEVEL` and `BROWSER_TIMELINER_LOG_FORMAT` (values: `json`, `console`).
- **Correlation IDs**: Pass `--correlation-id` or let the CLI generate one; all log records include it.
- **Structured output**: JSON logs include timestamps, severity, module name, correlation ID, and contextual fields for ingestion into SIEM/SOAR platforms.

## Architecture overview

### Execution flow

- **Entry point**: `browser_timeliner.cli:main()` parses CLI flags, configures logging via `browser_timeliner.logging_config`, and orchestrates the analysis pipeline.
- **Ingestion**: `browser_timeliner.ingest.load_inputs()` determines artifact types, leveraging `browser_timeliner.chromium_reader` / `browser_timeliner.firefox_reader` and `browser_timeliner.preferences_parser` for data loading.
- **Analysis**: `browser_timeliner.analysis.analyze_artifacts()` runs sessionization, rule evaluation, and anomaly detection to produce an `AnalysisResult` from `browser_timeliner.models`.
- **Presentation**: Depending on CLI options, `browser_timeliner.cli` renders tables, emits JSON payloads, or calls `browser_timeliner.exporter` to persist exports.

### Module reference

- **`browser_timeliner/__init__.py`**: Declares package metadata (`__version__`).
- **`browser_timeliner/cli.py`**: CLI front end. Configures logging, loads custom rules, invokes analysis, renders output, and manages exports. Depends on `analysis`, `logging_config`, `rule_engine`, `exporter`, and `models`.
- **`browser_timeliner/logging_config.py`**: Centralized enterprise-grade logging. Provides environment-aware configuration, JSON/console formatters, correlation ID context management, and helper accessors (`get_logger`).
- **`browser_timeliner/analysis.py`**: Coordinates end-to-end analysis. Instantiates `Sessionizer`, `RuleEngine`, and `AnomalyDetector`, returning an `AnalysisResult`. Emits lifecycle logging and defaults rule sets if none provided.
- **`browser_timeliner/ingest.py`**: Detects artifact types, loads history/preference data, and reports ingestion outcomes. Uses `chromium_reader`, `firefox_reader`, `preferences_parser`, `utils.validate_sqlite_file`, and `models`.
- **`browser_timeliner/chromium_reader.py`**: Reads Chromium history SQLite databases. Normalizes visits, downloads, and search terms into `HistoryData` while applying URL parsing via `domain_utils` and timestamp conversion utilities.
- **`browser_timeliner/firefox_reader.py`**: Equivalent loader for Firefox artifacts using browser-specific schema handling.
- **`browser_timeliner/preferences_parser.py`**: Parses Chromium `Preferences` JSON into the structured `PreferencesData` model, mapping nested settings (extensions, notifications, proxy configuration, etc.).
- **`browser_timeliner/models.py`**: Dataclass definitions for all core entities (history records, sessions, anomalies, rules, preferences). Shared across ingestion, analysis, exporting, and tests.
- **`browser_timeliner/sessionizer.py`**: Deterministic session reconstruction based on referrer relationships and idle gaps. Produces `Session` objects and visit-to-session mappings.
- **`browser_timeliner/rule_engine.py`**: Loads YAML rule definitions (`browser_timeliner/rules/default_rules.yaml`), parses conditions, and evaluates them against visits to produce `RuleMatch` records while tagging URLs.
- **`browser_timeliner/anomaly_detector.py`**: Applies heuristic anomaly detection over visits and sessions using categories from `browser_timeliner.categories` and constants from `browser_timeliner.constants`.
- **`browser_timeliner/categories.py`**: Enum of analytic categories referenced by rules, anomaly detection, and reporting.
- **`browser_timeliner/constants.py`**: Shared constants (epoch offsets, suspicious TLD sets, idle thresholds) consumed by utilities and analyzers.
- **`browser_timeliner/domain_utils.py`**: URL parsing helper used by Chromium ingestion to extract host, TLD, IP flags, and file extensions.
- **`browser_timeliner/exporter.py`**: Transforms analysis results into CSV/JSON/HTML/XLSX exports. Contains structured logging detailing export statistics.
- **`browser_timeliner/utils.py`**: Miscellaneous helpers (timestamp conversions, SQLite validation, dataclass serialization) reused across readers and ingest.
- **`browser_timeliner/rules/default_rules.yaml`**: Curated rule pack distributed with the CLI. Custom packs can be supplied via `--rules`.

### Supporting tests

- **`tests/test_ingest.py`**: Validates ingestion detection and parsing paths.
- **`tests/test_exporter.py`**: Ensures timeline exports serialize expected structures.
- **`tests/test_preferences_parser.py`**: Covers preference parsing edge cases.

### Extending the toolkit

- **Custom rules**: Add YAML files mirroring the schema in `browser_timeliner/rules/default_rules.yaml` and provide them with `--rules`.
- **New data sources**: Implement additional readers that return `HistoryData` / `PreferencesData` and register them in `browser_timeliner.ingest` detection logic.
- **Integrations**: The structured logging and export utilities are designed to feed SIEM/SOAR systems or downstream automation pipelines.
