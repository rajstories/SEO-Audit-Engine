"""
server.py — local MCP server + live dashboard host (one process, two faces).

  1. MCP tools over stdio  -> Claude Code calls: seo_load, seo_detect, seo_report, seo_export
  2. HTTP + SSE on localhost:7700 -> the live cockpit that fills as issues are found.

STARTER: works end to end out of the box. Extend the detectors (seo/detector.py) and
the fixes (the model-driven title rewriting / redirect map) during the Sprint.

Needs the MCP SDK to expose tools to Claude (`pip install mcp`); without it the dashboard
still runs so you can use run.py. Standard library otherwise.
"""
from __future__ import annotations
import html, json, os, queue, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DASH_DIR = ROOT / "dashboard"
OUTPUT_DIR = ROOT / "outputs"
OUT_DIR = OUTPUT_DIR
PORT = int(os.environ.get("SEO_PORT", "7700"))
MODEL = os.environ.get("RADAR_MODEL", "qwen3.5:9b")

import sys
sys.path.insert(0, str(ROOT))
from seo import detector  # noqa: E402

RUN = {"site": None, "urls": 0, "issues": [], "summary": None, "status": "idle",
       "checks": [], "score_breakdown": {"score": 100, "deductions": []}}
_subs: list[queue.Queue] = []
_lock = threading.Lock()


# Send a structured event to all connected dashboard clients.
def _emit(event, data):
    payload = json.dumps({"event": event, "data": data})
    with _lock:
        for q in list(_subs):
            try: q.put_nowait(payload)
            except Exception: pass


# ----- pipeline tools (importable by run.py without MCP) -----
# Load crawl rows and reset the live run state.
def seo_load(export_dir: str, site_name: str | None = None) -> dict:
    rows = detector.load_rows(export_dir)
    RUN.update({"rows": rows, "urls": len(rows), "issues": [], "summary": None,
                "site": site_name or _guess_site(rows), "status": "running",
                "checks": _initial_checks(), "score_breakdown": {"score": 100, "deductions": []},
                "competitive_gap": None, "previous_audit": None})
    _emit("loaded", {"site": RUN["site"], "urls": len(rows)})
    _emit("checks", {"checks": RUN["checks"]})
    return {"urls": len(rows), "site": RUN["site"]}


# Guess the audited site name from the first crawl URL.
def _guess_site(rows):
    if not rows: return "unknown"
    addr = rows[0].get("Address", "")
    try:
        from urllib.parse import urlparse
        return urlparse(addr).netloc or "unknown"
    except Exception:
        return "unknown"


# Build the initial checklist shown by the live dashboard.
def _initial_checks():
    return [{"check": name, "found": 0, "done": False}
            for name in getattr(detector, "DETECTOR_CHECKS", [])]


# Mark one detector check as complete and broadcast the progress event.
def _on_detector_progress(data):
    check = data.get("check")
    found = int(data.get("found") or 0)
    for row in RUN.get("checks", []):
        if row.get("check") == check:
            row.update({"found": found, "done": True})
            break
    payload = {"stage": "detecting", "check": check, "found": found}
    _emit("progress", payload)


# Run detectors and stream each completed check to the dashboard.
def seo_detect() -> dict:
    if not RUN.get("checks"):
        RUN["checks"] = _initial_checks()
        _emit("checks", {"checks": RUN["checks"]})
    issues = detector.detect(RUN.get("rows", []), progress=_on_detector_progress)
    RUN["issues"] = issues
    RUN["summary"] = detector.summarize(issues)

    breakdown = _score_breakdown(issues)
    score = breakdown["score"]
    RUN["health_score"] = score
    RUN["score_breakdown"] = breakdown

    for i in issues:
        _emit("issue", i)
    _emit("summary", RUN["summary"])
    _emit("score", {"score": score})
    return {"detected": len(issues), "summary": RUN["summary"], "score": score}


