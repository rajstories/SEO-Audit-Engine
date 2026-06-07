# SEO Command Center

Production-oriented SEO audit runner for Screaming Frog CSV exports. It uses pandas-only detection for crawl issues, optional Ollama calls for title recommendations, and exports client-ready HTML reports with history and competitor comparisons.

## Requirements

```bash
pip install pandas
```

PDF export uses WeasyPrint:

```bash
pip install weasyprint
```

WeasyPrint also needs its native system libraries. If those are missing, `--pdf` will warn and the audit will still complete with HTML and JSON outputs.

## Usage

Run commands from this folder or from any other directory. Output paths are absolute inside `seo-command-center/outputs`.

### Basic audit

```bash
python3 run.py export/ --site-name "Client Site"
```

Writes:

- `outputs/report.json`
- `outputs/report.html`
- `outputs/fixes.csv`
- `outputs/redirect_map.csv`
- `history/clientsite_YYYY-MM-DD.json`

### Competitor comparison

```bash
python3 run.py client-export/ competitor-export/ --site-name "Client Site"
```

Adds a **Competitive Gap** section showing issues the client has that the competitor does not, plus areas where the competitor has fewer affected URLs.

### PDF report

```bash
python3 run.py export/ --site-name "Client Site" --pdf
```

Writes `outputs/report.pdf` when WeasyPrint and its native dependencies are available.

### Offline mode

```bash
python3 run.py export/ --site-name "Client Site" --no-ollama
```

Skips Ollama entirely and uses deterministic fallback title suggestions from URL slug, H1, and site name.

## What the Audit Checks

- Missing, duplicate, too-long, and too-short titles
- Missing and duplicate meta descriptions
- Broken links and server errors
- Redirects and redirect chains
- Missing and duplicate H1s
- Orphan pages
- Non-indexable 200 URLs that still receive internal links
- Thin content
- Slow pages over 3 seconds

Image alt detection is intentionally excluded because Screaming Frog CSV rows made it too noisy for reliable client reporting.

## Scoring

The report includes an explicit scoring breakdown:

- High severity issue types deduct 10 points each
- Medium severity issue types deduct 5 points each
- Low severity issue types deduct 2 points each

Each deduction includes the affected URL count and a business reason so the score is easy to defend in client conversations.

## Notes

- Detection stays pure pandas. CSV data is never sent to an LLM.
- Ollama is used only for title generation and has a 30 second timeout.
- Missing or slow Ollama never stops the audit.
- `--site-name` is used in title recommendations and report branding.
