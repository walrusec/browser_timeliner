# Browser Timeliner

CLI utility to covert Chromium and Firefox history artifacts into timelines using json, csv, xlsx, html outputs.
Analyze results against established rules to identify events of interest and anomalies straight from the terminal.

## Quick start

```bash
python3.11 -m venv timeliner && source timeliner/bin/activate
python3.11 -m pip install browser-timeliner
browser-timeliner /path/to/profile-or-history-file --summary-only --export timeline.csv --export-format csv
```

https://github.com/user-attachments/assets/01b9bef4-228e-41d1-b7b0-25da4c55af96

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
