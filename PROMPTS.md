# Key Prompts Log

## 1. The Deterministic Detector (Pandas over LLM)
**Prompt Summary:** "Build `agents/detector.py` with the 18 SEO rulebook detectors using pure pandas. DO NOT feed the CSV to the LLM to avoid token overflow. Add plain English comments above every function."
**Purpose:** To achieve 100% deterministic F1 accuracy for the auto-grader without crashing the local model's memory.
**Iteration:** Worked on the first try. This was a crucial architectural decision that saved hours of debugging LLM hallucinations and memory issues.

## 2. Self-Healing Fixer & Micro-Batching
**Prompt Summary:** "Update `fixer.py` with a self-healing validation loop for titles (check pixel width via `len*6 <= 561`, allow 3 retries, fallback to 57 chars + '...'). Also implement micro-batching to send 5 URLs per LLM call, returning a strict JSON array."
**Purpose:** To generate fixes 5x faster (efficiency points) and guarantee outputs strictly adhere to the 561px rulebook limit.
**Iteration:** Required iteration. The first attempt failed because the local model returned markdown code blocks instead of raw JSON arrays. Had to refine the prompt to strictly enforce JSON output and wrap the parser in a try/except block with a single-URL fallback.

## 3. The Pure Python Redirect Map
**Prompt Summary:** "Add a redirect map generator in `fixer.py` using `difflib.get_close_matches` to map 404 broken links to the closest live page. Cap it at 30 links. Pure Python, no LLM."
**Purpose:** To hit the Champion tier requirement for a redirect map without wasting LLM compute or runtime.
**Iteration:** Worked perfectly first try. Proved that algorithmic string matching is far superior and faster than LLM guessing for exact URL routing.

## 4. End-to-End CLI Execution & Audit Logging
**Prompt Summary:** (Run via Claude Code CLI using gemma4:31b-cloud) "Run python3 run.py ../sample-export --no-dashboard and explain the logic inside detector.py."
**Purpose:** To run the final end-to-end pipeline test, populate .claude/audit.jsonl via system hooks, and prep for the 30-second judge code-reading demo.
**Iteration:** Took a couple of tries. audit.jsonl wasn't writing because settings.json hook schema was invalid (missing "type" field). Fixed schema, re-launched, logs captured correctly.
