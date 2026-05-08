import re
import os
import requests
import json
from collections import defaultdict
from playwright.sync_api import sync_playwright

YEARS = range(2008, 2027)
LIMIT = 60
MAX_RETRIES = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.cricbuzz.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Scorecard ────────────────────────────────────────────────────────────────

def fetch_scorecard_from_page(page, match_id):
    """Navigate to scorecard page and extract structured data from embedded JSON."""

    import json as _json

    url = f"https://www.cricbuzz.com/live-cricket-scorecard/{match_id}"

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    # Extract scorecardApiData from embedded Next.js JSON
    raw = page.evaluate("""
        () => {
            for (const s of document.querySelectorAll('script:not([src])')) {
                if (s.textContent.includes('scorecardApiData')) return s.textContent;
            }
            return '';
        }
    """)

    # Find the scoreCard JSON array
    m = re.search(
        r'\\"scoreCard\\":(\[.*?\]),\\"matchHeader\\"',
        raw,
        re.DOTALL
    )

    print(f"  DEBUG scorecard regex match: {bool(m)}, raw len: {len(raw)}")

    if not m:
        # fallback
        text = page.inner_text('main').strip()
        return text[:5000]

    try:
        # Unescape and parse
        sc_raw = m.group(1).replace('\\"', '"').replace('\\\\', '\\')
        innings_list = _json.loads(sc_raw)

    except Exception as e:
        return f"[Scorecard parse error: {e}]"

    lines = []

    for inn in innings_list:

        bat_team = inn.get('batTeamDetails', {}).get('batTeamName', '?')
        score = inn.get('scoreDetails', {})

        lines.append(f"\n{'='*60}")
        lines.append(
            f"  {bat_team}  "
            f"{score.get('runs','?')}/"
            f"{score.get('wickets','?')} "
            f"({score.get('overs','?')} ov)  "
            f"RR: {score.get('runRate','?')}"
        )
        lines.append(f"{'='*60}")

        # Batters
        lines.append("\nBATTING")

        lines.append(
            f"  {'Batter':<25} {'R':>4} {'B':>4} "
            f"{'4s':>3} {'6s':>3} {'SR':>7}  Dismissal"
        )

        lines.append("  " + "-"*75)

        for b in inn.get('batTeamDetails', {}).get('batsmenData', {}).values():

            if b.get('balls', 0) or b.get('runs', 0):

                lines.append(
                    f"  {b['batName']:<25} "
                    f"{b['runs']:>4} "
                    f"{b.get('balls',0):>4} "
                    f"{b['fours']:>3} "
                    f"{b['sixes']:>3} "
                    f"{b['strikeRate']:>7}  "
                    f"{b.get('outDesc','')}"
                )

        extras = inn.get('extrasData', {})

        lines.append(
            f"  Extras: {extras.get('total',0)} "
            f"(b {extras.get('byes',0)}, "
            f"lb {extras.get('legByes',0)}, "
            f"w {extras.get('wides',0)}, "
            f"nb {extras.get('noBalls',0)})"
        )

        # Bowlers
        lines.append("\nBOWLING")

        lines.append(
            f"  {'Bowler':<25} {'O':>5} {'M':>3} "
            f"{'R':>4} {'W':>3} {'Econ':>6}"
        )

        lines.append("  " + "-"*50)

        for b in inn.get('bowlTeamDetails', {}).get('bowlersData', {}).values():

            lines.append(
                f"  {b['bowlName']:<25} "
                f"{b['overs']:>5} "
                f"{b['maidens']:>3} "
                f"{b['runs']:>4} "
                f"{b['wickets']:>3} "
                f"{b['economy']:>6}"
            )

        # Fall of wickets
        wkts = inn.get('wicketsData', {})

        if wkts:

            fow = ', '.join(
                f"{v['wktRuns']}-{v['wktNbr']} "
                f"({v['batName']}, {v['wktOver']} ov)"
                for v in sorted(
                    wkts.values(),
                    key=lambda x: x['wktNbr']
                )
            )

            lines.append(f"\n  Fall of Wickets: {fow}")

    return '\n'.join(lines)