# Build the report object that is persisted to report.json.
def _report_obj() -> dict:
    return {
        "site": RUN["site"],
        "urls_crawled": RUN["urls"],
        "summary": RUN["summary"] or {"total_issues": 0, "by_severity": {}},
        "health_score": RUN.get("health_score", 100),
        "score_breakdown": RUN.get("score_breakdown", {"score": 100, "deductions": []}),
        "issues": RUN["issues"],
        "fixes": RUN.get("fixes", {"titles": [], "redirect_map": []}),
        "recommendations": RUN.get("recommendations", []),
        "competitive_gap": RUN.get("competitive_gap"),
        "previous_audit": RUN.get("previous_audit"),
        "run_meta": {"model": MODEL, "model_calls": RUN.get("model_calls", 0),
                     "duration_sec": RUN.get("duration_sec", 0)},
    }


# Attach generated fixes to the live run state.
def seo_set_fixes(titles=None, redirect_map=None) -> dict:
    RUN["fixes"] = {"titles": titles or [], "redirect_map": redirect_map or []}
    _emit("fixes", RUN["fixes"]); return {"titles": len(titles or []), "redirects": len(redirect_map or [])}


# Attach prioritized recommendations to the live run state.
def seo_recommend(recommendations: list) -> dict:
    RUN["recommendations"] = recommendations
    _emit("recommendations", {"recommendations": recommendations}); return {"count": len(recommendations)}


# Write outputs/report.json.
def seo_report() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUTPUT_DIR / "report.json"
    json.dump(_report_obj(), open(p, "w", encoding="utf-8"), indent=2)
    RUN["status"] = "done"; _emit("saved", {"path": str(p)}); return {"path": str(p)}


# Read report.json and write the client-facing HTML report.
def seo_export() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_json = OUTPUT_DIR / "report.json"
    report_obj = _load_report_obj(report_json)
    p = OUTPUT_DIR / "report.html"
    open(p, "w", encoding="utf-8").write(_render_html(report_obj))
    _emit("exported", {"path": str(p)}); return {"path": str(p)}


# Load the persisted report JSON with an in-memory fallback.
def _load_report_obj(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _report_obj()


# Escape a value for safe HTML rendering.
def _h(value):
    return html.escape(str(value or ""))


# Calculate a simple audit score from severity counts.
def _score(summary):
    sev = (summary or {}).get("by_severity", {})
    penalty = sev.get("High", 0) * 10 + sev.get("Medium", 0) * 5 + sev.get("Low", 0) * 2
    return max(0, min(100, 100 - penalty))


# Calculate the score and the exact deductions that explain it.
def _score_breakdown(issues):
    weights = {"High": 10, "Medium": 5, "Low": 2}
    deductions = []
    total_penalty = 0
    for issue in sorted(issues or [], key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x.get("severity"), 3)):
        severity = issue.get("severity")
        points = weights.get(severity, 0)
        if not points:
            continue
        total_penalty += points
        deductions.append({
            "points": points,
            "issue_type": issue.get("type", ""),
            "severity": severity,
            "count": int(issue.get("count") or 0),
            "reason": _score_reason(issue),
        })
    return {"score": max(0, min(100, 100 - total_penalty)), "deductions": deductions}


# Explain why one score deduction matters to the client.
def _score_reason(issue):
    labels = {
        "duplicate_title": "duplicate titles affecting {count} pages reduce SERP clarity and CTR",
        "title_too_long": "titles too long affecting {count} pages may be truncated in search results",
        "missing_title": "missing titles affecting {count} pages leave snippets uncontrolled",
        "broken_link": "broken links affecting {count} URLs waste crawl budget and user trust",
        "server_error": "server errors affecting {count} URLs block users and crawlers",
        "missing_meta_description": "missing meta descriptions affecting {count} pages reduce snippet control",
        "slow_page": "slow pages affecting {count} URLs hurt user experience and conversions",
    }
    count = int(issue.get("count") or 0)
    template = labels.get(issue.get("type"), "{issue} affecting {count} URL(s) needs review")
    return template.format(issue=str(issue.get("type", "")).replace("_", " "), count=count)


# Return Tailwind classes for a severity badge.
def _badge_classes(severity):
    return {
        "High": "bg-red-100 text-red-700 ring-red-200",
        "Medium": "bg-amber-100 text-amber-800 ring-amber-200",
        "Low": "bg-gray-100 text-gray-700 ring-gray-200",
    }.get(severity, "bg-gray-100 text-gray-700 ring-gray-200")


