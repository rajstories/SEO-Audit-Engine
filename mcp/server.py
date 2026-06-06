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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DASH_DIR = os.path.join(ROOT, "dashboard")
OUT_DIR = os.path.join(ROOT, "outputs")
PORT = int(os.environ.get("SEO_PORT", "7700"))
MODEL = os.environ.get("RADAR_MODEL", "qwen3.5:9b")

import sys
sys.path.insert(0, ROOT)
from seo import detector  # noqa: E402

RUN = {"site": None, "urls": 0, "issues": [], "summary": None, "status": "idle",
       "checks": []}
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
def seo_load(export_dir: str) -> dict:
    rows = detector.load_rows(export_dir)
    RUN.update({"rows": rows, "urls": len(rows), "issues": [], "summary": None,
                "site": _guess_site(rows), "status": "running",
                "checks": _initial_checks()})
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

    score = _score(RUN["summary"])
    RUN["health_score"] = score

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
        "issues": RUN["issues"],
        "fixes": RUN.get("fixes", {"titles": [], "redirect_map": []}),
        "recommendations": RUN.get("recommendations", []),
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
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "report.json")
    json.dump(_report_obj(), open(p, "w", encoding="utf-8"), indent=2)
    RUN["status"] = "done"; _emit("saved", {"path": p}); return {"path": p}


# Read report.json and write the client-facing HTML report.
def seo_export() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    report_json = os.path.join(OUT_DIR, "report.json")
    report_obj = _load_report_obj(report_json)
    p = os.path.join(OUT_DIR, "report.html")
    open(p, "w", encoding="utf-8").write(_render_html(report_obj))
    _emit("exported", {"path": p}); return {"path": p}


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


# Return Tailwind classes for a severity badge.
def _badge_classes(severity):
    return {
        "High": "bg-red-100 text-red-700 ring-red-200",
        "Medium": "bg-amber-100 text-amber-800 ring-amber-200",
        "Low": "bg-gray-100 text-gray-700 ring-gray-200",
    }.get(severity, "bg-gray-100 text-gray-700 ring-gray-200")


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


# Render the agency-quality client report with Tailwind CDN.
def _render_html(o) -> str:
    sev = (o["summary"] or {}).get("by_severity", {})
    issues = sorted(o.get("issues", []),
                    key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x.get("severity"), 3),
                                   -int(x.get("count") or 0), x.get("type", "")))
    fixes = o.get("fixes", {}) or {}
    redirects = fixes.get("redirect_map", []) or []
    top_fixes = issues[:3]
    score = _score(o.get("summary", {}))
    audit_date = datetime.now().strftime("%B %d, %Y")
    issue_rows = "".join(
        f"""<tr class="border-b border-slate-100">
          <td class="px-4 py-3"><span class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 {_badge_classes(i.get('severity'))}">{_h(i.get('severity'))}</span></td>
          <td class="px-4 py-3 font-medium text-slate-900">{_h(i.get('type')).replace('_', ' ')}</td>
          <td class="px-4 py-3 text-slate-700">{int(i.get('count') or 0)}</td>
          <td class="px-4 py-3 text-slate-600">{_h(i.get('explanation'))}</td>
        </tr>"""
        for i in issues)
    fix_cards = "".join(
        f"""<div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div class="mb-2 flex items-center justify-between gap-3">
            <h3 class="text-base font-semibold text-slate-950">{_h(i.get('type')).replace('_', ' ')}</h3>
            <span class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 {_badge_classes(i.get('severity'))}">{_h(i.get('severity'))}</span>
          </div>
          <p class="text-sm text-slate-600">{_h(_business_impact(i))}</p>
          <p class="mt-3 text-sm font-medium text-slate-900">{int(i.get('count') or 0)} affected URL(s)</p>
        </div>"""
        for i in top_fixes)
    redirect_rows = "".join(
        f"""<tr class="border-b border-slate-100">
          <td class="max-w-[320px] truncate px-4 py-3 text-slate-700">{_h(r.get('from'))}</td>
          <td class="max-w-[320px] truncate px-4 py-3 text-slate-700">{_h(r.get('to'))}</td>
          <td class="px-4 py-3 text-slate-600">{_h(r.get('reason'))}</td>
        </tr>"""
        for r in redirects)
    redirect_section = ""
    if redirects:
        redirect_section = f"""<section class="mb-8 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
    <div class="border-b border-slate-200 px-5 py-4">
      <h2 class="text-xl font-bold text-slate-950">Redirect Map</h2>
      <p class="mt-1 text-sm text-slate-500">{len(redirects)} recommended redirect(s)</p>
    </div>
    <div class="overflow-x-auto">
      <table class="min-w-full text-left text-sm">
        <thead class="bg-slate-100 text-xs uppercase tracking-wide text-slate-500">
          <tr><th class="px-4 py-3">From</th><th class="px-4 py-3">To</th><th class="px-4 py-3">Reason</th></tr>
        </thead>
        <tbody>{redirect_rows}</tbody>
      </table>
    </div>
  </section>"""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEO Audit — {_h(o.get('site'))}</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-50 text-slate-900">
