<div align="center">

<img src="https://capsule-render.vercel.app/api?type=venom&height=220&text=SEO%20Command%20Center&fontSize=62&color=0:020617,50:052e16,100:020617&fontColor=f0fdf4&stroke=22c55e&strokeWidth=3&animation=fadeIn&fontAlignY=50&desc=Autonomous%20Audit%20Engine%20%E2%80%A2%20Local%20AI%20%E2%80%A2%20Zero%20Cloud%20Dependencies&descSize=17&descAlignY=72&descFontColor=4ade80" width="100%"/>

<br/>

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![pandas](https://img.shields.io/badge/pandas-Detection%20Engine-150458?style=flat-square&logo=pandas&logoColor=white)](https://pandas.pydata.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-000000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.ai)
[![Offline](https://img.shields.io/badge/Runs-100%25%20Offline-22c55e?style=flat-square)](.)
[![Speed](https://img.shields.io/badge/Audit%20Speed-Under%2060s-f59e0b?style=flat-square)](.)
[![Rules](https://img.shields.io/badge/SEO%20Rules-17%20Detectors-8b5cf6?style=flat-square)](.)

<br/>

[**Live Demo**](#-live-audit-nmgtechnologiescom) · [**How It Works**](#-how-it-works) · [**Architecture**](#-architecture) · [**Quick Start**](#-quick-start) · [**Lessons Learned**](#-engineering-lessons)

<br/>

</div>

## ✦ What This Is

> **The Problem:** SEO audits are slow, manual, and expensive. Agencies charge thousands for what is essentially a repeatable checklist applied to crawl data.

SEO Command Center **automates the entire process** end-to-end. Drop in a Screaming Frog CSV export of any website, and the engine:

- 🔍 Runs **17 deterministic SEO checks** via pure pandas — zero hallucination risk
- ⚖️ **Prioritizes every issue** by business impact (HIGH / MEDIUM / LOW)
- 🤖 Uses a **local AI model** to rewrite broken and over-length titles
- 🗺️ **Maps 404 pages** to the nearest live URL via string similarity
- 📄 Generates a **client-ready HTML report** — all in under 60 seconds, fully offline

No cloud. No API keys. No per-crawl fees. Just fast, accurate, repeatable audits.

---

## 🔬 Live Audit: nmgtechnologies.com

*Validated on a real production digital marketing agency website.*

```
Site:         nmgtechnologies.com
URLs crawled: 456
Health Score: 40 / 100  ⚠️ Needs Work
```

| Severity | Issue | URLs Affected |
|:--------:|-------|:-------------:|
| 🔴 **HIGH** | Duplicate Title | 12 |
| 🔴 **HIGH** | Broken Link (4xx) | 6 |
| 🟡 **MEDIUM** | Title Too Long | 63 |
| 🟡 **MEDIUM** | Duplicate Meta Description | 16 |
| 🟡 **MEDIUM** | Non-Indexable But Linked | 10 |
| 🟡 **MEDIUM** | Redirect (3xx) | 7 |
| 🟡 **MEDIUM** | Missing H1 | 2 |
| ⚪ **LOW** | Meta Too Long | 42 |
| ⚪ **LOW** | Slow Page | 152 |
| ⚪ **LOW** | Duplicate H1 | 19 |
| ⚪ **LOW** | Title Too Short | 21 |
| ⚪ **LOW** | Thin Content | 10 |

**Fixes auto-generated:**
```
✅  6 redirect mappings    →  404 broken URLs mapped to nearest live URLs
✅  75 title rewrites      →  AI-generated, pixel-width validated, retry-looped
```

---

## ⚡ How It Works

```
INPUT: Screaming Frog CSV Export
           │
           ▼
  ┌─────────────────┐
  │  Stage 1: INGEST │  Load + normalize columns · report URL count
  └────────┬────────┘
           │
           ▼
  ┌──────────────────┐
  │  Stage 2: DETECT  │  17 deterministic pandas rules · zero AI involvement
  └────────┬─────────┘
           │
           ▼
  ┌────────────────────────┐
  │  Stage 3: PRIORITIZE   │  Score every issue HIGH / MEDIUM / LOW
  └────────┬───────────────┘
           │
           ▼
  ┌────────────────┐
  │  Stage 4: FIX  │  AI rewrites bad titles + difflib maps 404 redirects
  └────────┬───────┘
           │
           ▼
  ┌──────────────────┐
  │  Stage 5: DELIVER │  Dashboard + report.json + report.html + CSVs
  └──────────────────┘
```

> **Core Design Principle:** The LLM is called **exactly twice** in the entire pipeline — once for title generation, once for redirect suggestions. Everything else is deterministic Python. This means the pipeline runs in under 60 seconds, never hits token limits, and produces consistent results on any site.

---

## 🛡️ 17 SEO Detectors

<details>
<summary><b>🔴 HIGH Severity — Business-Critical Issues</b></summary>

| Rule | Detection Logic |
|------|----------------|
| Missing Title | `Title 1` empty on indexable 200 page |
| Duplicate Title | Same `Title 1` on 2+ indexable URLs |
| Broken Link (4xx) | `Status Code` 400–499 |
| Server Error (5xx) | `Status Code` 500–599 |
| Redirect Chain | 3xx URL that redirects to another 3xx |

</details>

<details>
<summary><b>🟡 MEDIUM Severity — Ranking Impact Issues</b></summary>

| Rule | Detection Logic |
|------|----------------|
| Title Too Long | `Pixel Width` > 561px |
| Missing Meta Description | `Meta Description 1` empty |
| Duplicate Meta Description | Same meta on 2+ pages |
| Missing H1 | `H1-1` empty on 200 page |
| Redirect (3xx) | `Status Code` 300–399 |
| Orphan Page | `Inlinks = 0` on indexable page |
| Non-Indexable But Linked | Non-Indexable with `Inlinks > 0` |

</details>

<details>
<summary><b>⚪ LOW Severity — Quality Improvements</b></summary>

| Rule | Detection Logic |
|------|----------------|
| Title Too Short | `Title 1 Length` < 30 chars |
| Meta Description Too Long | `Meta Length` > 155 chars |
| Duplicate H1 | Same H1 on multiple pages |
| Thin Content | `Word Count` < 200 |
| Slow Page | `Response Time` > 3.0 seconds |

</details>

---

## 🏗️ Architecture

```
seo-command-center/
│
├── 📄  run.py                  ← Coordinator: orchestrates all agents
├── 📋  SKILL.md                ← Claude Code orchestration instructions
│
├── 🤖  agents/
│   ├── detector.py             ← 17 pure-pandas SEO detectors
│   └── fixer.py                ← AI title rewriter + redirect map
│
├── 🔌  mcp/
│   └── server.py               ← MCP server: SSE streaming + live dashboard
│
├── 🖥️  dashboard/
│   ├── index.html              ← Live cockpit (Tailwind CSS)
│   └── app.js                  ← Real-time SSE updates
│
├── 📦  outputs/
│   ├── report.json             ← Machine-readable results
│   ├── report.html             ← Client-ready HTML report
│   ├── fixes.csv               ← AI-generated title rewrites
│   └── redirect_map.csv        ← 404 → live URL mappings
│
└── 📈  history/                ← Trend tracking: one JSON per audit run
```

---

## 🧠 Key Engineering Features

### 1 · Self-Healing Title Validation Loop

Local AI models frequently generate over-length titles. This loop measures pixel width, rejects invalid output, and forces a re-prompt up to 3 times before falling back to graceful truncation.

```python
def generate_valid_title(url, max_retries=3):
    for attempt in range(max_retries):
        title = ask_ollama(f"Write SEO title for {url}. Under 60 chars.")
        pixel_width = len(title) * 6  # estimate: 6px per char
        if pixel_width <= 561 and len(title) > 10:
            return title  # ✅ valid — ship it
        # model gave a bad title — force re-prompt
    return title[:57] + "..."  # last resort truncation
```

### 2 · Micro-Batching for 5× Speed

```python
# Send 5 URLs per prompt instead of 1-at-a-time
# Falls back to one-by-one if JSON parsing fails
prompt = "Write SEO titles for these 5 URLs. Return ONLY a JSON array."
```

### 3 · Pure-Python Redirect Mapping (No LLM)

```python
from difflib import get_close_matches

matches = get_close_matches(broken_url, live_urls, n=1, cutoff=0.4)
# /old-about-page  →  /about-us   (matched by string similarity)
```

### 4 · Column Resilience

```python
df = df.rename(columns=lambda x: x.strip())
# Handles Screaming Frog exports where column names carry whitespace
```

### 5 · Graceful Offline Mode

```bash
python3 run.py sample-export/ --no-ollama
# Full detection + report without any AI model
# Title fixes fall back to URL-slug: /about-us → "About Us | Site"
```

---

## 💡 Engineering Lessons

Three real mistakes from v1, and how they were fixed.

---

**Mistake 1 — Coverage Over Precision**

> v1 had 18 detectors. One of them — `missing_image_alt` — fired **279 times** on data that wasn't a real problem. This single false detector contaminated the entire report's credibility.

**Fix:** Removed it. Raised the `slow_page` threshold from `>1.0s` to `>3.0s` after calibrating against real data. 17 accurate detectors beats 18 where one is broken.

**Lesson:** *In data pipelines, one bad signal contaminates everything downstream. Measure precision before shipping.*

---

**Mistake 2 — LLM in the Critical Path**

> v1 blocked report generation until the AI title fixer completed. On large exports with retries, this meant 10+ minutes of silence. The report never appeared.

**Fix:** Decoupled the pipeline. Report writes first. AI fixer runs after as an optional enhancement. The pipeline never blocks on AI availability.

**Lesson:** *AI calls should be optional enhancements, never blocking dependencies.*

---

**Mistake 3 — Relative Output Paths**

> Early version wrote to `outputs/` relative to the current working directory. Running from a different folder broke everything — silently.

**Fix:**
```python
OUTPUT_DIR = Path(__file__).parent / "outputs"
```

**Lesson:** *Always anchor paths to `__file__`, never to the working directory.*

---

## 🚀 Quick Start

### Install

```bash
git clone https://github.com/yourusername/seo-command-center
cd seo-command-center
pip install -r requirements.txt

# Optional: Ollama for AI-powered title rewrites
brew install ollama && ollama pull qwen3.5:9b
```

### Run a Basic Audit

```bash
python3 run.py path/to/screaming-frog-export/
```

### Run with Live Dashboard

```bash
# Terminal 1 — start the dashboard server
python3 mcp/server.py

# Terminal 2 — run the audit
python3 run.py path/to/export/

# Open http://localhost:7700 to watch in real-time
```

### Compare Two Sites

```bash
python3 run.py client-export/ competitor-export/
```

### Fully Offline (No AI Model)

```bash
python3 run.py path/to/export/ --no-ollama
```

---

## 📤 Outputs

Every audit run produces five files automatically:

| File | Description |
|------|-------------|
| `outputs/report.json` | Machine-readable results, schema-validated |
| `outputs/report.html` | Client-ready HTML report with priority recommendations |
| `outputs/fixes.csv` | Before/after title rewrites with pixel-width validation |
| `outputs/redirect_map.csv` | 404 → nearest live URL mappings |
| `history/*.json` | Timestamped audit history for trend tracking |

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Detection** | Python + pandas | Fast, deterministic, zero hallucination risk |
| **AI Fixes** | Ollama (`qwen3.5:9b` / `gemma4:31b`) | Runs locally, no API costs |
| **Dashboard** | SSE Streaming + Tailwind CSS | Real-time visibility as the audit runs |
| **PDF Export** | WeasyPrint | Pixel-perfect client reports |
| **Redirect Map** | `difflib` string similarity | More reliable than asking an LLM to guess |
| **Reports** | JSON + HTML + CSV | Consumable by humans and machines |

---

## 📊 vs. The Alternatives

| | **SEO Command Center** | Agency Audit | SaaS Tools |
|--|:---:|:---:|:---:|
| Cost | Free | $2,000–5,000 | $100–500/mo |
| Time | < 60s | 5–10 days | Hours |
| Offline | ✅ | ❌ | ❌ |
| Customizable | ✅ | ❌ | Limited |
| AI Title Fixes | ✅ | Manual | ❌ |
| 404 Redirect Map | ✅ | Manual | ❌ |
| Exportable Reports | ✅ | PDF only | Limited |

---

<div align="center">

---

**SEO Command Center** · Built by Raj · 2026

*Built to prove that the right architecture beats brute-forcing everything through an LLM.*

</div>
