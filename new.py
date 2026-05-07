import re
from playwright.sync_api import sync_playwright

SERIES_URL = "https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches"
PREFIX = "https://www.cricbuzz.com/live-cricket-scores/"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={"Referer": "https://www.cricbuzz.com/"},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        page.goto(SERIES_URL, wait_until="domcontentloaded", timeout=60000)

        print("Window open — waiting 10 seconds...")
        page.wait_for_timeout(10000)

        html = page.content()
        browser.close()

    ids = re.findall(r'/live-cricket-scores/(\d+)/', html)
    seen = set()
    links = []
    for match_id in ids:
        if match_id not in seen:
            seen.add(match_id)
            links.append(PREFIX + match_id)

    links.sort()

    with open("matches.txt", "w") as f:
        f.write("\n".join(links))

    print(f"Saved {len(links)} links to matches.txt")
    for link in links:
        print(link)
    print(f"Found {len(seen)} unique match IDs.")

if __name__ == "__main__":
    main()
