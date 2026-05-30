#!/bin/bash
# sync.sh -- triggered by launchd WatchPaths when Tasks.md changes
# one-shot: brctl guard, copy, fetch live data, commit, push, exit

TASKS="$HOME/Documents/My Second Brain/Work & Projects/Tasks.md"
REPO="$HOME/task-dashboard"

log() { echo "[sync $(date '+%H:%M:%S')] $*"; }

# brctl guard: wait until iCloud is done syncing Tasks.md before reading it
wait_for_icloud() {
    local waited=0
    while brctl status 2>/dev/null | grep -qF "Tasks.md"; do
        if [ "$waited" -ge 30 ]; then
            log "iCloud guard timeout after 30s, proceeding anyway"
            return
        fi
        sleep 2
        waited=$((waited + 2))
    done
}

wait_for_icloud
cp "$TASKS" "$REPO/Tasks.md"

# Fetch live data (emails, calendar) -- non-blocking, fails gracefully
log "fetching live data..."
/opt/homebrew/bin/python3.12 "$REPO/fetch_dashboard_data.py" 2>&1 | while IFS= read -r line; do log "$line"; done

cd "$REPO" || exit 1
git add Tasks.md dashboard-data.json
if ! git diff --cached --quiet; then
    git commit -m "sync $(date '+%Y-%m-%d %H:%M')" && \
        git push && log "pushed" || log "push failed -- check remote"
else
    log "no changes"
fi
