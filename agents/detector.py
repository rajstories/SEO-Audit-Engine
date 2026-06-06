import pandas as pd


def load_export(csv_path):
    """Load Screaming Frog CSV and return cleaned dataframe."""
    df = pd.read_csv(csv_path, encoding='utf-8', low_memory=False)
    return df


def get_indexable_html(df):
    """Filter to indexable HTML pages only — base for most checks."""
    return df[
        (_str(df, 'Indexability') == 'Indexable') &
        (_num(df, 'Status Code') == 200) &
        (_str(df, 'Content Type').str.contains('text/html', case=False, na=False))
    ]


def detect_all(df):
    """Run every deterministic rulebook detector. Returns list of issue dicts."""
    html = df[_str(df, 'Content Type').str.contains('text/html', case=False, na=False)]
    html_200 = html[_num(html, 'Status Code') == 200]
    idx = get_indexable_html(df)
    issues = []

    title = _str(idx, 'Title 1').str.strip()
    meta = _str(idx, 'Meta Description 1').str.strip()
    h1 = _str(idx, 'H1-1').str.strip()

    # HIGH severity
    _add(issues, 'missing_title', 'High', idx[title == ''])

    _add(issues, 'duplicate_title', 'High',
         idx[(title != '') & title.duplicated(keep=False)])

    _add(issues, 'broken_link', 'High',
         df[_num(df, 'Status Code').between(400, 499)])

    _add(issues, 'server_error', 'High',
         df[_num(df, 'Status Code').between(500, 599)])

    redirects = df[_num(df, 'Status Code').between(300, 399)]
    redirect_set = set(_str(redirects, 'Address').replace('', pd.NA).dropna())
    _add(issues, 'redirect_chain', 'High',
         redirects[_str(redirects, 'Redirect URL').isin(redirect_set)])

    # MEDIUM severity
    _add(issues, 'title_too_long', 'Medium',
         idx[(_num(idx, 'Title 1 Pixel Width') > 561) |
             (_num(idx, 'Title 1 Length') > 60)])

    _add(issues, 'missing_meta_description', 'Medium', idx[meta == ''])

    _add(issues, 'duplicate_meta_description', 'Medium',
         idx[(meta != '') & meta.duplicated(keep=False)])

    h1_200 = _str(html_200, 'H1-1').str.strip()
    _add(issues, 'missing_h1', 'Medium', html_200[h1_200 == ''])

    _add(issues, 'redirect', 'Medium', redirects)

    _add(issues, 'orphan_page', 'Medium',
         idx[_num(idx, 'Inlinks') == 0])

    _add(issues, 'non_indexable_but_linked', 'Medium',
         df[(_str(df, 'Indexability') == 'Non-Indexable') &
            (_num(df, 'Inlinks') > 0)])

    # LOW severity
    _add(issues, 'title_too_short', 'Low',
         idx[(title != '') & (_num(idx, 'Title 1 Length') < 30)])

    _add(issues, 'meta_description_too_long', 'Low',
         idx[_num(idx, 'Meta Description 1 Length') > 155])

    _add(issues, 'duplicate_h1', 'Low',
         idx[(h1 != '') & h1.duplicated(keep=False)])

    _add(issues, 'thin_content', 'Low',
         idx[_num(idx, 'Word Count') < 200])

    _add(issues, 'slow_page', 'Low',
         df[_num(df, 'Response Time') > 1.0])

    return issues


def _str(df, column):
    if column not in df:
        return pd.Series('', index=df.index, dtype='string')
    return df[column].fillna('').astype(str)


def _num(df, column):
    if column not in df:
        return pd.Series(0, index=df.index, dtype='float64')
    return pd.to_numeric(df[column], errors='coerce').fillna(0)


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
