#!/usr/bin/env python3
"""
build.py -- reads Tasks.md, generates public/index.html
Run locally: python3 build.py
Netlify build command: python3 build.py
"""
import re
import sys
from pathlib import Path
from html import escape
from datetime import datetime, date

TASKS_FILE = Path(__file__).parent / "Tasks.md"
OUTPUT_DIR = Path(__file__).parent / "public"
OUTPUT_FILE = OUTPUT_DIR / "index.html"


def strip_wikilink(text):
    def replace(m):
        inner = m.group(1)
        return inner.split("|", 1)[1] if "|" in inner else inner
    return re.sub(r"\[\[([^\]]+)\]\]", replace, text)


def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def days_ago(d):
    return (date.today() - d).days if d else None


def parse_tasks(content):
    active = []
    blocked = []
    completed = []
    current_section = None
    current_subsection = None
    current_subsection_tasks = []

    def flush_subsection():
        if current_subsection is not None and current_subsection_tasks:
            active.append({"section": current_subsection, "tasks": current_subsection_tasks[:]})

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "## Active":
            current_section = "active"; current_subsection = None; current_subsection_tasks = []; continue
        if stripped == "## Blocked":
            flush_subsection(); current_subsection = None; current_section = "blocked"; continue
        if stripped == "## Completed":
            flush_subsection(); current_subsection = None; current_section = "completed"; continue
        if stripped.startswith("## "):
            flush_subsection(); current_section = None; continue
        if stripped.startswith("<!--") or stripped == "---" or not stripped:
            continue
        if current_section == "active" and stripped.startswith("### "):
            flush_subsection()
            current_subsection = strip_wikilink(stripped[4:].strip())
            current_subsection_tasks = []; continue
        if current_section == "active" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            created = None
            m = re.search(r"<!--\s*created:\s*(\d{4}-\d{2}-\d{2})\s*-->", task_text)
            if m:
                created = parse_date(m.group(1)); task_text = task_text[:m.start()].strip()
            task_text = strip_wikilink(task_text)
            if current_subsection is None:
                current_subsection = "Other"; current_subsection_tasks = []
            current_subsection_tasks.append({"text": task_text, "created": created}); continue
        if current_section == "blocked" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting = ""; since = ""
            m = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$", task_text)
            if m:
                task_text = m.group(1).strip(); waiting = m.group(2).strip(); since = m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", task_text)
                if m2:
                    task_text = m2.group(1).strip(); waiting = m2.group(2).strip()
            since_date = parse_date(since)
            days = days_ago(since_date)
            blocked.append({"task": strip_wikilink(task_text), "waiting": waiting, "since": since, "since_date": since_date, "days_blocked": days}); continue
        if current_section == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            task_text = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            date_str = ""
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", task_text)
            if m:
                date_str = m.group(1); task_text = task_text[:m.start()].strip()
            completed.append({"task": strip_wikilink(task_text), "date": date_str}); continue

    flush_subsection()
    return active, blocked, completed


