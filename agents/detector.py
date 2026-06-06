import pandas as pd


# List the detector checks in the order they should stream to the dashboard.
DETECTOR_CHECKS = [
    'missing_title',
    'duplicate_title',
    'broken_link',
    'server_error',
    'redirect_chain',
    'title_too_long',
    'missing_meta_description',
    'duplicate_meta_description',
    'missing_h1',
    'redirect',
    'orphan_page',
    'non_indexable_but_linked',
    'title_too_short',
    'meta_description_too_long',
    'duplicate_h1',
    'thin_content',
    'slow_page',
    'missing_image_alt',
]


# Load a Screaming Frog export into a dataframe.
def load_export(csv_path):
    """Load Screaming Frog CSV and return cleaned dataframe."""
    df = pd.read_csv(csv_path, encoding='utf-8', low_memory=False)
    return df


# Return indexable 200 HTML rows for page-level checks.
def get_indexable_html(df):
    """Filter to indexable HTML pages only — base for most checks."""
    return df[
        (_str(df, 'Indexability') == 'Indexable') &
        (_num(df, 'Status Code') == 200) &
        (_str(df, 'Content Type').str.contains('text/html', case=False, na=False))
    ]


# Run all deterministic detector checks and optionally stream progress.
def detect_all(df, progress=None):
    """Run every deterministic rulebook detector. Returns list of issue dicts."""
    df = df.rename(columns=lambda x: x.strip())

    required_cols = {
        'Content Type', 'Status Code', 'Indexability', 'Title 1',
        'Meta Description 1', 'H1-1', 'Title 1 Pixel Width',
        'Title 1 Length', 'Redirect URL', 'Address', 'Inlinks',
        'Meta Description 1 Length', 'Word Count', 'Response Time'
    }
    missing = required_cols - set(df.columns)
    if missing:
        print(f"Error: Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        return []

    html = df[_str(df, 'Content Type').str.contains('text/html', case=False, na=False)]

    html_200 = html[_num(html, 'Status Code') == 200]
    idx = get_indexable_html(df)
    issues = []

    title = _str(idx, 'Title 1').str.strip()
    meta = _str(idx, 'Meta Description 1').str.strip()
    h1 = _str(idx, 'H1-1').str.strip()

    # HIGH severity
    _run_check(issues, progress, 'missing_title', 'High', idx[title == ''])

    _run_check(issues, progress, 'duplicate_title', 'High',
               idx[(title != '') & title.duplicated(keep=False)])

    _run_check(issues, progress, 'broken_link', 'High',
               df[_num(df, 'Status Code').between(400, 499)])

    _run_check(issues, progress, 'server_error', 'High',
               df[_num(df, 'Status Code').between(500, 599)])

    redirects = df[_num(df, 'Status Code').between(300, 399)]
    redirect_set = set(_str(redirects, 'Address').replace('', pd.NA).dropna())
    _run_check(issues, progress, 'redirect_chain', 'High',
               redirects[_str(redirects, 'Redirect URL').isin(redirect_set)])

    # MEDIUM severity
    _run_check(issues, progress, 'title_too_long', 'Medium',
               idx[(_num(idx, 'Title 1 Pixel Width') > 561) |
                   (_num(idx, 'Title 1 Length') > 60)])

    _run_check(issues, progress, 'missing_meta_description', 'Medium', idx[meta == ''])

    _run_check(issues, progress, 'duplicate_meta_description', 'Medium',
               idx[(meta != '') & meta.duplicated(keep=False)])

    h1_200 = _str(html_200, 'H1-1').str.strip()
    _run_check(issues, progress, 'missing_h1', 'Medium', html_200[h1_200 == ''])

    _run_check(issues, progress, 'redirect', 'Medium', redirects)

    _run_check(issues, progress, 'orphan_page', 'Medium',
               idx[_num(idx, 'Inlinks') == 0])

    _run_check(issues, progress, 'non_indexable_but_linked', 'Medium',
               df[(_str(df, 'Indexability') == 'Non-Indexable') &
                  (_num(df, 'Inlinks') > 0)])

    # LOW severity
    _run_check(issues, progress, 'title_too_short', 'Low',
               idx[(title != '') & (_num(idx, 'Title 1 Length') < 30)])

    _run_check(issues, progress, 'meta_description_too_long', 'Low',
               idx[_num(idx, 'Meta Description 1 Length') > 155])

    _run_check(issues, progress, 'duplicate_h1', 'Low',
               idx[(h1 != '') & h1.duplicated(keep=False)])

    _run_check(issues, progress, 'thin_content', 'Low',
               idx[_num(idx, 'Word Count') < 200])

    _run_check(issues, progress, 'slow_page', 'Low',
               df[_num(df, 'Response Time') > 1.0])

    _run_check(issues, progress, 'missing_image_alt', 'Medium',
               df[(_str(df, 'Content Type').str.contains('image', case=False, na=False)) &
                  (_str(df, 'Alt Text') == '')])

    return issues


# Return a string series for a column, defaulting safely when it is missing.
def _str(df, column):
    col = column.strip()
    if col not in df:
        return pd.Series('', index=df.index, dtype='string')
    return df[col].fillna('').astype(str)


# Return a numeric series for a column, defaulting safely when it is missing.
def _num(df, column):
    col = column.strip()
    if col not in df:
        return pd.Series(0, index=df.index, dtype='float64')
    return pd.to_numeric(df[col], errors='coerce').fillna(0)


# Add one detector issue and stream its completed count.
def _run_check(issues, progress, issue_type, severity, df_subset):
    count = _add(issues, issue_type, severity, df_subset)
    if progress:
        try:
            progress({"stage": "detecting", "check": issue_type, "found": count})
        except Exception:
            pass
    return count


# Add an issue dictionary from a filtered dataframe.
def _add(issues, issue_type, severity, df_subset):
    """Helper to build issue dict from a filtered dataframe."""
    urls = _str(df_subset, 'Address').replace('', pd.NA).dropna().tolist()
    if urls:
        issues.append({
            "type": issue_type,
            "severity": severity,
            "affected_urls": urls,
            "count": len(urls),
            "explanation": f"{len(urls)} URLs affected by {issue_type.replace('_', ' ')}."
        })
    return len(urls)
