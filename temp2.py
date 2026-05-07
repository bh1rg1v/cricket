import json
import requests
from collections import defaultdict

MATCH_ID = "149618"
OUTPUT = "output.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.cricbuzz.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch(url):
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def over_str(over_num):
    o = int(over_num)
    b = round((over_num - o) * 10)
    return f"{o}.{b}"

def build_output(data, innings):
    balls = sorted(data["balls"], key=lambda x: (x["inningsId"], x["ballNbr"]))
    score = data["scoreDetails"]

    lines = []

    # Match summary
    lines += [
        "=" * 60,
        f"  MATCH {MATCH_ID} - INNINGS {innings}",
        "=" * 60,
        f"  Score: {score['runs']}/{score['wickets']} in {score['overs']} overs  |  Run Rate: {score['runRate']}",
        "=" * 60, "",
    ]

    # Ball by ball grouped by over
    lines.append("BALL BY BALL")
    lines.append("-" * 60)
    overs = defaultdict(list)
    for b in balls:
        overs[int(b["overNum"])].append(b)

    cumulative = 0
    for over_num in sorted(overs):
        over_balls = sorted(overs[over_num], key=lambda x: x["ballNbr"])
        over_runs = sum(b["totalRuns"] for b in over_balls if "over-break" not in b.get("event","") or b == over_balls[-1])
        # simpler: just sum all
        over_runs = sum(b["totalRuns"] for b in over_balls)
        cumulative += over_runs
        labels = "  ".join(b["ballLabel"] for b in over_balls)
        events = [b["event"] for b in over_balls if b["event"] not in ("NONE", "over-break")]
        event_str = f"  [{', '.join(events)}]" if events else ""
        lines.append(f"  Over {over_num+1:>2}:  {labels:<30}  +{over_runs} runs  (Total: {cumulative}){event_str}")

    # Batters
    lines += ["", "BATTERS", "-" * 60]
    for b in data["batters"]:
        lines.append(f"  {b['batName']:<25}  {b['runs']:>3} runs  {b['balls']:>3} balls  "
                     f"4s:{b['fours']}  6s:{b['sixes']}  SR:{b['strikeRate']}")

    # Bowlers
    lines += ["", "BOWLERS", "-" * 60]
    for b in data["bowlers"]:
        lines.append(f"  {b['bowlName']:<25}  {b['overs']} ov  {b['runs']:>3} runs  "
                     f"{b['wickets']} wkts  Econ:{b['economy']}")

    # Win Probability (computed from cumulative score progression)
    lines += ["", "WIN PROBABILITY (over-by-over run progression)", "-" * 60]
    lines.append("  [Cricbuzz computes this client-side — raw progression below]")
    cumulative = 0
    for over_num in sorted(overs):
        over_balls = sorted(overs[over_num], key=lambda x: x["ballNbr"])
        over_runs = sum(b["totalRuns"] for b in over_balls)
        cumulative += over_runs
        wickets_in_over = sum(1 for b in over_balls if "WICKET" in b.get("event", ""))
        lines.append(f"  After over {over_num+1:>2}: {cumulative:>3} runs  wickets this over: {wickets_in_over}")

    return "\n".join(lines)

def main():
    sections = []
    for innings in (1, 2):
        print(f"Fetching innings {innings}...")
        data = fetch(f"https://www.cricbuzz.com/api/mcenter/balls-map/{MATCH_ID}/{innings}")
        sections.append(build_output(data, innings))

    output = "\n\n".join(sections)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Saved to {OUTPUT} ({len(output)} chars)")

if __name__ == "__main__":
    main()
