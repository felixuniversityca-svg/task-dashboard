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
from datetime import datetime, date, timedelta
from collections import defaultdict

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


def parse_tasks(content):
    active, blocked, completed = [], [], []
    current_section = None
    current_sub = None
    current_tasks = []

    def flush():
        if current_sub is not None and current_tasks:
            active.append({"section": current_sub, "tasks": current_tasks[:]})

    for line in content.splitlines():
        s = line.strip()
        if s == "## Active":
            current_section = "active"; current_sub = None; current_tasks = []; continue
        if s == "## Blocked":
            flush(); current_sub = None; current_section = "blocked"; continue
        if s == "## Completed":
            flush(); current_sub = None; current_section = "completed"; continue
        if s.startswith("## "):
            flush(); current_section = None; continue
        if s.startswith("<!--") or s == "---" or not s:
            continue
        if current_section == "active" and s.startswith("### "):
            flush()
            current_sub = strip_wikilink(s[4:].strip())
            current_tasks = []; continue
        if current_section == "active" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            task_text = strip_wikilink(task_text)
            if current_sub is None:
                current_sub = "Other"; current_tasks = []
            current_tasks.append(task_text); continue
        if current_section == "blocked" and "- [ ]" in line:
            task_text = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting = ""; since = ""
            m = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$", task_text)
            if m:
                task_text, waiting, since = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", task_text)
                if m2:
                    task_text, waiting = m2.group(1).strip(), m2.group(2).strip()
            since_date = parse_date(since)
            days = (date.today() - since_date).days if since_date else None
            blocked.append({"task": strip_wikilink(task_text), "waiting": waiting, "since_date": since_date, "days": days}); continue
        if current_section == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            task_text = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            d = None
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", task_text)
            if m:
                d = parse_date(m.group(1)); task_text = task_text[:m.start()].strip()
            completed.append({"task": strip_wikilink(task_text), "date": d}); continue

    flush()
    return active, blocked, completed


def sparkline_svg(completed, days=14):
    today = date.today()
    counts = defaultdict(int)
    for item in completed:
        if item["date"] and (today - item["date"]).days <= days:
            counts[item["date"]] += 1
    data = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        data.append(counts[d])
    max_val = max(data) if max(data) > 0 else 1
    w, h, pad = 280, 64, 4
    bar_w = (w - pad) / len(data) - 2
    bars = ""
    for i, v in enumerate(data):
        bh = max(3, int((v / max_val) * (h - pad * 2)))
        x = pad + i * ((w - pad) / len(data))
        y = h - pad - bh
        opacity = "1" if v > 0 else "0.15"
        bars += f'<rect x="{x:.1f}" y="{y}" width="{bar_w:.1f}" height="{bh}" rx="2" fill="#34d399" opacity="{opacity}"/>'
    total_recent = sum(data)
    return f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">{bars}</svg>', total_recent


def donut_svg(active):
    counts = [(s["section"], len(s["tasks"])) for s in active if s["tasks"]]
    if not counts:
        return '<svg viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg"><circle cx="40" cy="40" r="28" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="12"/></svg>', []
    colors = ["#6366f1", "#34d399", "#fbbf24", "#f472b6", "#60a5fa"]
    total = sum(c for _, c in counts)
    cx, cy, r, stroke_w = 40, 40, 28, 12
    circumference = 2 * 3.14159 * r
    arcs = ""
    offset = 0
    legend = []
    for i, (name, count) in enumerate(counts):
        pct = count / total
        dash = pct * circumference
        arcs += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                 f'stroke="{colors[i % len(colors)]}" stroke-width="{stroke_w}" '
                 f'stroke-dasharray="{dash:.2f} {circumference:.2f}" '
                 f'stroke-dashoffset="{-offset:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})"/>')
        legend.append({"name": name, "count": count, "color": colors[i % len(colors)]})
        offset += dash
    svg = f'<svg viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">{arcs}</svg>'
    return svg, legend


