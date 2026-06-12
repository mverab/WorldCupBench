"""
Leaderboard generator for WorldCupBench.

Reads all prediction JSONs from predictions/ and generates a Markdown
leaderboard showing model consensus on champions, finalists, and group winners.

Usage:
    python src/generate_leaderboard.py [--output leaderboard.md]

The output is designed to be injected into README.md between markers:
    <!-- LEADERBOARD:START -->
    ... generated table ...
    <!-- LEADERBOARD:END -->
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils  # noqa: E402


def load_all_predictions(predictions_dir: str = None) -> list:
    """Load all valid prediction JSONs from the pre-tournament predictions directory."""
    if predictions_dir is None:
        predictions_dir = os.path.join(utils.PREDICTIONS_DIR, "pre-tournament")
    predictions = []
    if not os.path.isdir(predictions_dir):
        return predictions

    for filename in sorted(os.listdir(predictions_dir)):
        if not filename.endswith("_prediction.json"):
            continue
        filepath = os.path.join(predictions_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            predictions.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return predictions


def build_consensus(predictions: list) -> dict:
    """Aggregate predictions into consensus statistics."""
    n = len(predictions)
    if n == 0:
        return {"count": 0}

    champions = Counter()
    runners_up = Counter()
    third_places = Counter()
    fourth_places = Counter()

    # Group winners
    group_winners = {chr(ord("A") + i): Counter() for i in range(12)}

    # Semi-finalists (teams that reach semi_finals)
    semi_finalists = Counter()

    for p in predictions:
        champions[p.get("champion", "?")] += 1
        runners_up[p.get("runner_up", "?")] += 1
        third_places[p.get("third", "?")] += 1
        fourth_places[p.get("fourth_place", "?")] += 1

        # Group winners
        gq = p.get("group_qualifiers", {})
        for team_info in gq.get("first_place", []):
            grp = team_info.get("group")
            code = team_info.get("team_code")
            if grp and code and grp in group_winners:
                group_winners[grp][code] += 1

        # Semi-finalists from bracket SF
        bracket = p.get("bracket", {})
        for match in bracket.get("SF", []):
            semi_finalists[match.get("home_team", "?")] += 1
            semi_finalists[match.get("away_team", "?")] += 1

    return {
        "count": n,
        "champion": champions.most_common(),
        "runner_up": runners_up.most_common(),
        "third_place": third_places.most_common(),
        "fourth_place": fourth_places.most_common(),
        "group_winners": {g: c.most_common() for g, c in group_winners.items()},
        "semi_finalists": semi_finalists.most_common(),
    }


def format_consensus_table(consensus: dict) -> str:
    """Format consensus data as a Markdown table."""
    n = consensus["count"]
    if n == 0:
        return "_No predictions available yet._"

    lines = []
    lines.append(f"### 🏆 Model Consensus ({n} models)")
    lines.append("")
    lines.append("| Position | Most Picked | Consensus |")
    lines.append("|----------|-------------|-----------|")

    def _pct(count: int, total: int) -> str:
        return f"{count}/{total} ({100 * count // total}%)"

    champ = consensus["champion"][0] if consensus["champion"] else ("?", 0)
    runner = consensus["runner_up"][0] if consensus["runner_up"] else ("?", 0)
    third = consensus["third_place"][0] if consensus["third_place"] else ("?", 0)
    fourth = consensus["fourth_place"][0] if consensus["fourth_place"] else ("?", 0)

    lines.append(f"| 🥇 Champion | {champ[0]} | {_pct(champ[1], n)} |")
    lines.append(f"| 🥈 Runner-up | {runner[0]} | {_pct(runner[1], n)} |")
    lines.append(f"| 🥉 Third Place | {third[0]} | {_pct(third[1], n)} |")
    lines.append(f"| 4th Place | {fourth[0]} | {_pct(fourth[1], n)} |")

    lines.append("")
    lines.append("### 🏅 Semi-Finalists")
    lines.append("")

    sf = consensus["semi_finalists"]
    if sf:
        sf_strs = [f"**{team}** {count}/{n}" for team, count in sf[:6]]
        lines.append(" | ".join(sf_strs))
    else:
        lines.append("_No semi-finalist data available._")

    lines.append("")
    lines.append("### 📊 Group Winners")
    lines.append("")
    lines.append("| Group | Winner Pick | Consensus |")
    lines.append("|-------|-------------|-----------|")

    for grp in sorted(consensus["group_winners"].keys()):
        winners = consensus["group_winners"][grp]
        if winners:
            top = winners[0]
            lines.append(f"| {grp} | {top[0]} | {_pct(top[1], n)} |")
        else:
            lines.append(f"| {grp} | — | — |")

    return "\n".join(lines)


def generate_leaderboard(predictions_dir: str = utils.PREDICTIONS_DIR) -> str:
    """Generate the full leaderboard Markdown."""
    predictions = load_all_predictions(predictions_dir)
    consensus = build_consensus(predictions)
    return format_consensus_table(consensus)


def update_readme(
    leaderboard_md: str,
    readme_path: str = "README.md",
    start_marker: str = "<!-- LEADERBOARD:START -->",
    end_marker: str = "<!-- LEADERBOARD:END -->",
):
    """Inject the leaderboard into README.md between markers."""
    if not os.path.exists(readme_path):
        print(f"README not found at {readme_path}")
        return False

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(f"Markers not found in {readme_path}. Skipping injection.")
        print("Add these markers to your README:")
        print(f"  {start_marker}")
        print(f"  {end_marker}")
        return False

    new_content = (
        content[: start_idx + len(start_marker)]
        + "\n\n"
        + leaderboard_md
        + "\n\n"
        + content[end_idx:]
    )

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Leaderboard injected into {readme_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate WorldCupBench leaderboard.")
    parser.add_argument(
        "--output",
        default=None,
        help="Write leaderboard to this file (default: stdout).",
    )
    parser.add_argument(
        "--inject-readme",
        action="store_true",
        help="Inject leaderboard into README.md between markers.",
    )
    args = parser.parse_args()

    leaderboard = generate_leaderboard()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(leaderboard)
        print(f"Leaderboard written to {args.output}")

    if args.inject_readme:
        update_readme(leaderboard)

    if not args.output and not args.inject_readme:
        print(leaderboard)


if __name__ == "__main__":
    main()
