import json
import re
import subprocess
from difflib import get_close_matches
from urllib.parse import urlparse

import pandas as pd


# Validate a generated title using the hackathon pixel-width estimate.
def _is_valid_title(title):
    title = (title or "").strip()
    pixel_width = len(title) * 6
    return pixel_width <= 561 and len(title) > 10


# Build a readable fallback title from a URL without using the LLM.
def _fallback_title(url):
    parsed = urlparse(str(url))
    path = parsed.path.strip("/")
    source = path.split("/")[-1] or parsed.netloc or "SEO Page"
    words = re.sub(r"[-_]+", " ", source).strip()
    words = re.sub(r"\s+", " ", words)
    title = words.title() if words else "SEO Page"
    return title if len(title) > 10 else f"{title} Overview"


# Ask Ollama for one title using only a URL string as model input.
def _ollama_title(prompt, model):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip().strip('"').strip("'")


# Ask Ollama for a batch response using only URL strings as model input.
def _ollama_text(prompt, model):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# Generate and validate one SEO title with up to three self-healing retries.
def generate_valid_title(url, model="qwen3.5:9b", max_retries=3):
    last_title = _fallback_title(url)
    for attempt in range(1, max_retries + 1):
        prompt = (
            "Write one concise SEO title for this URL. "
            "Return only the title text, no markdown, no explanation. "
            "The title must be more than 10 characters and fit within 561 pixels. "
            f"URL: {url}"
        )
        title = _ollama_title(prompt, model) or last_title
        last_title = title.strip()
        if _is_valid_title(last_title):
            return last_title
        print(f"Validation Failed (attempt {attempt}): was {len(last_title)} chars. Re-prompting...")
    return last_title[:57].rstrip() + "..."


# Generate SEO titles in small Ollama batches and fall back to one-by-one repair.
def generate_titles_batch(urls, model="qwen3.5:9b", batch_size=5):
    # Fallback sequence to ensure we have URLs to fix even if missing_title is empty
    targets = []

    # This function is now called with a list of candidate URLs from various issue types
    # in order of priority. We just need to ensure we process the input list.
    clean_urls = [str(url) for url in urls if str(url).strip()]

    # If for some reason the caller passed an empty list, we can't do much,
    # but the logic in run.py should handle the prioritization.
    # However, if we want to ensure at least 5 fixes, we'd need the full DF here.
    # Given the current architecture, we'll focus on processing the provided urls.

    fixes = []
    for start in range(0, len(clean_urls), batch_size):
        batch = clean_urls[start:start + batch_size]
        n = len(batch)
        prompt = (
            "Write concise SEO titles for these URLs.\n"
            f"Return ONLY a valid JSON array of exactly {n} strings. No markdown, no explanation.\n"
            "Each title must be more than 10 characters and fit within 561 pixels.\n"
            f"URLs: {json.dumps(batch)}"
        )
        try:
            parsed = json.loads(_ollama_text(prompt, model))
            if not isinstance(parsed, list) or len(parsed) != n:
                raise ValueError("Ollama returned the wrong number of titles.")
            titles = [str(title).strip() for title in parsed]
            if not all(_is_valid_title(title) for title in titles):
                raise ValueError("Ollama returned one or more invalid titles.")
        except Exception:
            titles = [generate_valid_title(url, model=model) for url in batch]
        fixes.extend([
            {"url": url, "old": "", "new": title}
            for url, title in zip(batch, titles)
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
