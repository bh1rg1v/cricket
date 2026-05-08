import re
import os
from playwright.sync_api import sync_playwright

seasons = [
    ("2008", "https://www.cricbuzz.com/cricket-series/2058/indian-premier-league-2008/matches"),
    ("2009", "https://www.cricbuzz.com/cricket-series/2059/indian-premier-league-2009/matches"),
    ("2010", "https://www.cricbuzz.com/cricket-series/2060/indian-premier-league-2010/matches"),
    ("2011", "https://www.cricbuzz.com/cricket-series/2037/indian-premier-league-2011/matches"),
    ("2012", "https://www.cricbuzz.com/cricket-series/2115/indian-premier-league-2012/matches"),
    ("2013", "https://www.cricbuzz.com/cricket-series/2170/indian-premier-league-2013/matches"),
    ("2014", "https://www.cricbuzz.com/cricket-series/2261/indian-premier-league-2014/matches"),
    ("2015", "https://www.cricbuzz.com/cricket-series/2330/indian-premier-league-2015/matches"),
    ("2016", "https://www.cricbuzz.com/cricket-series/2430/indian-premier-league-2016/matches"),
    ("2017", "https://www.cricbuzz.com/cricket-series/2568/indian-premier-league-2017/matches"),
    ("2018", "https://www.cricbuzz.com/cricket-series/2676/indian-premier-league-2018/matches"),
    ("2019", "https://www.cricbuzz.com/cricket-series/2810/indian-premier-league-2019/matches"),
    ("2020", "https://www.cricbuzz.com/cricket-series/3130/indian-premier-league-2020/matches"),
    ("2021", "https://www.cricbuzz.com/cricket-series/3472/indian-premier-league-2021/matches"),
    ("2022", "https://www.cricbuzz.com/cricket-series/4061/indian-premier-league-2022/matches"),
    ("2023", "https://www.cricbuzz.com/cricket-series/5945/indian-premier-league-2023/matches"),
    ("2024", "https://www.cricbuzz.com/cricket-series/7607/indian-premier-league-2024/matches"),
    ("2025", "https://www.cricbuzz.com/cricket-series/9237/indian-premier-league-2025/matches"),
    ("2026", "https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches"),
]

def get_match_ids(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    # Match IDs are in hrefs like /live-cricket-scores/{matchId}/...
    hrefs = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href*="/live-cricket-scores/"]'))
                   .map(a => a.getAttribute('href'))
    """)
    ids = []
    seen = set()
    for href in hrefs:
        m = re.search(r'/live-cricket-scores/(\d+)/', href)
        if m:
            mid = m.group(1)
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids

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

    for year, url in seasons:
        print(f"  Fetching {year}...")
        ids = get_match_ids(page, url)
        out_path = os.path.join("data", "ipl", year, "match_ids.txt")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(ids))
        print(f"    Saved {len(ids)} match IDs -> {out_path}")

    browser.close()
