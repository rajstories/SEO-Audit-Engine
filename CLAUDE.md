# SEO Command Center — Agent Rules

- NEVER read raw CSV into the model. Use pandas for all detection.
- Detection is pure Python. LLM only writes title/meta fixes.
- Always validate LLM title output: if len > 60 chars, re-prompt.
- All outputs go to outputs/ folder.
- After each working step, remind me to commit.
- report.json must match report.schema.json exactly.
- Always validate title length before accepting LLM output