<main class="mx-auto max-w-6xl px-6 py-8">
  <header class="mb-8 flex flex-col justify-between gap-4 border-b border-slate-200 pb-6 md:flex-row md:items-end">
    <div>
      <p class="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">SEO Command Center</p>
      <h1 class="mt-2 text-3xl font-bold tracking-tight text-slate-950">SEO Audit Report</h1>
      <p class="mt-2 text-slate-600">{_h(o.get('site'))}</p>
    </div>
    <div class="text-sm text-slate-500">Audit date<br><span class="font-semibold text-slate-900">{audit_date}</span></div>
  </header>

  <section class="mb-8 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
    <div class="mb-4">
      <h2 class="text-xl font-bold text-slate-950">Executive Summary</h2>
      <p class="mt-1 text-sm text-slate-500">A concise view of crawl coverage, issue volume, and overall SEO health.</p>
    </div>
    <div class="grid gap-4 md:grid-cols-3">
      <div class="rounded-lg bg-slate-50 p-5">
        <p class="text-sm font-medium text-slate-500">Total URLs</p>
        <p class="mt-2 text-4xl font-bold text-slate-950">{int(o.get('urls_crawled') or 0)}</p>
      </div>
      <div class="rounded-lg bg-slate-50 p-5">
        <p class="text-sm font-medium text-slate-500">Total Issues</p>
        <p class="mt-2 text-4xl font-bold text-slate-950">{int((o.get('summary') or {}).get('total_issues') or 0)}</p>
        <p class="mt-2 text-sm text-slate-500">High {sev.get('High', 0)} · Medium {sev.get('Medium', 0)} · Low {sev.get('Low', 0)}</p>
      </div>
      <div class="rounded-lg bg-slate-50 p-5">
        <p class="text-sm font-medium text-slate-500">SEO Health Score</p>
        <p class="mt-2 text-4xl font-bold text-slate-950">{score}<span class="text-lg text-slate-500">/100</span></p>
      </div>
    </div>
  </section>

  <section class="mb-8">
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-xl font-bold text-slate-950">Top 3 Fixes</h2>
      <p class="text-sm text-slate-500">Prioritized by severity and affected URLs</p>
    </div>
    <div class="grid gap-4 md:grid-cols-3">{fix_cards or '<div class="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-500 shadow-sm">No priority fixes detected.</div>'}</div>
  </section>

  <section class="mb-8 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
    <div class="border-b border-slate-200 px-5 py-4">
      <h2 class="text-xl font-bold text-slate-950">Issues</h2>
    </div>
    <div class="overflow-x-auto">
      <table class="min-w-full text-left text-sm">
        <thead class="bg-slate-100 text-xs uppercase tracking-wide text-slate-500">
          <tr><th class="px-4 py-3">Severity</th><th class="px-4 py-3">Issue</th><th class="px-4 py-3">URLs</th><th class="px-4 py-3">Explanation</th></tr>
        </thead>
        <tbody>{issue_rows or '<tr><td colspan="4" class="px-4 py-6 text-center text-slate-500">No issues detected.</td></tr>'}</tbody>
      </table>
    </div>
  </section>

  {redirect_section}

  <footer class="border-t border-slate-200 pt-5 text-sm text-slate-500">
    Generated by SEO Command Center · Model {_h((o.get('run_meta') or {}).get('model'))}
  </footer>
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