def build_html(active, blocked, completed):
    total_active = sum(len(s["tasks"]) for s in active)
    total_blocked = len(blocked)
    total_done = len(completed)
    now = datetime.now()
    updated_time = now.strftime("%H:%M")
    updated_date = now.strftime("%b %-d")

    # Active cards
    active_html = ""
    for section in active:
        if not section["tasks"]:
            continue
        count = len(section["tasks"])
        tasks_html = "".join(
            f'<li class="task-row">'
            f'<span class="task-pip"></span>'
            f'<span class="task-text">{escape(t["text"])}</span>'
            f'</li>'
            for t in section["tasks"]
        )
        active_html += (
            f'<div class="card active-card">'
            f'<div class="card-head">'
            f'<span class="card-title">{escape(section["section"])}</span>'
            f'<span class="pill pill-count">{count}</span>'
            f'</div>'
            f'<ul class="task-list">{tasks_html}</ul>'
            f'</div>'
        )
    if not active_html:
        active_html = '<p class="empty">Nothing active. Clear runway.</p>'

    # Blocked cards -- oldest first
    blocked_sorted = sorted(blocked, key=lambda x: x["days_blocked"] or 0, reverse=True)
    blocked_html = ""
    for item in blocked_sorted:
        days = item["days_blocked"]
        pill = ""
        extra_cls = ""
        if days is not None and days >= 14:
            pill = f'<span class="pill pill-crit">{days}d</span>'
            extra_cls = "card-crit"
        elif days is not None and days >= 3:
            pill = f'<span class="pill pill-warn">{days}d</span>'
            extra_cls = "card-warn"
        elif days is not None and days > 0:
            pill = f'<span class="pill pill-neutral">{days}d</span>'

        waiting_html = (
            f'<div class="waiting">Waiting on {escape(item["waiting"])}</div>'
            if item["waiting"] else ""
        )
        blocked_html += (
            f'<div class="card blocked-card {extra_cls}">'
            f'<div class="card-head">'
            f'<span class="blocked-pip"></span>'
            f'<span class="task-text" style="flex:1">{escape(item["task"])}</span>'
            f'{pill}'
            f'</div>'
            f'{waiting_html}'
            f'</div>'
        )
    if not blocked_html:
        blocked_html = '<p class="empty">Nothing blocked.</p>'

    # Completed
    completed_html = ""
    for item in reversed(completed):
        date_html = f'<span class="done-date">{escape(item["date"])}</span>' if item["date"] else ""
        completed_html += (
            f'<li class="done-row">'
            f'<span class="check">&#10003;</span>'
            f'<span class="done-text">{escape(item["task"])}</span>'
            f'{date_html}'
            f'</li>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Felix — Tasks</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #0d1117;
      --bg2:       #13182a;
      --surface:   #161d2f;
      --surface2:  #1c2540;
      --border:    rgba(255,255,255,0.07);
      --border2:   rgba(255,255,255,0.12);
      --text:      #e8edf5;
      --muted:     #6b7a99;
      --subtle:    #3d4d6e;
      --green:     #34d399;
      --green-bg:  rgba(52,211,153,0.10);
      --green-bdr: rgba(52,211,153,0.25);
      --amber:     #fbbf24;
      --amber-bg:  rgba(251,191,36,0.10);
      --amber-bdr: rgba(251,191,36,0.25);
      --red:       #f87171;
      --red-bg:    rgba(248,113,113,0.10);
      --red-bdr:   rgba(248,113,113,0.25);
      --done-col:  #3d4d6e;
      --radius:    14px;
      --radius-sm: 8px;
    }}

    html {{ background: var(--bg); }}

    body {{
      font-family: 'Inter', -apple-system, sans-serif;
      background:
        radial-gradient(ellipse 80% 40% at 50% -10%, rgba(99,102,241,0.12) 0%, transparent 70%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 36px 20px 60px;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{ max-width: 680px; margin: 0 auto; }}

    /* Header */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 36px;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .header-left {{ display: flex; align-items: center; gap: 14px; }}
    .avatar {{
      width: 40px; height: 40px; border-radius: 12px;
      background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
      display: flex; align-items: center; justify-content: center;
      font-size: 15px; font-weight: 700; color: #fff; flex-shrink: 0;
      box-shadow: 0 0 0 1px rgba(255,255,255,0.08), 0 4px 12px rgba(99,102,241,0.3);
    }}
    .header-title {{ font-size: 18px; font-weight: 700; letter-spacing: -0.4px; }}
    .header-sub {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}

    /* Stat chips */
    .stats {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .chip {{
      display: flex; align-items: center; gap: 7px;
      padding: 6px 14px; border-radius: 20px;
      font-size: 12px; font-weight: 600;
      background: var(--surface); border: 1px solid var(--border2);
      letter-spacing: 0.1px;
    }}
    .chip-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
    .chip-active {{ color: var(--green); border-color: var(--green-bdr); background: var(--green-bg); }}
    .chip-active .chip-dot {{ background: var(--green); box-shadow: 0 0 6px var(--green); }}
    .chip-blocked {{ color: var(--amber); border-color: var(--amber-bdr); background: var(--amber-bg); }}
    .chip-blocked .chip-dot {{ background: var(--amber); }}
    .chip-done {{ color: var(--muted); }}
    .chip-done .chip-dot {{ background: var(--done-col); }}

    /* Section label */
    .section-label {{
      font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
      text-transform: uppercase; color: var(--subtle);
      margin-bottom: 12px; padding-left: 2px;
    }}

    section {{ margin-bottom: 32px; }}

    /* Cards */
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 18px 20px;
      margin-bottom: 10px;
      transition: border-color 0.15s;
    }}
    .card:hover {{ border-color: var(--border2); }}

    .active-card {{ border-left: 2px solid var(--green); }}
    .blocked-card {{ border-left: 2px solid var(--amber); background: rgba(251,191,36,0.03); }}
    .card-warn {{ border-left-color: var(--amber); }}
    .card-crit {{ border-left: 2px solid var(--red); background: var(--red-bg); }}

    .card-head {{
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 14px;
    }}
    .card-head:last-child {{ margin-bottom: 0; }}

    .card-title {{
      font-size: 12px; font-weight: 600;
      color: var(--muted); text-transform: uppercase;
      letter-spacing: 0.6px; flex: 1;
    }}

    /* Pills */
    .pill {{
      font-size: 11px; font-weight: 700;
      border-radius: 6px; padding: 2px 8px;
      flex-shrink: 0;
    }}
    .pill-count {{ background: var(--surface2); color: var(--muted); border: 1px solid var(--border); }}
    .pill-neutral {{ background: var(--surface2); color: var(--muted); border: 1px solid var(--border); }}
    .pill-warn {{ background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-bdr); }}
    .pill-crit {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red-bdr); }}

    /* Task rows */
    .task-list {{ list-style: none; display: flex; flex-direction: column; gap: 10px; }}
    .task-row {{ display: flex; align-items: flex-start; gap: 12px; }}
    .task-pip {{
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--green); margin-top: 7px; flex-shrink: 0;
      box-shadow: 0 0 5px rgba(52,211,153,0.4);
    }}
    .task-text {{ font-size: 14px; line-height: 1.55; color: var(--text); }}

    /* Blocked pip */
    .blocked-pip {{
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--amber); flex-shrink: 0; margin-top: 2px;
    }}
    .card-crit .blocked-pip {{ background: var(--red); }}

    .waiting {{
      font-size: 12px; color: var(--muted);
      margin-top: 8px; padding-top: 8px;
      border-top: 1px solid var(--border);
    }}
    .waiting strong {{ color: var(--amber); font-weight: 600; }}
    .card-crit .waiting strong {{ color: var(--red); }}

    /* Completed */
    details {{ }}
    summary {{
      cursor: pointer; user-select: none; list-style: none;
      display: flex; align-items: center; gap: 8px;
      font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
      text-transform: uppercase; color: var(--subtle);
      margin-bottom: 12px; padding-left: 2px;
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::after {{
      content: ''; display: inline-block;
      width: 0; height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-top: 5px solid var(--subtle);
      transition: transform 0.15s;
    }}
    details[open] summary::after {{ transform: rotate(180deg); }}

    .done-list {{ list-style: none; display: flex; flex-direction: column; gap: 6px; }}
    .done-row {{
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }}
    .check {{ color: var(--done-col); font-size: 12px; flex-shrink: 0; }}
    .done-text {{ font-size: 13px; color: var(--done-col); text-decoration: line-through; flex: 1; }}
    .done-date {{ font-size: 11px; color: var(--subtle); white-space: nowrap; flex-shrink: 0; }}

    .empty {{ font-size: 13px; color: var(--muted); font-style: italic; padding: 4px 2px; }}

    /* Footer */
    footer {{
      margin-top: 48px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .footer-name {{ font-size: 12px; font-weight: 600; color: var(--subtle); }}
    .footer-time {{ font-size: 11px; color: var(--subtle); }}

    @media (max-width: 480px) {{
      body {{ padding: 24px 16px 48px; }}
      .header-title {{ font-size: 16px; }}
      .task-text {{ font-size: 13px; }}
      .chip {{ padding: 5px 11px; font-size: 11px; }}
    }}
  </style>
</head>
<body>
  <div class="container">

    <div class="header">
      <div class="header-left">
        <div class="avatar">F</div>
        <div>
          <div class="header-title">Felix — Tasks</div>
          <div class="header-sub">Second Brain</div>
        </div>
      </div>
      <div class="stats">
        <div class="chip chip-active"><span class="chip-dot"></span>{total_active} active</div>
        <div class="chip chip-blocked"><span class="chip-dot"></span>{total_blocked} blocked</div>
        <div class="chip chip-done"><span class="chip-dot"></span>{total_done} done</div>
      </div>
    </div>

    <section>
      <div class="section-label">Active</div>
      {active_html}
    </section>

    <section>
      <div class="section-label">Blocked</div>
      {blocked_html}
    </section>

    <section>
      <details>
        <summary>Completed &nbsp;({total_done})</summary>
        <ul class="done-list">{completed_html}</ul>
      </details>
    </section>

    <footer>
      <span class="footer-name">felix.janssen</span>
      <span class="footer-time">Updated {updated_date} at {updated_time}</span>
    </footer>

  </div>
</body>
</html>"""


def main():
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks.md not found at {TASKS_FILE}", file=sys.stderr)
        sys.exit(1)
    content = TASKS_FILE.read_text(encoding="utf-8")
    active, blocked, completed = parse_tasks(content)
    OUTPUT_DIR.mkdir(exist_ok=True)
    html = build_html(active, blocked, completed)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Built: {OUTPUT_FILE}")
    print(f"  {sum(len(s['tasks']) for s in active)} active  |  {len(blocked)} blocked  |  {len(completed)} done")
    for b in blocked:
        days = b["days_blocked"]
        flag = f" [{days}d]" if days else ""
        print(f"  [BLOCKED{flag}] {b['task']}")


if __name__ == "__main__":
    main()
