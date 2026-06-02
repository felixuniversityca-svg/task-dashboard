#!/usr/bin/env python3
"""
fetch_dashboard_data.py
Fetches emails, deadlines, article pipeline, pending replies, and today's agenda.
Writes dashboard-data.json for build.py. Called by sync.sh before every commit.
"""
import json, re, subprocess, sys, warnings
warnings.filterwarnings("ignore")
from datetime import datetime, date, timedelta
from pathlib import Path

SCRIPTS     = Path.home() / "Documents/My Second Brain/.claude/scripts"
VAULT       = Path.home() / "Documents/My Second Brain"
AUTO_MEMORY = Path.home() / ".claude/projects/-Users-McGill-Documents-My-Second-Brain/memory"
sys.path.insert(0, str(SCRIPTS))
OUTPUT = Path(__file__).parent / "dashboard-data.json"

SKIP_SUBJECTS       = {"morning brief", "evening recap", "your 3 priorities"}
SKIP_FROM_FRAGMENTS = {"noreply", "no-reply", "mailer-daemon", "notifications@", "indeed"}


# ── Email ─────────────────────────────────────────────────────────────────────

def fetch_inbox_emails(max_results=10):
    results = []
    try:
        from google_auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        svc   = build("gmail", "v1", credentials=creds)
        resp  = svc.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=max_results, q="-from:me"
        ).execute()
        for m in resp.get("messages", []):
            msg = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()
            h       = {x["name"]: x["value"] for x in msg["payload"]["headers"]}
            subject = h.get("Subject", "(no subject)").strip()
            from_raw= h.get("From", "")
            ts      = int(msg.get("internalDate", 0)) // 1000
            if any(s in subject.lower() for s in SKIP_SUBJECTS): continue
            if any(f in from_raw.lower() for f in SKIP_FROM_FRAGMENTS): continue
            sender = (from_raw.split("<")[0].strip().strip('"') if "<" in from_raw
                      else from_raw.split("@")[0].replace(".", " ").title())
            results.append({
                "subject": subject, "from": sender, "epoch": ts,
                "unread": "UNREAD" in msg.get("labelIds", []),
                "snippet": msg.get("snippet", "")[:160]
            })
            if len(results) >= 3: break
    except Exception as e:
        print(f"  inbox error: {e}", file=sys.stderr)
    return results


# ── Deadlines ─────────────────────────────────────────────────────────────────

def read_deadlines():
    path = VAULT / "Memory/MEMORY.md"
    if not path.exists(): return []
    text = path.read_text(encoding="utf-8")
    in_sec, items = False, []
    for line in text.splitlines():
        if line.strip() == "## Active Deadlines":    in_sec = True;  continue
        if in_sec and line.startswith("## "):        break
        if in_sec and line.strip().startswith("- "):
            m = re.match(
                r"-\s+\[\d{4}-\d{2}-\d{2}\]\s+(\d{4}-\d{2}-\d{2})[T ]?(\d{2}:\d{2})?\s*[-–]\s*(.+)",
                line.strip())
            if m:
                items.append({"date": m.group(1), "time": m.group(2) or "", "title": m.group(3).strip()})
    return items


# ── Article pipeline ──────────────────────────────────────────────────────────

STAGE_ORDER = {"blocked": 0, "drafting": 1, "draft_ready": 2,
               "sent": 3, "awaiting": 4, "published": 5}

def classify_stage(desc):
    d = desc.lower()
    if "sent ✅" in desc or "published" in d:              return "published"
    if "awaiting reply" in d or "awaiting feedback" in d \
       or "awaiting confirmation" in d:                        return "awaiting"
    if "sent to" in d or "envoy" in d:                        return "sent"
    if "drafted" in d or "pending review" in d:               return "draft_ready"
    if "blocked" in d or "v.1 pending" in d:                  return "blocked"
    return "drafting"

STAGE_LABELS = {
    "blocked":    "Blocked",
    "drafting":   "Drafting",
    "draft_ready":"Draft ready",
    "sent":       "Sent",
    "awaiting":   "Awaiting reply",
    "published":  "Published"
}
STAGE_COLORS = {
    "blocked":    "#ff3b30",
    "drafting":   "#aeaeb2",
    "draft_ready":"#0071e3",
    "sent":       "#af52de",
    "awaiting":   "#ff9500",
    "published":  "#34c759"
}

def parse_article_pipeline():
    mem = AUTO_MEMORY / "MEMORY.md"
    if not mem.exists(): return []
    articles = []
    for line in mem.read_text(encoding="utf-8").splitlines():
        if "Article Status" not in line: continue
        m = re.match(r"-\s+\[([^\]]+)\]\([^\)]+\):\s+(.+)", line)
        if not m: continue
        full_name = m.group(1)
        desc      = m.group(2).strip()
        name = (full_name.replace(" Article Status","").replace(" Status","").strip())
        # Skip non-partner entries
        if name in ("InvestSud Article Filing Convention","InvestSud Article Subheadings"): continue
        stage = classify_stage(desc)
        # Extract contact waiting on
        contact = ""
        cm = re.search(r"(?:to|from|sent to)\s+([A-Z][a-z]+(?:-[A-Z][a-z]+)?(?:\s[A-Z][a-z]+)?)", desc)
        if cm: contact = cm.group(1)
        # Extract sent date
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", desc)
        sent_date = dm.group(1) if dm else ""
        days_ago = ""
        if sent_date:
            try:
                d = datetime.strptime(sent_date, "%Y-%m-%d").date()
                days_ago = str((date.today() - d).days)
            except: pass
        articles.append({
            "name": name, "stage": stage,
            "label": STAGE_LABELS[stage],
            "color": STAGE_COLORS[stage],
            "contact": contact, "sent_date": sent_date,
            "days_ago": days_ago, "desc": desc[:100]
        })
    articles.sort(key=lambda x: STAGE_ORDER.get(x["stage"], 9))
    return articles


