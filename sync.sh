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

# ── Build HTML directly from vault (fetch runs separately via fetch.sh) ──────
log "building..."
if ! /opt/homebrew/bin/python3.12 "$REPO/build.py" "$TASKS" 2>&1 | while IFS= read -r line; do log "$line"; done; then
    log "build failed or Tasks.md too small -- aborting push"
    exit 1
fi

# ── Post-build validation ─────────────────────────────────────────────────────
HTML="$REPO/docs/index.html"
fail=0

# 1. CC counter must not show calendar-day value (80d = 80 calendar days to Aug 22)
if grep -q '80d left' "$HTML"; then
    log "VALIDATION FAIL: dashboard shows '80d left' — JS is overriding Python working-day count"
    fail=1
fi

# 2. Warn if any [x] checked tasks are still in ## Active (should be in ## Completed)
stale_checked=$(python3 -c "
import re
txt = open('$TASKS').read()
active = re.search(r'## Active(.*?)(?=## Awaiting|## Blocked|## Completed|\Z)', txt, re.S)
if active:
    hits = re.findall(r'^- \[x\].+', active.group(1), re.M)
    for h in hits: print(h[:80])
" 2>/dev/null)
if [ -n "$stale_checked" ]; then
    log "WARNING: checked [x] tasks found in ## Active — move them to ## Completed:"
    echo "$stale_checked" | while IFS= read -r line; do log "  $line"; done
fi

# 3. No item should appear twice in the agenda section (adjacent duplicate titles)
dupes=$(python3 -c "
import re, sys
html = open('$HTML').read()
m = re.search(r'id=\"dc-outer\".*?</div>', html, re.S)
if not m: sys.exit(0)
titles = re.findall(r'class=\"dc-ev-n\"[^>]*>([^<]+)<', html)
seen = set()
for t in titles:
    if t.strip().lower() in seen:
        print('DUPLICATE:', t.strip())
    seen.add(t.strip().lower())
" 2>/dev/null)
if [ -n "$dupes" ]; then
    log "VALIDATION FAIL: duplicate agenda items detected: $dupes"
    fail=1
fi

# 3. Credentials.md stub check — warn if still empty (non-blocking)
if grep -q '\[À RENSEIGNER\]' "$HOME/Documents/My Second Brain/Work & Projects/Internships/Capital Croissance/AI Mandate/Credentials.md" 2>/dev/null; then
    log "WARNING: Credentials.md still has unfilled slots"
fi

if [ "$fail" -eq 1 ]; then
    log "Validation failed — aborting push. Fix the issues above."
    exit 1
fi

# ── Commit and push ───────────────────────────────────────────────────────────
cd "$REPO" || exit 1
git add docs/index.html
if ! git diff --cached --quiet; then
    if git commit -m "sync $(date '+%Y-%m-%d %H:%M')" && git push; then
        mkdir -p "$(dirname "$COOLDOWN_FILE")" && date +%s > "$COOLDOWN_FILE"
        log "pushed"
    else
        log "push failed -- check ~/task-dashboard/sync-error.log"
    fi
else
    log "no changes"
fi
