import json
import re
import subprocess
from difflib import get_close_matches
from urllib.parse import urlparse

import pandas as pd


# Keep common SEO and software acronyms readable after title-casing fallback text.
ACRONYM_FIXES = {
    "Ai": "AI",
    "Api": "API",
    "Crm": "CRM",
    "Erp": "ERP",
    "It": "IT",
    "Saas": "SaaS",
    "Seo": "SEO",
    "Ui": "UI",
    "Ux": "UX",
}


# Validate a generated title using the hackathon pixel-width estimate.
def _is_valid_title(title):
    title = (title or "").strip()
    pixel_width = len(title) * 6
    return pixel_width <= 561 and 10 < len(title) <= 60


# Trim a title to the search-result length limit without leaving messy punctuation.
def _trim_title(title, max_chars=60):
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    title = title.strip("\"'“”‘’").rstrip(".")
    if len(title) <= max_chars:
        return title
    return title[:max_chars].rsplit(" ", 1)[0].rstrip(" -|:") or title[:max_chars].rstrip()


# Restore common acronyms after fallback title casing.
def _restore_acronyms(title):
    words = str(title or "").split(" ")
    return " ".join(ACRONYM_FIXES.get(word, word) for word in words)


# Build a readable fallback title from page context without using the LLM.
def _fallback_title(url, site_name="", h1=""):
    parsed = urlparse(str(url))
    path = parsed.path.strip("/")
    source = path.split("/")[-1] or parsed.netloc or "SEO Page"
    h1_text = str(h1 or "").strip()
    words = h1_text or re.sub(r"[-_]+", " ", source).strip()
    words = re.sub(r"\s+", " ", words)
    title = words if h1_text else words.title()
    if h1_text and h1_text.isupper():
        title = words.title()
    title = _restore_acronyms(title)
    if len(title) <= 10:
        title = f"{title} Overview"
    site = str(site_name or parsed.netloc or "").strip()
    if site:
        with_site = f"{title} | {site}"
        if len(with_site) <= 60:
            return with_site
    return _trim_title(title)


# Ask Ollama for one title using bounded subprocess execution.
def _ollama_title(prompt, model):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip().strip('"').strip("'")


# Ask Ollama for a batch response using bounded subprocess execution.
def _ollama_text(prompt, model):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# Normalize either a URL string or a dict into one page context object.
def _page_context(page, site_name=""):
    if isinstance(page, dict):
        url = str(page.get("url") or page.get("Address") or "").strip()
        return {
            "url": url,
            "old": str(page.get("old") or page.get("old_title") or page.get("Title 1") or "").strip(),
            "h1": str(page.get("h1") or page.get("H1-1") or "").strip(),
            "site": str(page.get("site") or page.get("site_name") or site_name or "").strip(),
        }
    return {"url": str(page).strip(), "old": "", "h1": "", "site": str(site_name or "").strip()}


# Generate and validate one SEO title with offline fallback and optional Ollama retries.
def generate_valid_title(page, model="qwen3.5:9b", max_retries=3, site_name="", use_ollama=True):
    ctx = _page_context(page, site_name=site_name)
    last_title = _fallback_title(ctx["url"], site_name=ctx["site"], h1=ctx["h1"])
    if not use_ollama:
        return last_title
    for attempt in range(1, max_retries + 1):
        prompt = (
            f"Page H1 is '{ctx['h1'] or 'unknown'}'. Site is '{ctx['site'] or 'unknown'}'. "
            "Write SEO title under 60 chars using H1 as the main keyword. "
            "Return only the title text, no markdown, no explanation. "
            "The title must be more than 10 characters and fit within 561 pixels. "
            f"URL: {ctx['url']}"
        )
        title = _ollama_title(prompt, model) or last_title
        last_title = _trim_title(title.strip())
        if _is_valid_title(last_title):
            return last_title
        print(f"Validation Failed (attempt {attempt}): was {len(last_title)} chars. Re-prompting...")
    return _trim_title(last_title)


# Generate SEO title fixes from page contexts and keep each URL's current title.
def generate_titles_batch(pages, model="qwen3.5:9b", batch_size=5, site_name="", use_ollama=True):
    contexts = [_page_context(page, site_name=site_name) for page in pages]
    contexts = [ctx for ctx in contexts if ctx["url"]]
    fixes = []
    for start in range(0, len(contexts), batch_size):
        batch = contexts[start:start + batch_size]
        n = len(batch)
        batch_prompt_rows = [
            {"url": ctx["url"], "h1": ctx["h1"], "site": ctx["site"]}
            for ctx in batch
        ]
        prompt = (
            "Write concise SEO titles for these pages.\n"
            f"Return ONLY a valid JSON array of exactly {n} strings. No markdown, no explanation.\n"
            "Each title must use the H1 as the main keyword where available, be more than 10 characters, and stay under 60 characters.\n"
            f"Pages: {json.dumps(batch_prompt_rows)}"
        )
        if use_ollama:
            try:
                parsed = json.loads(_ollama_text(prompt, model))
                if not isinstance(parsed, list) or len(parsed) != n:
                    raise ValueError("Ollama returned the wrong number of titles.")
                titles = [_trim_title(title) for title in parsed]
                if not all(_is_valid_title(title) for title in titles):
                    raise ValueError("Ollama returned one or more invalid titles.")
            except Exception:
                titles = [generate_valid_title(ctx, model=model, site_name=site_name, use_ollama=use_ollama) for ctx in batch]
        else:
            titles = [generate_valid_title(ctx, model=model, site_name=site_name, use_ollama=False) for ctx in batch]
        fixes.extend([
            {"url": ctx["url"], "old": ctx["old"], "new": title}
            for ctx, title in zip(batch, titles)
        ])
    return fixes


# Generate a deterministic redirect map from broken URLs to closest live URLs.
def generate_redirect_map(df):
    try:
        status = pd.to_numeric(df.get("Status Code"), errors="coerce").fillna(0)
        addresses = df.get("Address", pd.Series("", index=df.index)).fillna("").astype(str)
        broken_urls = addresses[status.between(400, 499)].replace("", pd.NA).dropna().tolist()[:30]
        live_urls = addresses[status == 200].replace("", pd.NA).dropna().tolist()
    except Exception:
        return []
    if not live_urls:
        return []
    redirect_map = []
    for url in broken_urls:
        try:
            matches = get_close_matches(url, live_urls, n=1, cutoff=0.4)
            target = matches[0] if matches else live_urls[0]
        except Exception:
            target = live_urls[0]
        redirect_map.append({
            "from": url,
            "to": target,
            "reason": "404 mapped to closest live URL",
        })
    return redirect_map
