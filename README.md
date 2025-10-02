# Browser Timeliner

Browser Timeliner turns Chromium and Firefox history artifacts into timelines, rule hits, and anomaly callouts straight from the terminal.

## Quick start

```bash
python3.11 -m pip install browser-timeliner
browser-timeliner /path/to/profile --summary-only
```

- Python 3.11.x is required (`pyproject.toml` pins `==3.11.*`).
- Use a virtual environment for isolation (`python3.11 -m venv timeliner && source timeliner/bin/activate`).

## Documentation

- **Deep dive usage, packaging, and development guide:** `docs/USAGE.md`
- **Contribution guidelines:** `CONTRIBUTING.md`

## Repository layout

- `browser_timeliner/` – CLI (`cli.py`), ingestion readers, rule engine, anomaly detector, exporter, and models.
- `tests/` – pytest coverage for ingestion, CLI, exporter, rules, anomalies, and integration paths.
- `docs/USAGE.md` – expanded installation, CLI, and packaging instructions.

## Links

- PyPI: https://pypi.org/project/browser-timeliner/
- GitHub: https://github.com/walrusec/browser_timeliner
