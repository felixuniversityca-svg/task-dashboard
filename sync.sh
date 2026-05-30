#!/bin/bash
# sync.sh -- watches Tasks.md, copies to repo, commits, pushes
# Requires: brew install fswatch
# Run via launchd (see com.felix.taskdashboard.plist)

TASKS="$HOME/Documents/My Second Brain/Work & Projects/Tasks.md"
REPO="$HOME/task-dashboard"
FSWATCH="/opt/homebrew/bin/fswatch"

if [ ! -f "$FSWATCH" ]; then
  echo "fswatch not found at $FSWATCH. Run: brew install fswatch" >&2
  exit 1
fi

echo "[sync] watching $TASKS"

"$FSWATCH" -o "$TASKS" | while read; do
  sleep 1  # wait for Obsidian non-atomic write to complete
  cp "$TASKS" "$REPO/Tasks.md"
  cd "$REPO" || exit 1
  git add Tasks.md
  # Only commit if there are actual changes
  if ! git diff --cached --quiet; then
    git commit -m "tasks $(date '+%Y-%m-%d %H:%M')"
    git push && echo "[sync] pushed at $(date '+%H:%M')"
  fi
done
