#!/usr/bin/env python3
"""
run.py - headless runner for the SEO Command Center.

Runs the full pipeline on one or two Screaming Frog exports:
  load -> detect -> fix recommendations -> report.json -> report.html -> optional PDF

Usage:
  python3 run.py sample-export/
  python3 run.py client-export/ competitor-export/
  python3 run.py sample-export/ --site-name "NMG Technologies" --pdf --no-ollama
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "outputs"
HISTORY_DIR = HERE / "history"
sys.path.insert(0, str(HERE / "mcp"))
sys.path.insert(0, str(HERE))

import server  # the MCP server module exposes every tool as a function
from agents.detector import load_export
from agents.fixer import generate_redirect_map, generate_titles_batch
from seo import detector as seo_detector


# Find affected URLs for a specific detector issue type.
def _affected_urls(issues, issue_type):
    for issue in issues:
        if issue.get("type") == issue_type:
            return issue.get("affected_urls", [])
    return []


# Return a unique list while preserving the original priority order.
def _unique(values):
    seen = set()
    ordered = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


# Build page contexts so the title fixer can use old title, H1, URL, and site name.
def _title_contexts(df, urls, site_name):
    clean_df = df.rename(columns=lambda x: str(x).strip())
    by_url = {}
    if "Address" in clean_df:
        for _, row in clean_df.iterrows():
            url = str(row.get("Address") or "").strip()
            if url and url not in by_url:
                by_url[url] = row
    contexts = []
    for url in urls:
        row = by_url.get(url)
        contexts.append({
            "url": url,
            "old": "" if row is None else str(row.get("Title 1") or "").strip(),
            "h1": "" if row is None else str(row.get("H1-1") or "").strip(),
            "site": site_name,
        })
    return contexts


# Write generated title fixes to outputs/fixes.csv.
def _write_title_fixes_csv(title_fixes):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "fixes.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "old_title", "new_title"])
        writer.writeheader()
        for fix in title_fixes:
            writer.writerow({
                "url": fix.get("url", ""),
                "old_title": fix.get("old", ""),
                "new_title": fix.get("new", ""),
            })
    return path


# Write generated redirect recommendations to outputs/redirect_map.csv.
def _write_redirect_map_csv(redirect_map):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "redirect_map.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["from", "to", "reason"])
        writer.writeheader()
        for row in redirect_map:
            writer.writerow({
                "from": row.get("from", ""),
                "to": row.get("to", ""),
                "reason": row.get("reason", ""),
            })
    return path


# Generate title and redirect fixes without letting fixer failures stop the audit.
def _generate_fixes(export_dir, issues, site_name, use_ollama):
    title_fixes = []
    redirect_map = []
    df = None
    try:
        df = load_export(Path(export_dir) / "internal_all.csv")
        candidates = []
        for issue_type in ["missing_title", "duplicate_title", "title_too_long"]:
            candidates.extend(_affected_urls(issues, issue_type))
        urls_to_fix = _unique(candidates)[:20]
        contexts = _title_contexts(df, urls_to_fix, site_name)
        title_fixes = generate_titles_batch(contexts, site_name=site_name, use_ollama=use_ollama)
    except Exception as e:
        print(f"[seo] warning: title fixes skipped: {e}", flush=True)
    try:
        if df is None:
            df = load_export(Path(export_dir) / "internal_all.csv")
        redirect_map = generate_redirect_map(df)
    except Exception as e:
        print(f"[seo] warning: redirect map skipped: {e}", flush=True)
    try:
        _write_title_fixes_csv(title_fixes)
        _write_redirect_map_csv(redirect_map)
    except Exception as e:
        print(f"[seo] warning: fix CSV export skipped: {e}", flush=True)
    return title_fixes, redirect_map


# Convert a site name into a stable filename slug.
def _site_slug(site):
    slug = re.sub(r"[^a-z0-9]+", "", str(site or "site").lower())
    return slug or "site"


# Find the most recent saved audit for the same site slug.
def _load_previous_audit(site_slug):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(HISTORY_DIR.glob(f"{site_slug}_*.json"))
    if not paths:
        return None
    try:
        with open(paths[-1], encoding="utf-8") as f:
            data = json.load(f)
        return {"path": str(paths[-1]), "data": data}
    except Exception:
        return None


# Build the previous-audit comparison object for the report.
def _previous_audit_comparison(site_slug, current_score):
    previous = _load_previous_audit(site_slug)
    if not previous:
        return None
    previous_score = int(previous["data"].get("health_score") or previous["data"].get("score_breakdown", {}).get("score") or 0)
    return {
        "previous_score": previous_score,
        "current_score": int(current_score),
        "delta": int(current_score) - previous_score,
        "path": previous["path"],
    }


# Save the completed report JSON into history with a timestamped filename.
def _save_history(report_obj, site_slug):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = HISTORY_DIR / f"{site_slug}_{stamp}.json"
    if path.exists():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = HISTORY_DIR / f"{site_slug}_{stamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_obj, f, indent=2)
    return path


# Map detected issues by type for competitor comparisons.
def _issue_map(issues):
    return {issue.get("type"): issue for issue in issues or []}


# Build a competitor gap analysis from two deterministic audits.
def _competitive_gap(client_issues, competitor_dir):
    if not competitor_dir:
        return None
    competitor_rows = seo_detector.load_rows(str(competitor_dir))
    competitor_issues = seo_detector.detect(competitor_rows)
    client_map = _issue_map(client_issues)
    competitor_map = _issue_map(competitor_issues)
    client_score = server._score_breakdown(client_issues)["score"]
    competitor_score = server._score_breakdown(competitor_issues)["score"]
    client_only = []
    competitor_better = []
    for issue_type, issue in client_map.items():
        competitor_issue = competitor_map.get(issue_type)
        client_count = int(issue.get("count") or 0)
        competitor_count = int((competitor_issue or {}).get("count") or 0)
        if competitor_issue is None:
            client_only.append({
                "type": issue_type,
                "severity": issue.get("severity"),
                "client_count": client_count,
            })
        if client_count > competitor_count:
            competitor_better.append({
                "type": issue_type,
                "severity": issue.get("severity"),
                "client_count": client_count,
                "competitor_count": competitor_count,
                "delta": client_count - competitor_count,
            })
    return {
        "competitor_dir": str(competitor_dir),
        "client_score": client_score,
        "competitor_score": competitor_score,
        "score_gap": competitor_score - client_score,
        "client_only_issues": sorted(client_only, key=lambda x: -int(x.get("client_count") or 0))[:10],
        "competitor_better_areas": sorted(competitor_better, key=lambda x: -int(x.get("delta") or 0))[:10],
    }


# Write report.pdf with WeasyPrint when the optional dependency is installed.
def _write_pdf_report():
    html_path = OUTPUT_DIR / "report.html"
    pdf_path = OUTPUT_DIR / "report.pdf"
    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return pdf_path
    except Exception as e:
        print(f"[seo] warning: PDF export skipped: {e}", flush=True)
        return None


# Read the current report JSON from outputs for history archiving.
def _load_current_report():
    with open(OUTPUT_DIR / "report.json", encoding="utf-8") as f:
        return json.load(f)


# Build the command-line parser for production audit runs.
def _parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("competitor_dir", nargs="?")
    ap.add_argument("--site-name", default="")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--no-ollama", action="store_true")
    ap.add_argument("--no-dashboard", action="store_true")
    return ap


# Run the full SEO audit pipeline and write report artifacts.
def main():
    args = _parser().parse_args()
    export_dir = Path(args.export_dir)
    competitor_dir = Path(args.competitor_dir) if args.competitor_dir else None

    if not args.no_dashboard:
        server.start_dashboard()
        print(f"[seo] dashboard: http://localhost:{server.PORT}", flush=True)
        time.sleep(1)

    t0 = time.time()
    server.seo_load(str(export_dir), site_name=args.site_name or None)
    server.seo_detect()
    site_name = args.site_name or server.RUN["site"]
    server.RUN["site"] = site_name

    title_fixes, redirect_map = _generate_fixes(
        export_dir,
        server.RUN["issues"],
        site_name,
        use_ollama=not args.no_ollama,
    )
    server.seo_set_fixes(titles=title_fixes, redirect_map=redirect_map)

    issues = sorted(server.RUN["issues"],
                    key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x["severity"], 3),
                                   -int(x.get("count") or 0)))
    recs = [f"Fix {i['type'].replace('_', ' ')} on {i['count']} URL(s): {server._business_impact(i)}"
            for i in issues[:5]]
    if not recs:
        recs.append("No issues detected on this crawl.")
    server.seo_recommend(recs)

    server.RUN["competitive_gap"] = _competitive_gap(server.RUN["issues"], competitor_dir)
    site_slug = _site_slug(site_name)
    server.RUN["previous_audit"] = _previous_audit_comparison(site_slug, server.RUN.get("health_score", 100))
    server.RUN["model_calls"] = 0 if args.no_ollama else len(title_fixes)
    server.RUN["duration_sec"] = round(time.time() - t0, 1)
    server.seo_report()
    server.seo_export()
    report_obj = _load_current_report()
    history_path = _save_history(report_obj, site_slug)
    pdf_path = _write_pdf_report() if args.pdf else None

    if not args.no_dashboard:
        print(f"\n[seo] Dashboard is live. Keeping process alive for 60s for final snapshot...")
        time.sleep(60)

    s = server.RUN["summary"]
    print("\n=== SEO AUDIT RESULT ===")
    print(f"Site         : {server.RUN['site']}  ({server.RUN['urls']} URLs)")
    print(f"Score        : {server.RUN.get('health_score', 100)}/100")
    print(f"Total issues : {s['total_issues']}  (High {s['by_severity'].get('High', 0)} / "
          f"Medium {s['by_severity'].get('Medium', 0)} / Low {s['by_severity'].get('Low', 0)})")
    print(f"History      : {history_path}")
    if pdf_path:
        print(f"PDF          : {pdf_path}")
    print("Wrote outputs/report.json, outputs/report.html, outputs/fixes.csv, and outputs/redirect_map.csv")


if __name__ == "__main__":
    main()