# ── Ball-by-ball ─────────────────────────────────────────────────────────────

def build_innings(data, match_id, innings):

    balls = sorted(
        data["balls"],
        key=lambda x: (x["inningsId"], x["ballNbr"])
    )

    score = data["scoreDetails"]

    lines = [
        "=" * 60,
        f"  MATCH {match_id} - INNINGS {innings}",
        "=" * 60,
        f"  Score: {score['runs']}/{score['wickets']} "
        f"in {score['overs']} overs  |  "
        f"Run Rate: {score['runRate']}",
        "=" * 60,
        "",
        "BALL BY BALL",
        "-" * 60,
    ]

    overs = defaultdict(list)

    for b in balls:
        overs[int(b["overNum"])].append(b)

    cumulative = 0

    for over_num in sorted(overs):

        over_balls = sorted(
            overs[over_num],
            key=lambda x: x["ballNbr"]
        )

        over_runs = sum(b["totalRuns"] for b in over_balls)

        cumulative += over_runs

        labels = "  ".join(b["ballLabel"] for b in over_balls)

        events = [
            b["event"]
            for b in over_balls
            if b["event"] not in ("NONE", "over-break")
        ]

        event_str = f"  [{', '.join(events)}]" if events else ""

        lines.append(
            f"  Over {over_num+1:>2}:  "
            f"{labels:<30}  "
            f"+{over_runs} runs  "
            f"(Total: {cumulative})"
            f"{event_str}"
        )

    lines += ["", "BATTERS", "-" * 60]

    for b in data["batters"]:

        lines.append(
            f"  {b['batName']:<25}  "
            f"{b['runs']:>3} runs  "
            f"{b['balls']:>3} balls  "
            f"4s:{b['fours']}  "
            f"6s:{b['sixes']}  "
            f"SR:{b['strikeRate']}"
        )

    lines += ["", "BOWLERS", "-" * 60]

    for b in data["bowlers"]:

        lines.append(
            f"  {b['bowlName']:<25}  "
            f"{b['overs']} ov  "
            f"{b['runs']:>3} runs  "
            f"{b['wickets']} wkts  "
            f"Econ:{b['economy']}"
        )

    return "\n".join(lines)


# ── Win probability ───────────────────────────────────────────────────────────




def get_match_teams(page):
    """Extract short team names from win probability titles."""

    try:

        sample = page.evaluate("""
            () => {
                const el = document.querySelector(
                    '[title*="Over"][title*="%"]'
                );
                return el ? el.getAttribute('title') : null;
            }
        """)

        if sample:

            m = re.search(
                r'\| (\w+): \d+% • (\w+): \d+%',
                sample
            )

            if m:
                return m.group(1), m.group(2)

    except Exception:
        pass

    return None, None


def get_teams_from_url(page):
    """Extract team names from page URL."""

    try:

        url = page.url

        m = re.search(r'/(\w+)-vs-(\w+)-', url)

        if m:
            return m.group(1).upper(), m.group(2).upper()

    except Exception:
        pass

    return "TeamA", "TeamB"


