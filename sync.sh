#!/bin/bash
# sync.sh -- triggered by launchd WatchPaths when Tasks.md changes
# one-shot: brctl guard, copy, commit, push, exit

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
cd "$REPO" || exit 1
git add Tasks.md
if ! git diff --cached --quiet; then
    git commit -m "tasks $(date '+%Y-%m-%d %H:%M')" && \
        git push && log "pushed" || log "push failed -- check remote"
else
    log "no changes"
fi
