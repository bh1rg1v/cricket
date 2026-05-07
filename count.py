import os
import re

DATA_DIR = "data/ipl/2026"
THRESHOLD = 67

def main():
    total = 0
    counter = 0

    for folder in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, folder, "data.txt")
        if not os.path.exists(path):
            continue

        total += 1
        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Find the win probability section
        wp_section = re.search(r'WIN PROBABILITY.*?(?=={60}|\Z)', content, re.DOTALL)
        if not wp_section:
            continue

        # Extract all "TEAM: X%" values
        probs = re.findall(r'(\w+): (\d+)%', wp_section.group())

        # Group max probability per team
        team_max = {}
        for team, pct in probs:
            team_max[team] = max(team_max.get(team, 0), int(pct))

        # Check if both teams hit >= THRESHOLD at least once
        teams = list(team_max.keys())
        if len(teams) >= 2 and all(team_max[t] >= THRESHOLD for t in teams):
            counter += 1
            print(f"  [YES] {folder}  —  " + "  ".join(f"{t}: {team_max[t]}%" for t in teams))
        else:
            print(f"  [NO]  {folder}  —  " + "  ".join(f"{t}: {team_max[t]}%" for t in teams))

    print(f"\nMatches where both teams hit >= {THRESHOLD}%: {counter}/{total}")
    if total:
        print(f"Percentage: {counter/total*100:.1f}%")

if __name__ == "__main__":
    main()
