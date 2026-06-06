#!/usr/bin/env python3
"""
run.py — headless runner for the SEO Command Center (also the grader's entry point).

Runs the full pipeline on a Screaming Frog export with no Claude Code:
  load -> detect -> (starter recommendations) -> write report.json + report.html

Usage:
  python run.py sample-export/
  python run.py sample-export/ --no-dashboard

The model-driven fixes (title rewriting, redirect map) are left as a Sprint TODO; the
starter writes empty fix blocks so the contract stays valid.
"""
from __future__ import annotations
import argparse, csv, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mcp"))
sys.path.insert(0, HERE)
import server  # the MCP server module exposes every tool as a function
from agents.detector import load_export
from agents.fixer import generate_redirect_map, generate_titles_batch


# Find affected URLs for a specific detector issue type.
def _affected_urls(issues, issue_type):
    for issue in issues:
        if issue.get("type") == issue_type:
            return issue.get("affected_urls", [])
    return []


# Write generated title fixes to outputs/fixes.csv.
def _write_title_fixes_csv(title_fixes):
    os.makedirs(os.path.join(HERE, "outputs"), exist_ok=True)
    path = os.path.join(HERE, "outputs", "fixes.csv")
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
    os.makedirs(os.path.join(HERE, "outputs"), exist_ok=True)
    path = os.path.join(HERE, "outputs", "redirect_map.csv")
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
def _generate_fixes(export_dir, issues):
    title_fixes = []
    redirect_map = []
    try:
        # Priority sequence for title fixes
        candidates = []
        for issue_type in ["missing_title", "duplicate_title", "title_too_long"]:
            candidates.extend(_affected_urls(issues, issue_type))

        # Ensure we have a unique list of URLs and at least 5 if possible
        unique_candidates = []
        for url in candidates:
            if url not in unique_candidates:
                unique_candidates.append(url)

        # Take a reasonable slice (e.g., top 20) to avoid model budget blowouts,
        # but ensure at least 5 if available.
        urls_to_fix = unique_candidates[:20] if unique_candidates else []
        if not urls_to_fix and len(unique_candidates) == 0:
            # If no titles need fixing, we can't invent URLs, but we've tried the priority list.
            pass

        title_fixes = generate_titles_batch(urls_to_fix)
    except Exception as e:
        print(f"[seo] warning: title fixes skipped: {e}", flush=True)
    try:
        df = load_export(os.path.join(export_dir, "internal_all.csv"))
        redirect_map = generate_redirect_map(df)
    except Exception as e:
        print(f"[seo] warning: redirect map skipped: {e}", flush=True)
    try:
        _write_title_fixes_csv(title_fixes)
        _write_redirect_map_csv(redirect_map)
    except Exception as e:
        print(f"[seo] warning: fix CSV export skipped: {e}", flush=True)
    return title_fixes, redirect_map


# Run the full SEO audit pipeline and write report artifacts.
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("--no-dashboard", action="store_true")
    args = ap.parse_args()

    if not args.no_dashboard:
        server.start_dashboard()
        print(f"[seo] dashboard: http://localhost:{server.PORT}", flush=True)
        time.sleep(1)

    t0 = time.time()
    server.seo_load(args.export_dir)
    res = server.seo_detect()
    title_fixes, redirect_map = _generate_fixes(args.export_dir, server.RUN["issues"])
    server.seo_set_fixes(titles=title_fixes, redirect_map=redirect_map)

    # starter recommendations from the detected issues (the skill writes richer ones)
    issues = sorted(server.RUN["issues"], key=lambda x: {"High":0,"Medium":1,"Low":2}.get(x["severity"],3))
    recs = []
    for i in issues[:5]:
        recs.append(f"Fix the {i['count']} {i['severity']}-severity '{i['type']}' issue(s) first.")
    if not recs:
        recs.append("No issues detected on this crawl.")
    server.seo_recommend(recs)
    server.RUN["model_calls"] = len(title_fixes) + 2
    server.RUN["duration_sec"] = round(time.time() - t0, 1)
    server.seo_report()
    server.seo_export()

    if not args.no_dashboard:
        print(f"\n[seo] Dashboard is live. Keeping process alive for 60s for final snapshot...")
        time.sleep(60)

    s = server.RUN["summary"]
    print("\n=== SEO AUDIT RESULT ===")
    print(f"Site         : {server.RUN['site']}  ({server.RUN['urls']} URLs)")
    print(f"Total issues : {s['total_issues']}  (High {s['by_severity'].get('High',0)} / "
          f"Medium {s['by_severity'].get('Medium',0)} / Low {s['by_severity'].get('Low',0)})")
    print("Wrote outputs/report.json, outputs/report.html, outputs/fixes.csv, and outputs/redirect_map.csv")


if __name__ == "__main__":
    main()
