#!/bin/bash
# fetch.sh — runs fetch_dashboard_data.py only (atomic write to dashboard-data.json).
# Called by com.felix.dashboardfetch.plist every 45 min.
# When cache.json updates, com.felix.taskdashboard.plist WatchPaths triggers build.

REPO="$HOME/task-dashboard"
log() { echo "[fetch $(date '+%H:%M:%S')] $*"; }

log "fetching live data..."
if /opt/homebrew/bin/python3.12 "$REPO/fetch_dashboard_data.py" 2>&1 | while IFS= read -r line; do log "$line"; done; then
    log "done"
else
    log "fetch failed — last-good cache preserved"
fi