# Return the report color bucket for a health score.
def _score_tone(score):
    if score >= 80:
        return "green"
    if score >= 60:
        return "amber"
    return "red"


# Return a compact CSS class name for severity labels.
def _severity_class(severity):
    return {
        "High": "sev-high",
        "Medium": "sev-medium",
        "Low": "sev-low",
    }.get(severity, "sev-low")


# Estimate traffic risk from high-severity issue volume.
def _estimated_traffic_loss(issues):
    high_urls = sum(int(i.get("count") or 0) for i in issues or [] if i.get("severity") == "High")
    if high_urls <= 0:
        return "No immediate high-severity traffic loss detected."
    low = min(60, max(5, high_urls * 1))
    high = min(80, low + 10)
    return f"{low}-{high}% of organic landing page opportunity may be at risk across {high_urls} high-severity URL(s)."


# Explain the business impact of a detector issue.
def _business_impact(issue):
    impacts = {
        "missing_title": "Missing titles weaken search snippets and reduce click-through from high-intent queries.",
        "duplicate_title": "Duplicate titles blur page intent, making it harder for search engines to rank the right URL.",
        "broken_link": "Broken URLs waste crawl budget, frustrate visitors, and leak conversion opportunities.",
        "server_error": "Server errors block both users and crawlers from important pages.",
        "redirect_chain": "Redirect chains slow down journeys and dilute link equity before users reach the final page.",
        "title_too_long": "Long titles are likely truncated, hiding important value propositions in search results.",
        "missing_meta_description": "Missing descriptions reduce control over search snippets and can lower click-through.",
        "duplicate_meta_description": "Duplicate descriptions make similar pages harder to differentiate in search.",
        "missing_h1": "Missing H1s weaken page structure and make the core topic less clear.",
        "redirect": "Redirects should be reviewed so users and crawlers reach final destinations efficiently.",
        "orphan_page": "Orphan pages are difficult for users and crawlers to discover through internal navigation.",
        "non_indexable_but_linked": "Internal links to non-indexable URLs can send authority toward pages that cannot rank.",
        "title_too_short": "Short titles often miss valuable context and reduce relevance for target searches.",
        "meta_description_too_long": "Long descriptions can be truncated, hiding key calls to action.",
        "duplicate_h1": "Duplicate H1s make multiple pages look interchangeable instead of purpose-built.",
        "thin_content": "Thin pages may struggle to satisfy search intent or convert visitors.",
        "slow_page": "Slow responses hurt user experience and can drag down organic performance.",
    }
    return impacts.get(issue.get("type"), "Fixing this issue improves crawl clarity and visitor experience.")


