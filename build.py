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
from datetime import datetime

TASKS_FILE = Path(__file__).parent / "Tasks.md"
OUTPUT_DIR = Path(__file__).parent / "public"
OUTPUT_FILE = OUTPUT_DIR / "index.html"


def strip_wikilink(text):
    """[[Link|Display]] -> Display, [[Link]] -> Link"""
    def replace(m):
        inner = m.group(1)
        if "|" in inner:
            return inner.split("|", 1)[1]
        return inner
    return re.sub(r"\[\[([^\]]+)\]\]", replace, text)


def parse_tasks(content):
    """
    Returns:
      active    = [{'section': str, 'tasks': [str]}]
      blocked   = [{'task': str, 'waiting': str, 'since': str}]
      completed = [{'task': str, 'date': str}]

    Defensive: unknown lines pass through silently, never crashes.
    """
    active = []
    blocked = []
    completed = []

    current_section = None
    current_subsection = None
    current_subsection_tasks = []

    def flush_subsection():
        if current_subsection is not None and current_subsection_tasks:
            active.append({
                "section": current_subsection,
                "tasks": current_subsection_tasks[:]
            })

    for line in content.splitlines():
        stripped = line.strip()

        # Top-level section boundaries
        if stripped == "## Active":
            current_section = "active"
            current_subsection = None
            current_subsection_tasks = []
            continue
        if stripped == "## Blocked":
            flush_subsection()
            current_subsection = None
            current_section = "blocked"
            continue
        if stripped == "## Completed":
            flush_subsection()
            current_subsection = None
            current_section = "completed"
            continue
        if stripped.startswith("## "):
            # Any other top-level section (Liens, etc.) -- stop
            flush_subsection()
            current_section = None
            continue

        # Skip comments and horizontal rules
        if stripped.startswith("<!--") or stripped == "---" or not stripped:
            continue

        # Subsection headers under ## Active
        if current_section == "active" and stripped.startswith("### "):
            flush_subsection()
            current_subsection = strip_wikilink(stripped[4:].strip())
            current_subsection_tasks = []
            continue

        # Active tasks
        if current_section == "active" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            task_text = strip_wikilink(task_text)
            if current_subsection is None:
                current_subsection = "Other"
                current_subsection_tasks = []
            current_subsection_tasks.append(task_text)
            continue

        # Blocked tasks: "task -- waiting: X -- since DATE"
        if current_section == "blocked" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting = ""
            since = ""
            m = re.match(
                r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$",
                task_text
            )
            if m:
                task_text = m.group(1).strip()
                waiting = m.group(2).strip()
                since = m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", task_text)
                if m2:
                    task_text = m2.group(1).strip()
                    waiting = m2.group(2).strip()
            blocked.append({
                "task": strip_wikilink(task_text),
                "waiting": waiting,
                "since": since,
            })
            continue

        # Completed tasks: "- [x] text ✅ YYYY-MM-DD"
        if current_section == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            task_text = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            date_str = ""
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", task_text)
            if m:
                date_str = m.group(1)
                task_text = task_text[: m.start()].strip()
            completed.append({
                "task": strip_wikilink(task_text),
                "date": date_str,
            })
            continue

        # All other lines pass through silently

    # Flush any trailing active subsection
    flush_subsection()

    return active, blocked, completed


