import json
from playwright.sync_api import sync_playwright

URL = "https://www.cricbuzz.com/live-cricket-graphs/149618"
MATCH_ID = "149618"
OUTPUT = "output.txt"

def fetch_graph_data():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.cricbuzz.com/",
            }
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()
        api_data = {}

        def handle_response(response):
            # Only capture cricbuzz API calls for this match
            if "cricbuzz.com/api" in response.url and MATCH_ID in response.url:
                try:
                    data = response.json()
                    api_data[response.url] = data
                    print(f"[API] {response.url}")
                except Exception:
                    pass

        page.on("response", handle_response)

        print("Loading page...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        print("Clicking Win Probability...")
        page.get_by_text("Win Probability", exact=False).first.click()
        page.wait_for_timeout(4000)

        visible_text = page.inner_text("body")
        browser.close()

    lines = ["=== VISIBLE PAGE TEXT ===\n", visible_text.strip(), "\n\n=== CRICBUZZ API DATA ==="]
    for url, data in api_data.items():
        lines.append(f"\n--- {url} ---")
        lines.append(json.dumps(data, indent=2))

    output = "\n".join(lines)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\nSaved to {OUTPUT} ({len(output)} chars)")

if __name__ == "__main__":
    fetch_graph_data()
