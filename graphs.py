import re
import os
import requests
from collections import defaultdict
from playwright.sync_api import sync_playwright

BASE_MATCH_ID = 149618
MATCH_INCREMENT = 11  # unused, kept for reference
NUM_MATCHES = 50
MATCHES_FILE = "matches.txt"
BASE_OUTPUT_DIR = "data/ipl/2026"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.cricbuzz.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch(url):
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def build_innings(data, match_id, innings):
    balls = sorted(data["balls"], key=lambda x: (x["inningsId"], x["ballNbr"]))
    score = data["scoreDetails"]

    lines = [
        "=" * 60,
        f"  MATCH {match_id} - INNINGS {innings}",
        "=" * 60,
        f"  Score: {score['runs']}/{score['wickets']} in {score['overs']} overs  |  Run Rate: {score['runRate']}",
        "=" * 60, "",
        "BALL BY BALL",
        "-" * 60,
    ]

    overs = defaultdict(list)
    for b in balls:
        overs[int(b["overNum"])].append(b)

    cumulative = 0
    for over_num in sorted(overs):
        over_balls = sorted(overs[over_num], key=lambda x: x["ballNbr"])
        over_runs = sum(b["totalRuns"] for b in over_balls)
        cumulative += over_runs
        labels = "  ".join(b["ballLabel"] for b in over_balls)
        events = [b["event"] for b in over_balls if b["event"] not in ("NONE", "over-break")]
        event_str = f"  [{', '.join(events)}]" if events else ""
        lines.append(f"  Over {over_num+1:>2}:  {labels:<30}  +{over_runs} runs  (Total: {cumulative}){event_str}")

    lines += ["", "BATTERS", "-" * 60]
    for b in data["batters"]:
        lines.append(f"  {b['batName']:<25}  {b['runs']:>3} runs  {b['balls']:>3} balls  "
                     f"4s:{b['fours']}  6s:{b['sixes']}  SR:{b['strikeRate']}")

    lines += ["", "BOWLERS", "-" * 60]
    for b in data["bowlers"]:
        lines.append(f"  {b['bowlName']:<25}  {b['overs']} ov  {b['runs']:>3} runs  "
                     f"{b['wickets']} wkts  Econ:{b['economy']}")

    return "\n".join(lines)

MAX_RETRIES = 3

def get_match_teams(page):
    """Extract short team names from win probability bar title attributes."""
    try:
        # titles look like "Over 1 | RCB: 59% • SRH: 41%"
        sample = page.evaluate("""() => {
            const el = document.querySelector('[title*="Over"][title*="%"]');
            return el ? el.getAttribute('title') : null;
        }""")
        if sample:
            m = re.search(r'\| (\w+): \d+% • (\w+): \d+%', sample)
            if m:
                return m.group(1), m.group(2)
    except Exception:
        pass
    return "TeamA", "TeamB"

def fetch_win_prob(page, match_id):
    url = f"https://www.cricbuzz.com/live-cricket-graphs/{match_id}"

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Loading {url} for win probability (attempt {attempt}/{MAX_RETRIES})...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            page.get_by_text("Win Probability", exact=True).first.click(timeout=15000)
            page.wait_for_timeout(2000)
            page.get_by_text("Over-by-over", exact=True).first.click(timeout=15000)
            page.wait_for_timeout(2000)
            break
        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                return f"  [Win probability unavailable after {MAX_RETRIES} attempts]"
            page.wait_for_timeout(3000)

    entries = page.evaluate("""() =>
        Array.from(document.querySelectorAll('[title*="Over"][title*="%"]'))
            .map(el => el.getAttribute('title'))
    """)

    seen = set()
    over_titles = []
    for t in entries:
        if t and t not in seen and not re.match(r'^(Royal|Sunrisers|Mumbai|Chennai|Delhi|Kolkata|Punjab|Rajasthan|Lucknow|Gujarat)', t):
            seen.add(t)
            over_titles.append(t)

    lines = ["", "WIN PROBABILITY — Over by Over", "-" * 60,
             f"  {'Over':<8}  Details", "  " + "-" * 40]
    for t in over_titles:
        m = re.match(r'Over (\d+) \| (.+)', t)
        if m:
            lines.append(f"  {m.group(1):<8}  {m.group(2)}")

    return "\n".join(lines)

def load_match_ids():
    with open(MATCHES_FILE) as f:
        links = [l.strip() for l in f if l.strip()]
    ids = []
    for link in links:
        m = re.search(r'/(\d+)$', link)
        if m:
            ids.append(m.group(1))
    # Start from BASE_MATCH_ID
    start = next((i for i, mid in enumerate(ids) if mid == str(BASE_MATCH_ID)), 0)
    return ids[start:]

def main():
    match_ids = load_match_ids()
    total = min(NUM_MATCHES, len(match_ids))
    print(f"Found {len(match_ids)} matches from {BASE_MATCH_ID}, fetching {total}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Referer": "https://www.cricbuzz.com/"},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        for i in range(total):
            match_id = match_ids[i]
            print(f"\n[{i+1}/{NUM_MATCHES}] Match {match_id}")
            match_sections = []

            # Ball-by-ball for both innings via API
            for innings in (1, 2):
                print(f"  Fetching innings {innings}...")
                try:
                    data = fetch(f"https://www.cricbuzz.com/api/mcenter/balls-map/{match_id}/{innings}")
                    match_sections.append(build_innings(data, match_id, innings))
                except Exception as e:
                    match_sections.append(f"  [Innings {innings} error: {e}]")

            # Check if already fetched by scanning existing folders for this match number
            match_num = f"MATCH{i+1}"
            existing = next(
                (d for d in os.listdir(BASE_OUTPUT_DIR)
                 if d.startswith(match_num + "_") and os.path.exists(os.path.join(BASE_OUTPUT_DIR, d, "data.txt")))
                if os.path.exists(BASE_OUTPUT_DIR) else None, None
            )
            if existing:
                print(f"  Skipping — {os.path.join(BASE_OUTPUT_DIR, existing, 'data.txt')} already exists")
                continue

            # Win probability via browser (also extracts team names from page title)
            win_prob = fetch_win_prob(page, match_id)
            match_sections.append(win_prob)

            team_a, team_b = get_match_teams(page)
            folder = os.path.join(BASE_OUTPUT_DIR, f"{match_num}_{team_a}_{team_b}")
            os.makedirs(folder, exist_ok=True)
            output_path = os.path.join(folder, "data.txt")

            output = "\n\n".join(match_sections)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"  Saved to {output_path} ({len(output)} chars)")

        browser.close()

if __name__ == "__main__":
    main()
