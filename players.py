import os
import re
import json
from playwright.sync_api import sync_playwright

MATCHES_FILE = "matches.txt"
OUTPUT = "players/players.txt"

limit = 50 # number of matches to process = number of matches completed

def load_match_ids():
    with open(MATCHES_FILE) as f:
        links = [l.strip() for l in f if l.strip()]
    ids = []
    for link in links:
        m = re.search(r'/(\d+)$', link)
        if m:
            ids.append(m.group(1))
    return ids

def main():
    match_ids = load_match_ids()
    players = {}  # id -> name

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={
                "Referer": "https://www.cricbuzz.com/",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        for i, match_id in enumerate(match_ids[:limit]):
            print(f"[{i+1}/{len(match_ids)}] Match {match_id}...")
            for innings in (1, 2):
                try:
                    url = f"https://www.cricbuzz.com/api/mcenter/balls-map/{match_id}/{innings}"
                    response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    if not response or response.status != 200:
                        continue
                    data = json.loads(page.inner_text("body"))
                    for b in data.get("batters", []):
                        players[b["batId"]] = b["batName"]
                    for b in data.get("bowlers", []):
                        players[b["bowlerId"]] = b["bowlName"]
                except Exception as e:
                    print(f"  Innings {innings} error: {e}")

        browser.close()

    os.makedirs("players", exist_ok=True)
    lines = [f"{pid} - {name}" for pid, name in sorted(players.items())]
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nSaved {len(players)} players to {OUTPUT}")

if __name__ == "__main__":
    main()