# Render the agency-quality client report with offline-safe CSS.
def _render_html(o) -> str:
    sev = (o.get("summary") or {}).get("by_severity", {})
    issues = sorted(o.get("issues", []),
                    key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x.get("severity"), 3),
                                   -int(x.get("count") or 0), x.get("type", "")))
    fixes = o.get("fixes", {}) or {}
    redirects = fixes.get("redirect_map", []) or []
    title_fixes = fixes.get("titles", []) or []
    top_fixes = issues[:3]
    score_data = o.get("score_breakdown") or _score_breakdown(issues)
    score = int(o.get("health_score") or score_data.get("score") or 100)
    tone = _score_tone(score)
    audit_date = datetime.now().strftime("%B %d, %Y")
    traffic_loss = _estimated_traffic_loss(issues)
    previous = o.get("previous_audit") or {}
    gap = o.get("competitive_gap") or {}
    style = """
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f6f7f9; color: #172033; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width: 1120px; margin: 0 auto; padding: 32px 24px; }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; border-bottom: 1px solid #d9dee8; padding-bottom: 24px; margin-bottom: 28px; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 34px; line-height: 1.1; letter-spacing: 0; }
    h2 { font-size: 22px; margin-bottom: 12px; }
    h3 { font-size: 16px; margin-bottom: 8px; }
    .eyebrow { color: #657085; font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; margin-bottom: 8px; }
    .muted { color: #657085; }
    .section { background: #fff; border: 1px solid #dfe4ec; border-radius: 8px; padding: 22px; margin-bottom: 22px; box-shadow: 0 1px 2px rgba(20, 31, 48, .04); }
    .summary-grid { display: grid; grid-template-columns: 220px 1fr; gap: 22px; align-items: stretch; }
    .score-circle { width: 178px; height: 178px; border-radius: 999px; display: grid; place-items: center; border: 14px solid; background: #fff; margin: 0 auto; }
    .score-circle strong { display: block; font-size: 44px; line-height: 1; }
    .score-circle span { color: #657085; font-size: 14px; }
    .green { border-color: #16a34a; color: #166534; }
    .amber { border-color: #f59e0b; color: #92400e; }
    .red { border-color: #ef4444; color: #991b1b; }
    .metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }
    .metric { background: #f7f9fc; border: 1px solid #e5e9f1; border-radius: 8px; padding: 14px; }
    .metric b { display: block; font-size: 28px; margin-top: 4px; }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .card { border: 1px solid #dfe4ec; border-radius: 8px; padding: 16px; background: #fff; }
    .badge { display: inline-block; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; margin-bottom: 10px; }
    .sev-high { background: #fee2e2; color: #991b1b; }
    .sev-medium { background: #fef3c7; color: #92400e; }
    .sev-low { background: #eef2f7; color: #475569; }
    .priority-list { padding-left: 20px; margin: 10px 0 0; }
    .priority-list li { margin: 8px 0; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th { text-align: left; background: #eef2f7; color: #475569; text-transform: uppercase; letter-spacing: .06em; font-size: 11px; }
    th, td { border-bottom: 1px solid #e6eaf1; padding: 10px 12px; vertical-align: top; }
    td.url { max-width: 360px; overflow-wrap: anywhere; color: #334155; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .callout { background: #f7f9fc; border: 1px solid #e5e9f1; border-radius: 8px; padding: 14px; }
    footer { color: #657085; border-top: 1px solid #d9dee8; padding-top: 18px; font-size: 13px; }
    @media (max-width: 760px) { main { padding: 20px 14px; } header, .summary-grid, .cards, .metric-grid, .split { display: block; } .score-circle { margin-bottom: 18px; } .card, .metric { margin-bottom: 12px; } }
    @page { margin: 18mm; }
    """
    issue_rows = "".join(
        f"""<tr><td><span class="badge {_severity_class(i.get('severity'))}">{_h(i.get('severity'))}</span></td>
        <td><strong>{_h(i.get('type')).replace('_', ' ')}</strong></td>
        <td>{int(i.get('count') or 0)}</td><td>{_h(i.get('explanation'))}</td></tr>"""
        for i in issues)
    fix_cards = "".join(
        f"""<article class="card"><span class="badge {_severity_class(i.get('severity'))}">{_h(i.get('severity'))}</span>
        <h3>{_h(i.get('type')).replace('_', ' ')}</h3><p class="muted">{_h(_business_impact(i))}</p>
        <p style="margin-top:10px"><strong>{int(i.get('count') or 0)}</strong> affected URL(s)</p></article>"""
        for i in top_fixes)
    priority_items = "".join(f"<li>{_h(rec)}</li>" for rec in (o.get("recommendations") or [])[:3])
    score_rows = "".join(
        f"""<tr><td>-{int(d.get('points') or 0)} pts</td><td>{_h(d.get('severity'))}</td>
        <td>{_h(d.get('issue_type')).replace('_', ' ')}</td><td>{_h(d.get('reason'))}</td></tr>"""
        for d in score_data.get("deductions", []))
    previous_html = ""
    if previous:
        delta = int(previous.get("delta") or 0)
        sign = "+" if delta >= 0 else ""
        previous_html = f"""<div class="callout"><strong>Previous Audit</strong><p class="muted">Last audit: {int(previous.get('previous_score') or 0)}/100 → This audit: {score}/100 ({sign}{delta} points)</p></div>"""
    gap_html = ""
    if gap:
        unique_rows = "".join(
            f"""<tr><td>{_h(i.get('type')).replace('_', ' ')}</td><td>{_h(i.get('severity'))}</td><td>{int(i.get('client_count') or 0)}</td></tr>"""
            for i in gap.get("client_only_issues", []))
        better_rows = "".join(
            f"""<tr><td>{_h(i.get('type')).replace('_', ' ')}</td><td>{int(i.get('client_count') or 0)}</td><td>{int(i.get('competitor_count') or 0)}</td><td>{int(i.get('delta') or 0)}</td></tr>"""
            for i in gap.get("competitor_better_areas", []))
        gap_html = f"""<section class="section"><h2>Competitive Gap</h2>
        <div class="metric-grid"><div class="metric"><span class="muted">Client score</span><b>{int(gap.get('client_score') or score)}</b></div>
        <div class="metric"><span class="muted">Competitor score</span><b>{int(gap.get('competitor_score') or 0)}</b></div>
        <div class="metric"><span class="muted">Score gap</span><b>{int(gap.get('score_gap') or 0)}</b></div></div>
        <div class="split" style="margin-top:16px"><div><h3>Issues client has that competitor does not</h3>
        <table><thead><tr><th>Issue</th><th>Severity</th><th>URLs</th></tr></thead><tbody>{unique_rows or '<tr><td colspan="3">No client-only issues detected.</td></tr>'}</tbody></table></div>
        <div><h3>Areas where competitor scores better</h3>
        <table><thead><tr><th>Issue</th><th>Client</th><th>Competitor</th><th>Gap</th></tr></thead><tbody>{better_rows or '<tr><td colspan="4">No competitor advantage detected.</td></tr>'}</tbody></table></div></div></section>"""
    title_rows = "".join(
        f"""<tr><td class="url">{_h(t.get('url'))}</td><td>{_h(t.get('old'))}</td><td>{_h(t.get('new'))}</td></tr>"""
        for t in title_fixes[:20])
    title_section = f"""<section class="section"><h2>Title Fixes</h2><table><thead><tr><th>URL</th><th>Old title</th><th>Recommended title</th></tr></thead><tbody>{title_rows or '<tr><td colspan="3">No title rewrites generated.</td></tr>'}</tbody></table></section>"""
    redirect_rows = "".join(
        f"""<tr><td class="url">{_h(r.get('from'))}</td><td class="url">{_h(r.get('to'))}</td><td>{_h(r.get('reason'))}</td></tr>"""
        for r in redirects)
    redirect_section = f"""<section class="section"><h2>Redirect Map</h2><table><thead><tr><th>From</th><th>To</th><th>Reason</th></tr></thead><tbody>{redirect_rows or '<tr><td colspan="3">No redirect recommendations generated.</td></tr>'}</tbody></table></section>"""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEO Audit - {_h(o.get('site'))}</title><style>{style}</style></head>
