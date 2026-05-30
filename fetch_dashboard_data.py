#!/usr/bin/env python3
"""
fetch_dashboard_data.py
Fetches recent inbox emails and upcoming deadlines from the vault.
Writes dashboard-data.json for build.py. Called by sync.sh before every commit.
"""
import json
import re
import sys
import warnings
warnings.filterwarnings("ignore")
from datetime import datetime
from pathlib import Path

SCRIPTS = Path.home() / "Documents/My Second Brain/.claude/scripts"
VAULT   = Path.home() / "Documents/My Second Brain"
sys.path.insert(0, str(SCRIPTS))
OUTPUT = Path(__file__).parent / "dashboard-data.json"

# Skip emails that are automated system messages
SKIP_SUBJECTS = {"morning brief", "evening recap", "your 3 priorities"}
SKIP_FROM_FRAGMENTS = {"noreply", "no-reply", "mailer-daemon", "notifications@"}


def fetch_inbox_emails(max_results=10):
    results = []
    try:
        from google_auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        svc = build("gmail", "v1", credentials=creds)
        resp = svc.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=max_results,
            q="-from:me"
        ).execute()
        for m in resp.get("messages", []):
            msg = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()
            h = {x["name"]: x["value"] for x in msg["payload"]["headers"]}
            subject = h.get("Subject", "(no subject)").strip()
            from_raw = h.get("From", "")
            ts = int(msg.get("internalDate", 0)) // 1000

            if any(s in subject.lower() for s in SKIP_SUBJECTS):
                continue
            if any(f in from_raw.lower() for f in SKIP_FROM_FRAGMENTS):
                continue

            # Extract sender name
            if "<" in from_raw:
                sender = from_raw.split("<")[0].strip().strip('"')
            else:
                sender = from_raw.split("@")[0].replace(".", " ").title()

            is_unread = "UNREAD" in msg.get("labelIds", [])
            results.append({
                "subject": subject,
                "from": sender,
                "epoch": ts,
                "unread": is_unread
            })
            if len(results) >= 5:
                break
    except Exception as e:
        print(f"  inbox error: {e}", file=sys.stderr)
    return results


def read_deadlines():
    """Parse upcoming deadlines from vault MEMORY.md Active Deadlines section."""
    path = VAULT / "Memory/MEMORY.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    in_section = False
    items = []
    for line in text.splitlines():
        if line.strip() == "## Active Deadlines":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.strip().startswith("- "):
            # Format: - [DATE] YYYY-MM-DD HH:MM - Description
            m = re.match(r"-\s+\[\d{4}-\d{2}-\d{2}\]\s+(\d{4}-\d{2}-\d{2})[T ]?(\d{2}:\d{2})?\s*[-–]\s*(.+)", line.strip())
            if m:
                date_str = m.group(1)
                time_str = m.group(2) or ""
                desc = m.group(3).strip()
                items.append({
                    "date": date_str,
                    "time": time_str,
                    "title": desc
                })
    return items


def main():
    print("  fetching inbox...", file=sys.stderr)
    emails = fetch_inbox_emails()
    print("  reading vault deadlines...", file=sys.stderr)
    deadlines = read_deadlines()

    data = {
        "emails": emails,
        "deadlines": deadlines,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    OUTPUT.write_text(json.dumps(data, indent=2))
    print(f"  done: {len(emails)} emails, {len(deadlines)} deadlines")


if __name__ == "__main__":
    main()