def fetch_win_prob(page, match_id):

    url = f"https://www.cricbuzz.com/live-cricket-graphs/{match_id}"

    print(f"  Loading graphs...")

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2000)

        # fallback
        team_a, team_b = get_teams_from_url(page)

        # click Win Probability tab
        try:

            page.get_by_text(
                "Win Probability",
                exact=True
            ).first.click(timeout=5000)

            page.wait_for_timeout(2000)

            page.get_by_text(
                "Over-by-over",
                exact=True
            ).first.click(timeout=5000)

            page.wait_for_timeout(2000)

            ta, tb = get_match_teams(page)

            if ta:
                team_a, team_b = ta, tb

        except Exception:
            return (
                f"  [Win probability not available for this match]",
                team_a,
                team_b
            )

        entries = page.evaluate("""
            () =>
                Array.from(
                    document.querySelectorAll(
                        '[title*="Over"][title*="%"]'
                    )
                ).map(el => el.getAttribute('title'))
        """)

        seen = set()
        over_titles = []

        for t in entries:

            if (
                t and
                t not in seen and
                not re.match(
                    r'^(Royal|Sunrisers|Mumbai|Chennai|Delhi|'
                    r'Kolkata|Punjab|Rajasthan|Lucknow|'
                    r'Gujarat|Deccan|Kochi|Pune|Rising)',
                    t
                )
            ):

                seen.add(t)
                over_titles.append(t)

        if not over_titles:
            return f"  [Win probability data empty]", team_a, team_b

        lines = [
            "",
            "WIN PROBABILITY — Over by Over",
            "-" * 60,
            f"  {'Over':<8}  Details",
            "  " + "-" * 40
        ]

        for t in over_titles:

            m = re.match(r'Over (\d+) \| (.+)', t)

            if m:
                lines.append(
                    f"  {m.group(1):<8}  {m.group(2)}"
                )

        return "\n".join(lines), team_a, team_b

    except Exception as e:
        return f"  [Win probability error: {e}]", None, None


# ── Main ──────────────────────────────────────────────────────────────────────

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"]
    )

    context = browser.new_context(
        user_agent=HEADERS["User-Agent"],
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Referer": "https://www.cricbuzz.com/"
        },
    )

    context.add_init_script(
        "Object.defineProperty("
        "navigator, "
        "'webdriver', "
        "{get: () => undefined}"
        ")"
    )

    page = context.new_page()

    for YEAR in YEARS:

        YEAR = str(YEAR)

        MATCH_IDS_FILE = f"data/ipl/{YEAR}/match_ids.txt"
        BASE_OUTPUT_DIR = f"data/ipl/{YEAR}"

        print(f"\n{'='*80}")
        print(f"PROCESSING IPL {YEAR}")
        print(f"{'='*80}")

        def load_match_ids():

            with open(MATCH_IDS_FILE) as f:
                return [
                    l.strip()
                    for l in f
                    if l.strip()
                ]

        match_ids = load_match_ids()

        # Optional limit
        match_ids = match_ids[:LIMIT]

        print(
            f"Processing {len(match_ids)} "
            f"matches for IPL {YEAR}"
        )

        for i, match_id in enumerate(match_ids, 1):

            print(f"\n[{i}/{len(match_ids)}] Match {match_id}")

            sections = []

            # Scorecard
            print(f"  Fetching scorecard...")

            sc_text = fetch_scorecard_from_page(
                page,
                match_id
            )

            sections.append(
                f"SCORECARD\n{'=' * 60}\n{sc_text}"
            )

            # Ball-by-ball
            for innings in (1, 2):

                print(f"  Fetching innings {innings}...")

                try:

                    data = fetch_json(
                        f"https://www.cricbuzz.com/api/mcenter/"
                        f"balls-map/{match_id}/{innings}"
                    )

                    sections.append(
                        build_innings(
                            data,
                            match_id,
                            innings
                        )
                    )

                except Exception as e:

                    sections.append(
                        f"  [Innings {innings} unavailable: {e}]"
                    )

            # Win probability
            win_prob, team_a, team_b = fetch_win_prob(
                page,
                match_id
            )

            sections.append(win_prob)

            team_a = team_a or "TeamA"
            team_b = team_b or "TeamB"

            folder = os.path.join(
                BASE_OUTPUT_DIR,
                f"MATCH{i}_{team_a}_{team_b}"
            )

            os.makedirs(folder, exist_ok=True)

            out_path = os.path.join(folder, "data.txt")

            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(sections))

            print(f"  Saved -> {out_path}")

    browser.close()