def build_html(active, blocked, completed):
    total_active = sum(len(s["tasks"]) for s in active)
    total_blocked = len(blocked)
    total_done = len(completed)
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Active cards
    active_html = ""
    for section in active:
        if not section["tasks"]:
            continue
        tasks_html = "".join(
            f'<li class="task-item">'
            f'<span class="task-dot active-dot"></span>'
            f'<span class="task-text">{escape(t)}</span>'
            f"</li>"
            for t in section["tasks"]
        )
        active_html += (
            f'<div class="section-card active-card">'
            f'<h3 class="section-title">{escape(section["section"])}</h3>'
            f'<ul class="task-list">{tasks_html}</ul>'
            f"</div>"
        )
    if not active_html:
        active_html = '<p class="empty-state">No active tasks. Clear runway.</p>'

    # Blocked cards
    blocked_html = ""
    for item in blocked:
        since_badge = (
            f'<span class="since-badge">since {escape(item["since"])}</span>'
            if item["since"]
            else ""
        )
        waiting_line = (
            f'<div class="waiting-line">'
            f'Waiting on: <strong>{escape(item["waiting"])}</strong> {since_badge}'
            f"</div>"
            if item["waiting"]
            else ""
        )
        blocked_html += (
            f'<div class="section-card blocked-card">'
            f'<div class="task-item blocked-task">'
            f'<span class="task-dot blocked-dot"></span>'
            f"<div>"
            f'<span class="task-text">{escape(item["task"])}</span>'
            f"{waiting_line}"
            f"</div>"
            f"</div>"
            f"</div>"
        )
    if not blocked_html:
        blocked_html = '<p class="empty-state">Nothing blocked.</p>'

    # Completed list (most recent first)
    completed_html = ""
    for item in reversed(completed):
        date_badge = (
            f'<span class="date-badge">{escape(item["date"])}</span>'
            if item["date"]
            else ""
        )
        completed_html += (
            f'<li class="task-item done-item">'
            f'<span class="checkmark">&#10003;</span>'
            f'<span class="task-text done-text">{escape(item["task"])}</span>'
            f"{date_badge}"
            f"</li>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Felix -- Tasks</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #222535;
      --border: #2d3147;
      --text: #e2e8f0;
      --text-muted: #8892a4;
      --active: #4ade80;
      --blocked: #fb923c;
      --done: #64748b;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 28px 16px;
    }}

    .container {{ max-width: 700px; margin: 0 auto; }}

    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 28px;
      gap: 12px;
      flex-wrap: wrap;
    }}

    h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.4px; }}
    .subtitle {{ font-size: 12px; color: var(--text-muted); margin-top: 3px; }}

    .stats-row {{ display: flex; gap: 8px; flex-wrap: wrap; }}

    .stat-chip {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid var(--border);
      background: var(--surface);
    }}
    .stat-chip.s-active {{ border-color: var(--active); color: var(--active); }}
    .stat-chip.s-blocked {{ border-color: var(--blocked); color: var(--blocked); }}
    .stat-chip.s-done {{ color: var(--done); }}
    .stat-dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
    .dot-a {{ background: var(--active); }}
    .dot-b {{ background: var(--blocked); }}
    .dot-d {{ background: var(--done); }}

    section {{ margin-bottom: 28px; }}

    .section-label {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 10px;
    }}

    .section-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
      margin-bottom: 8px;
    }}
    .active-card {{ border-left: 3px solid var(--active); }}
    .blocked-card {{
      border-left: 3px solid var(--blocked);
      background: rgba(251, 146, 60, 0.06);
    }}

    .section-title {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 10px;
    }}

    .task-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
    .task-item {{ display: flex; align-items: flex-start; gap: 10px; }}
    .task-dot {{ width: 7px; height: 7px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }}
    .active-dot {{ background: var(--active); }}
    .blocked-dot {{ background: var(--blocked); }}

    .task-text {{ font-size: 14px; line-height: 1.5; }}

    .waiting-line {{
      font-size: 12px;
      color: var(--blocked);
      margin-top: 4px;
      opacity: 0.9;
    }}
    .since-badge {{
      display: inline-block;
      font-size: 11px;
      background: rgba(251, 146, 60, 0.15);
      border: 1px solid rgba(251, 146, 60, 0.3);
      border-radius: 4px;
      padding: 1px 5px;
      margin-left: 4px;
    }}
    .blocked-task {{ align-items: flex-start; }}

    .date-badge {{
      margin-left: auto;
      font-size: 11px;
      color: var(--done);
      white-space: nowrap;
      padding-left: 10px;
      flex-shrink: 0;
    }}

    details {{ }}
    summary {{
      cursor: pointer;
      user-select: none;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 10px;
      list-style: none;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::before {{
      content: '\\25B6';
      font-size: 8px;
      transition: transform 0.15s;
      display: inline-block;
    }}
    details[open] summary::before {{ transform: rotate(90deg); }}

    .completed-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 5px;
    }}
    .done-item {{
      padding: 7px 10px;
      background: var(--surface);
      border-radius: 7px;
      border: 1px solid var(--border);
      justify-content: space-between;
      align-items: center;
    }}
    .checkmark {{ color: var(--done); font-size: 11px; flex-shrink: 0; }}
    .done-text {{ color: var(--done); text-decoration: line-through; font-size: 13px; }}

    .empty-state {{
      font-size: 13px;
      color: var(--text-muted);
      font-style: italic;
    }}

    footer {{
      text-align: right;
      font-size: 11px;
      color: var(--done);
      margin-top: 32px;
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}

    @media (max-width: 480px) {{
      body {{ padding: 16px 12px; }}
      h1 {{ font-size: 18px; }}
      .task-text {{ font-size: 13px; }}
      .stats-row {{ gap: 6px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Felix -- Tasks</h1>
        <div class="subtitle">Updated {updated}</div>
      </div>
      <div class="stats-row">
        <div class="stat-chip s-active"><span class="stat-dot dot-a"></span>{total_active} active</div>
        <div class="stat-chip s-blocked"><span class="stat-dot dot-b"></span>{total_blocked} blocked</div>
        <div class="stat-chip s-done"><span class="stat-dot dot-d"></span>{total_done} done</div>
      </div>
    </header>

    <section>
      <div class="section-label">Active</div>
      {active_html}
    </section>

    <section>
      <div class="section-label">Blocked / Awaiting</div>
      {blocked_html}
    </section>

    <section>
      <details>
        <summary>Completed ({total_done})</summary>
        <ul class="completed-list">{completed_html}</ul>
      </details>
    </section>

    <footer>felix.janssen -- second brain</footer>
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
    for s in active:
        print(f"  [{s['section']}] {s['tasks']}")
    for b in blocked:
        print(f"  [BLOCKED] {b['task']} -- waiting: {b['waiting']}")


if __name__ == "__main__":
    main()
