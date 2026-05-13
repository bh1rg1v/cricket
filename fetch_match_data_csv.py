import re
import os
import asyncio
import requests
import pandas as pd

from collections import defaultdict
from playwright.async_api import async_playwright


# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

YEARS = range(2018, 2027)

LIMIT = 200
CONCURRENT_TABS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.cricbuzz.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────
# REQUESTS
# ─────────────────────────────────────────────────────────────

def fetch_json(url):

    r = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    r.raise_for_status()

    return r.json()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def clean_name(name):

    return (
        name
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def get_short_name(team_name):

    short_name = "".join(
        [word[0] for word in team_name.split()]
    )

    # Fix for Sunrisers Hyderabad
    if short_name == "SH":
        short_name = "SRH"

    if short_name == "KXP":
        short_name = "KXIP"

    return short_name


# ─────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────

def save_scorecard_csvs(innings_data, innings_folder):

    os.makedirs(innings_folder, exist_ok=True)

    # =========================================================
    # BATTING CSV
    # =========================================================

    batting_rows = []

    batsmen = (
        innings_data
        .get("batTeamDetails", {})
        .get("batsmenData", {})
    )

    for b in batsmen.values():

        if b.get("balls", 0) or b.get("runs", 0):

            batting_rows.append({

                "batter": b.get("batName"),
                "runs": b.get("runs"),
                "balls": b.get("balls"),
                "fours": b.get("fours"),
                "sixes": b.get("sixes"),
                "strike_rate": b.get("strikeRate"),
                "dismissal": b.get("outDesc"),

            })

    batting_df = pd.DataFrame(batting_rows)

    batting_df.to_csv(

        os.path.join(
            innings_folder,
            "batting.csv"
        ),

        index=False

    )

    # =========================================================
    # BOWLING CSV
    # =========================================================

    bowling_rows = []

    bowlers = (
        innings_data
        .get("bowlTeamDetails", {})
        .get("bowlersData", {})
    )

    for b in bowlers.values():

        bowling_rows.append({

            "bowler": b.get("bowlName"),
            "overs": b.get("overs"),
            "maidens": b.get("maidens"),
            "runs": b.get("runs"),
            "wickets": b.get("wickets"),
            "economy": b.get("economy"),

        })

    bowling_df = pd.DataFrame(bowling_rows)

    bowling_df.to_csv(

        os.path.join(
            innings_folder,
            "bowling.csv"
        ),

        index=False

    )


def save_overs_csv(ball_data, innings_folder):

    if "balls" not in ball_data:
        return

    if not ball_data["balls"]:
        return

    overs_map = defaultdict(list)

    for ball in ball_data["balls"]:

        over_num = int(ball["overNum"]) + 1

        overs_map[over_num].append(ball)

    rows = []

    for over_num in sorted(overs_map):

        over_balls = overs_map[over_num]

        runs = sum(

            b.get("totalRuns", 0)

            for b in over_balls

        )

        wickets = sum(

            1

            for b in over_balls

            if b.get("isWicket")

        )

        rows.append({

            "over": over_num,
            "runs": runs,
            "wickets": wickets,

        })

    overs_df = pd.DataFrame(rows)

    overs_df.to_csv(

        os.path.join(
            innings_folder,
            "overs.csv"
        ),

        index=False

    )


# ─────────────────────────────────────────────────────────────
# SCORECARD
# ─────────────────────────────────────────────────────────────

async def fetch_scorecard_from_page(page, match_id):

    import json as _json

    url = (
        f"https://www.cricbuzz.com/"
        f"live-cricket-scorecard/{match_id}"
    )

    await page.goto(

        url,

        wait_until="domcontentloaded",

        timeout=60000

    )

    await page.wait_for_timeout(3000)

    raw = await page.evaluate("""
        () => {

            for (
                const s of document.querySelectorAll(
                    'script:not([src])'
                )
            ) {

                if (
                    s.textContent.includes(
                        'scorecardApiData'
                    )
                ) {
                    return s.textContent;
                }
            }

            return '';
        }
    """)

    m = re.search(

        r'\\"scoreCard\\":(\[.*?\]),\\"matchHeader\\"',

        raw,

        re.DOTALL

    )

    # print(
    #     f"  DEBUG scorecard regex match:"
    #     f" {bool(m)}, raw len: {len(raw)}"
    # )

    if not m:
        return None

    try:

        sc_raw = (

            m.group(1)

            .replace('\\"', '"')

            .replace('\\\\', '\\')

        )

        innings_list = _json.loads(sc_raw)

    except Exception as e:

        print(f"Scorecard parse error: {e}")

        return None

    # =========================================================
    # TEAM SHORT NAMES
    # =========================================================

    short_names = []

    for inn in innings_list:

        full_name = (

            inn
            .get("batTeamDetails", {})
            .get("batTeamName", "TEAM")

        )

        short_name = get_short_name(full_name)

        short_names.append(short_name)

    team_a_short = (
        short_names[0]
        if len(short_names) > 0
        else "TEAMA"
    )

    team_b_short = (
        short_names[1]
        if len(short_names) > 1
        else "TEAMB"
    )

    return {

        "team_a": team_a_short,
        "team_b": team_b_short,
        "innings": innings_list,
        "innings_short_names": short_names,

    }


# ─────────────────────────────────────────────────────────────
# MATCH WORKER
# ─────────────────────────────────────────────────────────────

async def process_match(
    context,
    BASE_OUTPUT_DIR,
    match_id,
    i
):

    page = await context.new_page()

    try:

        print(f"\n[{i}] Match {match_id}")

        # print("  Fetching scorecard...")

        scorecard_data = await fetch_scorecard_from_page(
            page,
            match_id
        )

        if not scorecard_data:

            print("  Failed to fetch scorecard")

            return

        TEAM_A = scorecard_data["team_a"]
        TEAM_B = scorecard_data["team_b"]

        innings_list = scorecard_data["innings"]

        # =====================================================
        # MATCH FOLDER
        # =====================================================

        folder = os.path.join(

            BASE_OUTPUT_DIR,

            f"MATCH{i}_{TEAM_A}_{TEAM_B}"

        )

        os.makedirs(folder, exist_ok=True)

        # =====================================================
        # SAVE BATTING/BOWLING CSVs
        # =====================================================

        for idx, innings_data in enumerate(

            innings_list,

            start=1

        ):

            batting_team = clean_name(

                scorecard_data[
                    "innings_short_names"
                ][idx - 1]

            )

            innings_folder = os.path.join(

                folder,

                f"innings{idx}_{batting_team}"

            )

            save_scorecard_csvs(

                innings_data,
                innings_folder

            )

        # =====================================================
        # SAVE OVERS CSV
        # =====================================================

        for innings in (1, 2):

            # print(
            #     f"  Fetching innings {innings}..."
            # )

            try:

                data = fetch_json(

                    f"https://www.cricbuzz.com/"
                    f"api/mcenter/"
                    f"balls-map/{match_id}/{innings}"

                )

                batting_team = clean_name(

                    scorecard_data[
                        "innings_short_names"
                    ][innings - 1]

                )

                innings_folder = os.path.join(

                    folder,

                    f"innings{innings}_{batting_team}"

                )

                save_overs_csv(

                    data,
                    innings_folder

                )

            except Exception as e:

                print(

                    f"  No ball-by-ball "
                    f"for innings {innings}: {e}"

                )

        print(f"  Saved -> {folder}")

    finally:

        await page.close()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=False,

            channel="chrome",

            args=[
                "--disable-blink-features="
                "AutomationControlled"
            ]
        )

        context = await browser.new_context(

            user_agent=HEADERS["User-Agent"],

            viewport={
                "width": 1280,
                "height": 800
            },

            extra_http_headers={
                "Referer": "https://www.cricbuzz.com/"
            },
        )

        await context.add_init_script(

            "Object.defineProperty("
            "navigator, "
            "'webdriver', "
            "{get: () => undefined}"
            ")"

        )

        for YEAR in YEARS:

            YEAR = str(YEAR)

            MATCH_IDS_FILE = (
                f"data/ipl/{YEAR}/match_ids.txt"
            )

            BASE_OUTPUT_DIR = (
                f"data/ipl/{YEAR}"
            )

            print(f"\n{'=' * 80}")
            print(f"PROCESSING IPL {YEAR}")
            print(f"{'=' * 80}")

            def load_match_ids():

                with open(

                    MATCH_IDS_FILE,

                    encoding="utf-8"

                ) as f:

                    return [

                        line.strip()

                        for line in f

                        if line.strip()

                    ]

            match_ids = load_match_ids()

            match_ids = match_ids[:LIMIT]

            print(
                f"Processing "
                f"{len(match_ids)} matches"
            )

            semaphore = asyncio.Semaphore(
                CONCURRENT_TABS
            )

            async def sem_task(match_id, i):

                async with semaphore:

                    await process_match(

                        context,
                        BASE_OUTPUT_DIR,
                        match_id,
                        i

                    )

            tasks = [

                sem_task(match_id, i)

                for i, match_id in enumerate(

                    match_ids,

                    start=1

                )

            ]

            await asyncio.gather(*tasks)

        await browser.close()


# ─────────────────────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    asyncio.run(main())