# ── Pending replies ───────────────────────────────────────────────────────────

def parse_pending_replies():
    articles = parse_article_pipeline()
    replies  = []
    for a in articles:
        if a["stage"] in ("awaiting", "blocked") and a["contact"]:
            label = f"{a['days_ago']}d" if a["days_ago"] else ""
            replies.append({
                "item":       a["name"],
                "waiting_on": a["contact"],
                "since":      a["sent_date"],
                "days":       a["days_ago"],
                "label":      label,
                "desc":       a["desc"][:80]
            })
    return replies


# ── Today's agenda ────────────────────────────────────────────────────────────

def fetch_today_agenda():
    """Try Apple Calendar via AppleScript, fall back to today's deadlines."""
    script = r"""
tell application "Calendar"
  set out to {}
  set td to (current date)
  set time of td to 0
  set te to td + 86399
  repeat with c in (every calendar)
    try
      set evs to every event of c whose start date >= td and start date <= te
      repeat with e in evs
        set st to start date of e
        set hh to text -2 thru -1 of ("0" & ((hours of st) as string))
        set mm to text -2 thru -1 of ("0" & ((minutes of st) as string))
        copy ((summary of e) & "@@" & hh & ":" & mm) to end of out
      end repeat
    end try
  end repeat
  out
end tell
"""
    events = []
    try:
        res = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=8)
        if res.returncode == 0 and res.stdout.strip():
            for chunk in res.stdout.split(","):
                chunk = chunk.strip()
                if "@@" in chunk:
                    title, time_str = chunk.split("@@", 1)
                    events.append({"title": title.strip(), "time": time_str.strip()})
    except Exception as e:
        print(f"  calendar error: {e}", file=sys.stderr)

    # Fallback: today's deadlines from vault
    if not events:
        today_str = date.today().isoformat()
        for dl in read_deadlines():
            if dl["date"] == today_str:
                t = dl.get("time", "")
                events.append({"title": dl["title"], "time": t})

    return sorted(events, key=lambda x: x.get("time", ""))


# ── Vault graph ──────────────────────────────────────────────────────────────

FOLDER_COLORS = {
    "Identity":         "#af52de",
    "Knowledge":        "#34c759",
    "Work & Projects":  "#0071e3",
    "People":           "#ff9500",
    "Career & Identity":"#ff9500",
    "Communications":   "#32ade6",
    "Memory":           "#aeaeb2",
    "Archive":          "#636366",
    "Resources":        "#636366",
    ".claude":          "#636366",
}

def parse_vault_graph():
    md_files = list(VAULT.rglob("*.md"))
    # Build name → file mapping (case-insensitive, stem only)
    name_map = {}
    for f in md_files:
        name_map[f.stem.lower()] = f

    nodes, links = [], []
    node_ids = {}  # path → index

    for f in md_files:
        rel = f.relative_to(VAULT)
        folder = rel.parts[0] if len(rel.parts) > 1 else "root"
        color = FOLDER_COLORS.get(folder, "#aeaeb2")
        nid = str(rel)
        if nid not in node_ids:
            node_ids[nid] = len(nodes)
            nodes.append({"id": nid, "name": f.stem, "folder": folder, "color": color})

    for f in md_files:
        src_id = str(f.relative_to(VAULT))
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for raw in re.findall(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]", text):
            target_key = raw.strip().lower()
            # Try exact stem match
            target_file = name_map.get(target_key)
            if not target_file:
                # Try matching just the last part (e.g. "Folder/Note" → "Note")
                target_file = name_map.get(target_key.split("/")[-1])
            if target_file:
                tgt_id = str(target_file.relative_to(VAULT))
                if src_id != tgt_id and src_id in node_ids and tgt_id in node_ids:
                    links.append({"source": src_id, "target": tgt_id})

    # Deduplicate links
    seen = set()
    unique_links = []
    for l in links:
        key = (l["source"], l["target"])
        rev = (l["target"], l["source"])
        if key not in seen and rev not in seen:
            seen.add(key)
            unique_links.append(l)

    return {"nodes": nodes, "links": unique_links}


# ── Claude usage ─────────────────────────────────────────────────────────────

def read_claude_usage():
    p = Path.home() / ".claude/data/claude_usage.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("  fetching inbox...",           file=sys.stderr)
    emails    = fetch_inbox_emails()
    print("  reading deadlines...",        file=sys.stderr)
    deadlines = sorted(read_deadlines(), key=lambda d: (d.get("date", ""), d.get("time", "") or "99:99"))
    print("  parsing article pipeline...", file=sys.stderr)
    pipeline  = parse_article_pipeline()
    print("  parsing pending replies...",  file=sys.stderr)
    replies   = parse_pending_replies()
    print("  fetching today's agenda...",  file=sys.stderr)
    agenda    = fetch_today_agenda()
    print("  reading claude usage...",     file=sys.stderr)
    claude_usage = read_claude_usage()
    print("  parsing vault graph...",      file=sys.stderr)
    vault_graph  = parse_vault_graph()

    data = {
        "emails":       emails,
        "deadlines":    deadlines,
        "pipeline":     pipeline,
        "replies":      replies,
        "agenda":       agenda,
        "claude_usage": claude_usage,
        "vault_graph":  vault_graph,
        "fetched_at":   datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  done: {len(emails)} emails, {len(pipeline)} articles, "
          f"{len(replies)} pending replies, {len(agenda)} agenda items")


if __name__ == "__main__":
    main()
