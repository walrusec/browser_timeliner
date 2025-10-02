# Browser Timeliner Usage Guide

This guide expands on the quick start instructions in the top-level `README.md` and covers detailed installation paths, CLI usage patterns, packaging, and project architecture.

---

## Installation options

### Install from PyPI (recommended)

```bash
python3.11 -m pip install --upgrade pip
python3.11 -m pip install browser-timeliner
```

- **Upgrade later**: `python3.11 -m pip install --upgrade browser-timeliner`
- **Virtual environment**: `python3.11 -m venv timeliner && source timeliner/bin/activate`
- Python 3.11.x is required because `pyproject.toml` pins `requires-python = "==3.11.*"`.

### Local editable install for development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python3.11 -m pip install --upgrade pip
python3.11 -m pip install -e '.[test]'
python3 -m pytest
```

This installs Browser Timeliner in editable mode with the `test` extras (currently `pytest==8.2.2`) and exposes the `browser-timeliner` console script inside the environment.

### Install from an existing wheel

If you have built artifacts in `dist/`, install them into a clean environment:

```bash
python3.11 -m venv timeliner-wheel
source timeliner-wheel/bin/activate
python3.11 -m pip install dist/browser_timeliner-0.1.0-py3-none-any.whl
```

---

## Running the CLI

`browser-timeliner` accepts a Chromium or Firefox history database, a preferences file, an entire profile directory, or a zip bundle containing artifacts. A quick summary-only run looks like this:

```bash
browser-timeliner /path/to/profile --summary-only
```

Common scenarios:

- **Export a full timeline CSV**
  ```bash
  browser-timeliner ~/Evidence/ChromeProfile --export timeline.csv
  ```

- **Inspect raw JSON output**
  ```bash
  browser-timeliner ~/Evidence/History --format json
  ```

- **Use a custom rules pack and focus on anomalies**
  ```bash
  browser-timeliner ~/Evidence/FirefoxProfile \
    --rules custom_rules.yaml \
    --filter anomalies \
    --export anomalies.csv
  ```

Run `browser-timeliner --help` to view the complete set of flags, including session filtering, structured logging controls, export formats, and preference export options.

---

## Packaging and publishing

Create release artifacts and publish them to PyPI or TestPyPI:

```bash
python3.11 -m pip install --upgrade build twine
python3.11 -m build           # dist/browser_timeliner-*.whl + *.tar.gz
python3.11 -m twine upload dist/*
```

Artifacts are written to the `dist/` directory and can be distributed manually, attached to GitHub releases, or uploaded to package indexes.

---

## Project structure

- `browser_timeliner/cli.py` — entry point orchestrating ingestion, analysis, exporting, and logging.
- `browser_timeliner/chromium_reader.py` & `browser_timeliner/firefox_reader.py` — normalize Chromium/Firefox history databases into shared models.
- `browser_timeliner/preferences_parser.py` — parse Chromium `Preferences` JSON artifacts into structured data.
- `browser_timeliner/rule_engine.py` + `browser_timeliner/rules/default_rules.yaml` — evaluate YAML-defined detections.
- `browser_timeliner/anomaly_detector.py`, `browser_timeliner/sessionizer.py`, and `browser_timeliner/exporter.py` — generate anomalies, sessions, and output files.
- `browser_timeliner/models.py` — dataclasses representing the core entities used throughout the pipeline.
- `tests/` — pytest coverage for ingest, CLI, exporter, preferences parsing, rule engine, anomaly detection, sessionizer, and analysis integration.

---

## Extending the toolkit

- **Custom rules**: Supply additional YAML files that mirror `browser_timeliner/rules/default_rules.yaml` and load them with `--rules`.
- **New data sources**: Implement readers that return `HistoryData` or `PreferencesData` and register them in `browser_timeliner.ingest`.
- **Integrations**: Structured logging and exporter outputs are designed to feed SIEM/SOAR pipelines; adapt them as needed for your environment.
