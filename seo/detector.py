"""
detector.py — deterministic SEO issue detection from a Screaming Frog internal_all.csv.

Detection is pure Python orchestration plus pandas rules. The model is only for judgment
work such as rewriting titles/metas or choosing redirect targets.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

import pandas as pd

from agents.detector import DETECTOR_CHECKS, detect_all


# Load internal_all.csv rows from a Screaming Frog export folder.
def load_rows(export_dir: str) -> list[dict]:
    path = os.path.join(export_dir, "internal_all.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# Run detector checks over crawl rows and optionally stream progress.
def detect(rows: list[dict], progress=None) -> list[dict]:
    """Return issue dicts: {type, severity, affected_urls, count, explanation}."""
    return detect_all(pd.DataFrame(rows), progress=progress)


# Summarize issue types by severity.
def summarize(issues: list[dict]) -> dict:
    by_sev = defaultdict(int)
    for i in issues:
        by_sev[i["severity"]] += 1
    return {"total_issues": len(issues),
            "by_severity": {"High": by_sev["High"], "Medium": by_sev["Medium"], "Low": by_sev["Low"]}}


if __name__ == "__main__":
    import sys
    import json

    d = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(d)
    iss = detect(rows)
    print(f"Loaded {len(rows)} rows, detected {len(iss)} issue types.")
    print(json.dumps(summarize(iss), indent=2))
    for i in iss:
        print(f"  [{i['severity']:<6}] {i['type']:<32} x{i['count']}")