<body><main>
  <header><div><p class="eyebrow">SEO Command Center</p><h1>SEO Audit Report</h1><p class="muted" style="margin-top:8px">{_h(o.get('site'))}</p></div>
  <div class="muted">Audit date<br><strong style="color:#172033">{audit_date}</strong></div></header>

  <section class="section"><h2>Executive Summary</h2>
    <div class="summary-grid"><div class="score-circle {tone}"><div><strong>{score}</strong><span>/100 health score</span></div></div>
    <div><p class="muted">This one-page view highlights the SEO risks most likely to affect traffic, rankings, and client-visible momentum.</p>
      <div class="metric-grid"><div class="metric"><span class="muted">Total URLs</span><b>{int(o.get('urls_crawled') or 0)}</b></div>
      <div class="metric"><span class="muted">Total issues</span><b>{int((o.get('summary') or {}).get('total_issues') or 0)}</b></div>
      <div class="metric"><span class="muted">Severity mix</span><b>{sev.get('High', 0)} / {sev.get('Medium', 0)} / {sev.get('Low', 0)}</b><span class="muted">High / Medium / Low</span></div></div>
      <div class="callout" style="margin-top:14px"><strong>Estimated traffic loss</strong><p class="muted">{_h(traffic_loss)}</p></div>
      {previous_html}</div></div>
  </section>

  <section class="section"><h2>3 Most Critical Issues</h2><div class="cards">{fix_cards or '<article class="card"><p class="muted">No critical issues detected.</p></article>'}</div></section>
  <section class="section"><h2>Fix These 3 Things First</h2><ol class="priority-list">{priority_items or '<li>No priority fixes detected.</li>'}</ol></section>
  {gap_html}
  <section class="section"><h2>Scoring Breakdown</h2><p class="muted" style="margin-bottom:12px">Score: {score}/100</p>
    <table><thead><tr><th>Deduction</th><th>Severity</th><th>Issue</th><th>Reason</th></tr></thead><tbody>{score_rows or '<tr><td colspan="4">No score deductions.</td></tr>'}</tbody></table></section>
  <section class="section"><h2>Issues</h2><table><thead><tr><th>Severity</th><th>Issue</th><th>URLs</th><th>Explanation</th></tr></thead><tbody>{issue_rows or '<tr><td colspan="4">No issues detected.</td></tr>'}</tbody></table></section>
  {title_section}
  {redirect_section}
  <footer>Generated by SEO Command Center · Model {_h((o.get('run_meta') or {}).get('model'))}</footer>
