## 10:15 - Used pandas for all detection instead of feeding CSV to LLM
50k rows would cause memory overflow on local 9B model. Pandas ensures
100% deterministic F1 accuracy with zero hallucination risk.

## 11:30 - Implemented self-healing validation loop for title generation
qwen3.5 was generating 65+ char titles. Added 3-retry loop with pixel
width check (len*6 <= 561). Falls back to truncation after 3 failures.

## 12:15 - outputs/ was in .gitignore, force-added with git add -f
Discovered outputs folder was being ignored. Used git add -f to force
include report.json, report.html, fixes.csv, redirect_map.csv.

## 13:00 - audit.jsonl hooks were failing due to wrong settings.json schema
hooks missing "type" field. Fixed schema, relaunched Claude Code, 
verified audit.jsonl writing correctly with wc -l showing 10+ lines.


## 11:45 - Switched from URL-fetching script to CSV-based plugin

Old ForgeSprint code fetched live URLs. Brief requires offline Screaming Frog
CSV processing. Starter bundle used as base — saves MCP server/dashboard setup time.

## 12:33 - Outputs were gitignored, force-added with git add -f

## 10:15 - Used pandas for all detection instead of feeding CSV to LLM
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
verified audit.jsonl writing correctly with wc -l showing 10+ lines.
