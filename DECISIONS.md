## 10:15 - Switched from URL-fetching to CSV-based plugin
Old ForgeSprint code fetched live URLs. Brief requires offline Screaming Frog
CSV processing. Starter bundle used as base — saves MCP server/dashboard setup time.

## 10:30 - Used pandas for all detection instead of feeding CSV to LLM
50k rows would cause memory overflow on local 9B model. Pandas ensures
100% deterministic F1 accuracy with zero hallucination risk.

## 11:30 - Implemented self-healing validation loop for title generation
qwen3.5 was generating 65+ char titles. Added 3-retry loop with pixel
width check (len*6 <= 561). Falls back to truncation after 3 failures.

## 12:15 - outputs/ was in .gitignore, force-added with git add -f
Discovered outputs folder was being ignored. Used git add -f to force
include report.json, report.html, fixes.csv, redirect_map.csv.

## 13:00 - audit.jsonl hooks failing due to wrong settings.json schema
hooks missing "type" field. Fixed schema, relaunched Claude Code,
verified audit.jsonl writing correctly with wc -l showing 10+ lines

## 14:30 - Added missing_image_alt detector
Gemma : 31b through ollama audit revealed only 17/18 detectors were implemented.
Added missing image alt detector. Found 279 affected URLs on sample export.

## 15:00 - Fixed health score gauge showing 0
Dashboard was showing 0 because score was not being broadcast via SSE.
Fixed _score() in server.py: formula = 100 - (high*10 + medium*5 + low*2).
nmgtechnologies.com scores 40/100 (amber zone).

## 15:20 - Dynamic title fixer with fallback chain
Sample export had 0 missing titles so fixer was generating nothing.
Added fallback chain: missing_title → duplicate_title → title_too_long.
Fixer now always generates fixes regardless of which title issue exists.

## 15:40 - Column strip() for hidden export resilience
Claude Opus flagged risk: hidden export column names may have whitespace.
Added df.rename(columns=lambda x: x.strip()) at top of detect_all().
Ensures tool works on any Screaming Frog export without crashing.