</main></body></html>"""


# ----- dashboard HTTP host -----
class H(BaseHTTPRequestHandler):
    # Suppress noisy request logs in the local dashboard server.
    def log_message(self, *a): pass
    # Send an HTTP response with no-cache headers.
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache"); self.end_headers()
        self.wfile.write(body.encode() if isinstance(body, str) else body)
    # Serve dashboard assets, state snapshots, and the SSE stream.
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            p = os.path.join(DASH_DIR, "index.html")
            self._send(200, open(p, encoding="utf-8").read() if os.path.exists(p) else "no dashboard")
        elif self.path == "/app.js":
            p = os.path.join(DASH_DIR, "app.js")
            self._send(200, open(p, encoding="utf-8").read() if os.path.exists(p) else "", "application/javascript")
        elif self.path == "/state":
            self._send(200, json.dumps({k: v for k, v in RUN.items() if k != "rows"}), "application/json")
        elif self.path == "/events":
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache"); self.end_headers()
            q = queue.Queue()
            with _lock: _subs.append(q)
            try:
                snap = {k: v for k, v in RUN.items() if k != "rows"}
                self.wfile.write(f"data: {json.dumps({'event':'snapshot','data':snap})}\n\n".encode()); self.wfile.flush()
                while True:
                    try: self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                    except queue.Empty: self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception: pass
            finally:
                with _lock:
                    if q in _subs: _subs.remove(q)
        else: self._send(404, "not found")


# Start the local dashboard HTTP server in a background thread.
def start_dashboard(port=PORT):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# Run the MCP stdio server that exposes SEO tools to Claude Code.
def _run_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print(f"[seo] MCP SDK not found. Dashboard only at http://localhost:{PORT}", flush=True)
        while True: time.sleep(3600)
    mcp = FastMCP("seo-command-center")

    @mcp.tool()
    def load(export_dir: str) -> dict:
        """Load a Screaming Frog export directory (expects internal_all.csv)."""
        return seo_load(export_dir)

    @mcp.tool()
    def detect_issues() -> dict:
        """Run the SEO rulebook detectors over the loaded crawl."""
        return seo_detect()

    @mcp.tool()
    def set_fixes(titles: list = None, redirect_map: list = None) -> dict:
        """Attach the model-written title rewrites and the redirect map."""
        return seo_set_fixes(titles, redirect_map)

    @mcp.tool()
    def recommend(recommendations: list) -> dict:
        """Attach the prioritized recommendations."""
        return seo_recommend(recommendations)

    @mcp.tool()
    def write_report() -> dict:
        """Write outputs/report.json."""
        return seo_report()

    @mcp.tool()
    def export_report() -> dict:
        """Write outputs/report.html (the client deliverable)."""
        return seo_export()

    mcp.run()


if __name__ == "__main__":
    start_dashboard()
    print(f"[seo] dashboard live at http://localhost:{PORT}", flush=True)
    _run_mcp()
