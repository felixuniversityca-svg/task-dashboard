#!/bin/bash
# sync.sh -- triggered by launchd WatchPaths when Tasks.md changes
# Builds locally, commits public/index.html + Tasks.md, pushes to GitHub.
# GitHub Pages serves public/index.html directly -- no cloud build step.
# 5-min debounce prevents flooding GitHub with commits during rapid edits.

TASKS="$HOME/Documents/My Second Brain/Work & Projects/Tasks.md"
REPO="$HOME/task-dashboard"
COOLDOWN_FILE="$HOME/.claude/data/last_dashboard_push.txt"
COOLDOWN=300  # 5 minutes

log() { echo "[sync $(date '+%H:%M:%S')] $*"; }

# ── Debounce: wait out remaining cooldown before proceeding ──────────────────
if [ -f "$COOLDOWN_FILE" ]; then
    last=$(cat "$COOLDOWN_FILE")
    now=$(date +%s)
    elapsed=$((now - last))
    if [ "$elapsed" -lt "$COOLDOWN" ]; then
        wait_time=$((COOLDOWN - elapsed))
        log "cooldown: waiting ${wait_time}s..."
        sleep "$wait_time"
    fi
fi

# ── iCloud guard: wait until iCloud finishes syncing Tasks.md ────────────────
wait_for_icloud() {
    local waited=0
    while brctl status 2>/dev/null | grep -qF "Tasks.md"; do
        if [ "$waited" -ge 30 ]; then
            log "iCloud guard timeout, proceeding anyway"
            return
        fi
        sleep 2
        waited=$((waited + 2))
    done
}
wait_for_icloud
cp "$TASKS" "$REPO/Tasks.md"

# ── Fetch live data (emails, calendar) ───────────────────────────────────────
log "fetching live data..."
/opt/homebrew/bin/python3.12 "$REPO/fetch_dashboard_data.py" 2>&1 | while IFS= read -r line; do log "$line"; done

# ── Build HTML locally ────────────────────────────────────────────────────────
log "building..."
/opt/homebrew/bin/python3.12 "$REPO/build.py" 2>&1 | while IFS= read -r line; do log "$line"; done

# ── Commit and push ───────────────────────────────────────────────────────────
cd "$REPO" || exit 1
git add Tasks.md docs/index.html public/index.html
if ! git diff --cached --quiet; then
    git commit -m "sync $(date '+%Y-%m-%d %H:%M')" && \
        git push && \
        mkdir -p "$(dirname "$COOLDOWN_FILE")" && date +%s > "$COOLDOWN_FILE" && \
        log "pushed" || log "push failed -- check remote"
else
    log "no changes"
fi
