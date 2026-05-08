from playwright.sync_api import sync_playwright

PLAYER_ID = 14701
OUTPUT = "output.txt"

def fetch(page, url, label):
    print(f"  Loading {label}...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    if "all-matches" in url:
        print(f"  Scrolling to load all data...")
        prev_height = 0
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            curr_height = page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                break
            prev_height = curr_height
        print(f"  Done scrolling.")

    return page.inner_text("body").strip()

def col(val, width):
    return str(val).ljust(width)

def parse_career_summary(lines, section_name):
    idx = next((i for i, l in enumerate(lines) if section_name in l), None)
    if idx is None:
        return ""

    # Formats are on the next few lines after the section header
    formats = []
    i = idx + 1
    while i < len(lines) and lines[i].strip() in ("Test", "ODI", "T20", "IPL", "T20I"):
        formats.append(lines[i].strip())
        i += 1

    # Stats: each stat name is followed by N value lines (one per format)
    stats = {}
    stat_order = []
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # Stop at next section
        if any(line.startswith(s) for s in ("Bowling Career", "Batting Career", "Career Timeline", "SUMMARY", "Related")):
            break
        # Stat name line (no digits, not a format name)
        if not any(c.isdigit() for c in line) and line not in formats and "/" not in line and "." not in line:
            stat_name = line
            stat_order.append(stat_name)
            stats[stat_name] = []
            i += 1
            # Collect values for each format
            while i < len(lines) and len(stats[stat_name]) < len(formats):
                v = lines[i].strip()
                if v:
                    stats[stat_name].append(v)
                i += 1
        else:
            i += 1

    if not stats:
        return ""

    w0, wn = 15, 12
    out = [f"  {section_name}", "  " + "-" * (w0 + wn * len(formats))]
    out.append("  " + col("Stat", w0) + "".join(col(f, wn) for f in formats))
    out.append("  " + "-" * (w0 + wn * len(formats)))
    for stat in stat_order:
        vals = stats.get(stat, [])
        out.append("  " + col(stat, w0) + "".join(col(v, wn) for v in vals))
    return "\n".join(out)

def extract_series_links(page):
    """Extract seriesName -> URL by scanning full page HTML after scrolling."""
    import re
    raw = page.content()
    with open('debug_html.txt', 'w', encoding='utf-8') as f:
        f.write(raw)
    result = {}
    for m in re.finditer(r'seriesID[\\"]+:(\d+),[\\"]+seriesName[\\"]+:[\\"]+(.*?)[\\"]', raw):
        series_id, name = m.group(1), m.group(2)
        slug = name.lower().replace(' ', '-')
        result[name.upper()] = f"https://www.cricbuzz.com/cricket-series/{series_id}/{slug}"
    return result

def parse_match_table(text, n_cols):
    """Parse table where each row's values are on separate lines with \t-only lines between.
    Rows are separated by blank lines. Section headers appear between row groups."""
    lines = text.splitlines()

    # Find where the header row is (contains tab-separated column names)
    start = None
    for i, line in enumerate(lines):
        if '\t' in line and ('Score' in line or 'Wickets' in line):
            start = i + 1
            break
    if start is None:
        return []

    footer_markers = {"APPS", "Android", "iOS", "FOLLOW US ON", "Facebook", "COMPANY"}
    rows = []
    section = ""
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Stop at footer
        if stripped in footer_markers:
            break

        # Blank line — skip
        if not stripped:
            i += 1
            continue

        # Tab-only line — skip (separator between values)
        if stripped == '\t':
            i += 1
            continue

        # Check if this is a section header:
        # Section headers are NOT tab-only and are followed eventually by a value then a \t line
        # Heuristic: if next non-empty line after this is a \t line, it's a data value not a header
        # A section header has no \t in it and the line after it (skipping blanks) is also not a \t
        if '\t' not in line:
            # Look ahead: if the very next line (ignoring truly empty lines but NOT tab lines) is a tab-only line,
            # then this is a data value. Otherwise it's a section header.
            j = i + 1
            while j < len(lines) and lines[j] == '':
                j += 1
            next_line = lines[j] if j < len(lines) else ''
            if next_line == '\t' or next_line.strip() == '' and '\t' in next_line:
                # This is the first value of a data row — collect the full row
                values = [stripped]
                k = i + 1
                while k < len(lines) and len(values) < n_cols:
                    s = lines[k].strip()
                    if s and s != '\t':
                        values.append(s)
                    k += 1
                if len(values) == n_cols:
                    rows.append([section] + values)
                i = k
            else:
                # It's a section header
                section = stripped
                i += 1
        else:
            i += 1

    return rows

def format_match_table(title, headers, rows, series_links=None):
    if not rows:
        return f"  [No data found for {title}]"

    all_cols = ["Series"] + headers
    widths = [max(len(str(r[i])) if i < len(r) else 0 for r in ([all_cols] + rows)) for i in range(len(all_cols))]

    sep = "  " + "-+-".join("-" * w for w in widths)
    out = []
    out.append("  " + " | ".join(col(all_cols[i], widths[i]) for i in range(len(all_cols))))
    out.append(sep)

    prev_section = None
    for row in rows:
        section = row[0] if row else ""
        if section != prev_section:
            link = (series_links or {}).get(section, "")
            section_line = f"\n  ── {section} ──"
            if link:
                section_line += f"  {link}"
            out.append(section_line)
            prev_section = section
        data = row[1:]
        out.append("  " + " | ".join(col(data[i] if i < len(data) else "", widths[i+1]) for i in range(len(headers))))

    return "\n".join(out)

def format_profile(text):
    lines = text.splitlines()
    fields = ["Born", "Birth Place", "Role", "Batting Style", "Bowling Style"]
    out = ["  " + "-" * 50]
    for field in fields:
        for i, line in enumerate(lines):
            if line.strip() == field and i + 1 < len(lines):
                out.append(f"  {field:<20} {lines[i+1].strip()}")
                break
    out.append("  " + "-" * 50)
    return "\n".join(out)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Referer": "https://www.cricbuzz.com/"},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        profile_url = f"https://www.cricbuzz.com/profiles/{PLAYER_ID}"
        profile_text = fetch(page, profile_url, "MAIN PROFILE")
        player_name = page.locator("span.text-xl.font-bold").first.inner_text().strip()

        batting_link = page.evaluate(f"""() => {{
            const a = Array.from(document.querySelectorAll('a[href*="/{PLAYER_ID}/"][href*="batting"]'));
            return a.length ? a[0].href : null;
        }}""")
        batting_text = fetch(page, batting_link, "BATTING") if batting_link else ""
        bat_series_links = extract_series_links(page) if batting_link else {}

        page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        bowling_link = page.evaluate(f"""() => {{
            const a = Array.from(document.querySelectorAll('a[href*="/{PLAYER_ID}/"][href*="bowling"]'));
            return a.length ? a[0].href : null;
        }}""")
        bowling_text = fetch(page, bowling_link, "BOWLING") if bowling_link else ""
        bowl_series_links = extract_series_links(page) if bowling_link else {}

        browser.close()

    profile_lines = profile_text.splitlines()
    bat_rows  = parse_match_table(batting_text,  8)
    bowl_rows = parse_match_table(bowling_text,  8)

    sections = [
        "=" * 70,
        f"  PLAYER PROFILE  —  {player_name}  (ID: {PLAYER_ID})",
        "=" * 70,
        format_profile(profile_text),
        "",
        parse_career_summary(profile_lines, "Batting Career Summary"),
        "",
        parse_career_summary(profile_lines, "Bowling Career Summary"),
        "",
        "=" * 70,
        "  BATTING — ALL MATCHES",
        "=" * 70,
        format_match_table("Batting", ["Score","OPPN.","Format","Venue","Date","SR","4s","6s"], bat_rows, bat_series_links),
        "",
        "=" * 70,
        "  BOWLING — ALL MATCHES",
        "=" * 70,
        format_match_table("Bowling", ["Wickets","OPPN.","Format","Venue","Date","Economy","Overs","Maidens"], bowl_rows, bowl_series_links),
    ]

    output = "\n".join(sections)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Saved to {OUTPUT} ({len(output)} chars)")

if __name__ == "__main__":
    main()