def build_html(active, blocked, completed):
    total_active = sum(len(s["tasks"]) for s in active)
    total_blocked = len(blocked)
    total_done = len(completed)
    today = date.today()
    done_this_week = sum(1 for c in completed if c["date"] and (today - c["date"]).days <= 7)
    oldest_block = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    spark_svg, spark_total = sparkline_svg(completed)
    donut, legend = donut_svg(active)
    updated = datetime.now().strftime("%b %-d at %H:%M")

    # KPI strip
    oldest_block_html = (
        f'<div class="kpi-card kpi-warn"><div class="kpi-val">{oldest_block}d</div><div class="kpi-label">Oldest block</div></div>'
        if oldest_block > 0 else
        f'<div class="kpi-card kpi-green"><div class="kpi-val">0</div><div class="kpi-label">Oldest block</div></div>'
    )
    kpi_html = f"""
      <div class="kpi-card"><div class="kpi-val kpi-active">{total_active}</div><div class="kpi-label">Active</div></div>
      <div class="kpi-card kpi-{'warn' if total_blocked else 'neutral'}"><div class="kpi-val {'kpi-warn-val' if total_blocked else ''}">{total_blocked}</div><div class="kpi-label">Blocked</div></div>
      <div class="kpi-card kpi-green"><div class="kpi-val kpi-green-val">{done_this_week}</div><div class="kpi-label">Done this week</div></div>
      {oldest_block_html}
    """

    # Legend for donut
    legend_html = "".join(
        f'<div class="legend-row"><span class="legend-dot" style="background:{l["color"]}"></span>'
        f'<span class="legend-name">{escape(l["name"])}</span>'
        f'<span class="legend-count">{l["count"]}</span></div>'
        for l in legend
    ) or '<div class="legend-row" style="color:var(--muted);font-size:12px">No active projects</div>'

    # Blocked cards
    blocked_sorted = sorted(blocked, key=lambda x: x["days"] or 0, reverse=True)
    blocked_html = ""
    for b in blocked_sorted:
        days = b["days"]
        if days is not None and days >= 14:
            pill = f'<span class="pill pill-crit">{days}d</span>'
            cls = "blocked-crit"
        elif days is not None and days >= 3:
            pill = f'<span class="pill pill-warn">{days}d</span>'
            cls = "blocked-warn"
        else:
            pill = f'<span class="pill pill-neutral">{days or 0}d</span>'
            cls = ""
        waiting_html = f'<div class="waiting-line">Waiting on <strong>{escape(b["waiting"])}</strong></div>' if b["waiting"] else ""
        blocked_html += (
            f'<div class="blocked-item {cls}">'
            f'<div class="blocked-row"><span class="blocked-dot"></span>'
            f'<span class="blocked-task">{escape(b["task"])}</span>{pill}</div>'
            f'{waiting_html}</div>'
        )
    if not blocked_html:
        blocked_html = '<p class="empty">Nothing blocked right now.</p>'

    # Active tasks
    active_html = ""
    for section in active:
        if not section["tasks"]:
            continue
        rows = "".join(
            f'<li class="active-row"><span class="active-pip"></span><span class="active-text">{escape(t)}</span></li>'
            for t in section["tasks"]
        )
        active_html += (
            f'<div class="project-block">'
            f'<div class="project-head"><span class="project-name">{escape(section["section"])}</span>'
            f'<span class="project-count">{len(section["tasks"])}</span></div>'
            f'<ul class="active-list">{rows}</ul></div>'
        )
    if not active_html:
        active_html = '<p class="empty">No active tasks.</p>'

    # Completed
    done_html = "".join(
        f'<li class="done-row"><span class="done-check">✓</span>'
        f'<span class="done-text">{escape(c["task"])}</span>'
        f'{"<span class=done-date>" + escape(str(c["date"])) + "</span>" if c["date"] else ""}'
        f'</li>'
        for c in reversed(completed)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Felix — Tasks</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #0b0f1a;
      --surface: #111827;
      --surface2: #1a2235;
      --border: rgba(255,255,255,0.06);
      --border2: rgba(255,255,255,0.11);
      --text: #f0f4ff;
      --muted: #5c6b8a;
      --subtle: #2d3a54;
      --green: #34d399;
      --green-dim: rgba(52,211,153,0.12);
      --green-bdr: rgba(52,211,153,0.22);
      --amber: #fbbf24;
      --amber-dim: rgba(251,191,36,0.10);
      --amber-bdr: rgba(251,191,36,0.22);
      --red: #f87171;
      --red-dim: rgba(248,113,113,0.10);
      --red-bdr: rgba(248,113,113,0.22);
      --indigo: #818cf8;
      --r: 12px;
    }}
    html {{ background: var(--bg); }}
    body {{
      font-family: 'Inter', -apple-system, sans-serif;
      background: radial-gradient(ellipse 90% 50% at 50% -5%, rgba(99,102,241,0.15) 0%, transparent 65%), var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 32px 18px 64px;
      -webkit-font-smoothing: antialiased;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}

    /* Header */
    .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:28px; flex-wrap:wrap; gap:12px; }}
    .header-left {{ display:flex; align-items:center; gap:12px; }}
    .avatar {{ width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,#6366f1,#8b5cf6); display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:800; color:#fff; flex-shrink:0; box-shadow:0 0 0 1px rgba(255,255,255,0.1),0 4px 14px rgba(99,102,241,0.35); }}
    .header-name {{ font-size:17px; font-weight:700; letter-spacing:-0.3px; }}
    .header-sub {{ font-size:11px; color:var(--muted); margin-top:2px; }}
    .header-time {{ font-size:11px; color:var(--muted); }}

    /* KPI strip */
    .kpi-strip {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:24px; }}
    .kpi-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:16px 14px; }}
    .kpi-warn {{ background:var(--amber-dim); border-color:var(--amber-bdr); }}
    .kpi-green {{ background:var(--green-dim); border-color:var(--green-bdr); }}
    .kpi-neutral {{ }}
    .kpi-val {{ font-size:26px; font-weight:800; letter-spacing:-1px; color:var(--text); line-height:1; margin-bottom:5px; }}
    .kpi-active {{ color:var(--indigo); }}
    .kpi-warn-val {{ color:var(--amber); }}
    .kpi-green-val {{ color:var(--green); }}
    .kpi-label {{ font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.8px; color:var(--muted); }}

    /* Two-col row */
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:24px; }}
    .panel {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:18px; }}
    .panel-title {{ font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:var(--muted); margin-bottom:14px; }}
    .spark-total {{ font-size:22px; font-weight:800; color:var(--green); letter-spacing:-0.5px; }}
    .spark-label {{ font-size:10px; color:var(--muted); margin-top:2px; margin-bottom:12px; font-weight:500; }}
    .spark-svg {{ width:100%; }}
    .donut-wrap {{ display:flex; align-items:center; gap:14px; }}
    .donut-svg {{ width:72px; height:72px; flex-shrink:0; }}
    .legend {{ display:flex; flex-direction:column; gap:7px; flex:1; min-width:0; }}
    .legend-row {{ display:flex; align-items:center; gap:7px; }}
    .legend-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
    .legend-name {{ font-size:12px; color:var(--text); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .legend-count {{ font-size:11px; font-weight:700; color:var(--muted); }}

    /* Section label */
    .sec-label {{ font-size:10px; font-weight:700; letter-spacing:1.1px; text-transform:uppercase; color:var(--muted); margin-bottom:10px; }}
    .section {{ margin-bottom:24px; }}

    /* Blocked */
    .blocked-item {{ background:var(--surface); border:1px solid var(--border); border-left:2px solid var(--amber); border-radius:var(--r); padding:14px 16px; margin-bottom:8px; }}
    .blocked-crit {{ border-left-color:var(--red); background:var(--red-dim); }}
    .blocked-warn {{ border-left-color:var(--amber); background:var(--amber-dim); }}
    .blocked-row {{ display:flex; align-items:center; gap:10px; }}
    .blocked-dot {{ width:6px; height:6px; border-radius:50%; background:var(--amber); flex-shrink:0; }}
    .blocked-crit .blocked-dot {{ background:var(--red); }}
    .blocked-task {{ font-size:14px; flex:1; line-height:1.4; }}
    .waiting-line {{ font-size:12px; color:var(--muted); margin-top:8px; padding-top:8px; border-top:1px solid var(--border); }}
    .waiting-line strong {{ color:var(--amber); font-weight:600; }}
    .blocked-crit .waiting-line strong {{ color:var(--red); }}

    /* Pills */
    .pill {{ font-size:11px; font-weight:700; border-radius:5px; padding:2px 7px; flex-shrink:0; }}
    .pill-warn {{ background:var(--amber-dim); color:var(--amber); border:1px solid var(--amber-bdr); }}
    .pill-crit {{ background:var(--red-dim); color:var(--red); border:1px solid var(--red-bdr); }}
    .pill-neutral {{ background:var(--subtle); color:var(--muted); border:1px solid var(--border); }}

    /* Active */
    .project-block {{ background:var(--surface); border:1px solid var(--border); border-left:2px solid var(--indigo); border-radius:var(--r); padding:14px 16px; margin-bottom:8px; }}
    .project-head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }}
    .project-name {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.6px; color:var(--muted); }}
    .project-count {{ font-size:11px; font-weight:700; background:var(--surface2); color:var(--muted); border:1px solid var(--border); border-radius:6px; padding:1px 7px; }}
    .active-list {{ list-style:none; display:flex; flex-direction:column; gap:9px; }}
    .active-row {{ display:flex; align-items:flex-start; gap:10px; }}
    .active-pip {{ width:5px; height:5px; border-radius:50%; background:var(--indigo); margin-top:8px; flex-shrink:0; box-shadow:0 0 5px rgba(129,140,248,0.5); }}
    .active-text {{ font-size:14px; line-height:1.5; }}

    /* Completed */
    details {{ }}
    summary {{ cursor:pointer; user-select:none; list-style:none; display:flex; align-items:center; gap:7px; font-size:10px; font-weight:700; letter-spacing:1.1px; text-transform:uppercase; color:var(--muted); margin-bottom:10px; }}
    summary::-webkit-details-marker {{ display:none; }}
    summary::after {{ content:''; display:inline-block; width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent; border-top:4px solid var(--muted); transition:transform 0.15s; }}
    details[open] summary::after {{ transform:rotate(180deg); }}
    .done-list {{ list-style:none; display:flex; flex-direction:column; gap:5px; }}
    .done-row {{ display:flex; align-items:center; gap:9px; padding:9px 12px; background:var(--surface); border:1px solid var(--border); border-radius:8px; }}
    .done-check {{ color:var(--subtle); font-size:11px; flex-shrink:0; }}
    .done-text {{ font-size:13px; color:var(--subtle); text-decoration:line-through; flex:1; }}
    .done-date {{ font-size:10px; color:var(--subtle); white-space:nowrap; flex-shrink:0; }}

    .empty {{ font-size:13px; color:var(--muted); font-style:italic; }}

    @media (max-width:520px) {{
      .kpi-strip {{ grid-template-columns:repeat(2,1fr); }}
      .two-col {{ grid-template-columns:1fr; }}
      .kpi-val {{ font-size:22px; }}
      .active-text, .blocked-task {{ font-size:13px; }}
    }}
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="header-left">
      <div class="avatar">F</div>
      <div>
        <div class="header-name">Felix Janssen</div>
        <div class="header-sub">Second Brain</div>
      </div>
    </div>
    <div class="header-time">Updated {updated}</div>
  </div>

  <!-- KPI strip -->
  <div class="kpi-strip">{kpi_html}</div>

  <!-- Sparkline + Donut -->
  <div class="two-col">
    <div class="panel">
      <div class="panel-title">Completed (last 14 days)</div>
      <div class="spark-total">{spark_total}</div>
      <div class="spark-label">tasks done</div>
      <div class="spark-svg">{spark_svg}</div>
    </div>
    <div class="panel">
      <div class="panel-title">Active by project</div>
      <div class="donut-wrap">
        <div class="donut-svg">{donut}</div>
        <div class="legend">{legend_html}</div>
      </div>
    </div>
  </div>

  <!-- Blocked -->
  <div class="section">
    <div class="sec-label">Blocked</div>
    {blocked_html}
  </div>

  <!-- Active -->
  <div class="section">
    <div class="sec-label">Active</div>
    {active_html}
  </div>

  <!-- Completed -->
  <div class="section">
    <details>
      <summary>Completed &nbsp;({total_done})</summary>
      <ul class="done-list">{done_html}</ul>
    </details>
  </div>

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
    OUTPUT_FILE.write_text(build_html(active, blocked, completed), encoding="utf-8")
    print(f"Built: {OUTPUT_FILE}")
    print(f"  {sum(len(s['tasks']) for s in active)} active  |  {len(blocked)} blocked  |  {len(completed)} done")


if __name__ == "__main__":
    main()
