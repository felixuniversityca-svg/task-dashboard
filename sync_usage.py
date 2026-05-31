#!/usr/bin/env python3
"""
sync_usage.py — fast-path sync for Claude session usage.
Reads ~/.claude/data/claude_usage.json, writes docs/usage.json,
commits and pushes only when the percentage value changed.
Runs every 5 minutes via launchd.
"""
import json, subprocess, sys
from pathlib import Path

REPO   = Path.home() / "task-dashboard"
SOURCE = Path.home() / ".claude/data/claude_usage.json"
DEST   = REPO / "docs/usage.json"


def main():
    if not SOURCE.exists():
        print("No usage data yet — statusline hasn't written it")
        return

    try:
        new_data = json.loads(SOURCE.read_text())
    except Exception as e:
        print(f"Error reading source: {e}"); return

    new_pct = new_data.get("five_hour_pct")

    # Skip push if percentage hasn't changed
    if DEST.exists():
        try:
            old_pct = json.loads(DEST.read_text()).get("five_hour_pct")
            if old_pct == new_pct:
                print(f"No change ({new_pct}% used), skipping"); return
        except Exception:
            pass

    DEST.write_text(json.dumps(new_data))

    subprocess.run(["git", "-C", str(REPO), "add", "docs/usage.json"],
                   capture_output=True)

    diff = subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"],
                          capture_output=True)
    if diff.returncode == 0:
        print("No git change after add"); return

    subprocess.run(
        ["git", "-C", str(REPO), "commit", "-m", f"usage: {new_pct}% used"],
        capture_output=True
    )
    push = subprocess.run(["git", "-C", str(REPO), "push"],
                          capture_output=True, text=True)
    if push.returncode == 0:
        print(f"Pushed: {new_pct}% used")
    else:
        print(f"Push failed: {push.stderr.strip()}")


if __name__ == "__main__":
    main()
