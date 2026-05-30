#!/usr/bin/env python3
"""
build.py -- reads Tasks.md + dashboard-data.json, generates public/index.html
Run locally: python3 build.py
Netlify build command: python3 build.py
"""
import json
import re
import sys
from pathlib import Path
from html import escape
from datetime import datetime, date, timedelta
from collections import defaultdict

TASKS_FILE  = Path(__file__).parent / "Tasks.md"
DATA_FILE   = Path(__file__).parent / "dashboard-data.json"
OUTPUT_DIR  = Path(__file__).parent / "public"
OUTPUT_FILE = OUTPUT_DIR / "index.html"


# ── Helpers ─────────────────────────────────────────────────────────────────

def strip_wikilink(text):
    return re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split("|")[-1] if "|" in m.group(1) else m.group(1), text)

def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None

def days_ago(d):
    return (date.today() - d).days if d else None

def rel_date(d, time_str=""):
    if not d:
        return ""
    t = f" {time_str}" if time_str else ""
    delta = (d - date.today()).days
    if delta < 0:
        return f"{abs(delta)}d ago{t}"
    if delta == 0:
        return f"Today{t}"
    if delta == 1:
        return f"Tomorrow{t}"
    if delta <= 6:
        return f"{d.strftime('%A')}{t}"
    return f"{d.strftime('%b %-d')}{t}"

def epoch_label(epoch):
    if not epoch:
        return ""
    dt = datetime.fromtimestamp(epoch)
    delta = (date.today() - dt.date()).days
    if delta == 0:
        return dt.strftime("%-I:%M %p")
    if delta == 1:
        return "Yesterday"
    if delta <= 6:
        return dt.strftime("%A")
    return dt.strftime("%b %-d")


# ── Parse Tasks.md ───────────────────────────────────────────────────────────

def parse_tasks(content):
    active, blocked, completed = [], [], []
    sec = sub = None
    tasks = []

    def flush():
        if sub and tasks:
            active.append({"section": sub, "tasks": tasks[:]})

    for line in content.splitlines():
        s = line.strip()
        if s == "## Active":
            sec = "active"; sub = None; tasks = []; continue
        if s == "## Blocked":
            flush(); sub = None; sec = "blocked"; continue
        if s == "## Completed":
            flush(); sub = None; sec = "completed"; continue
        if s.startswith("## "):
            flush(); sec = None; continue
        if s.startswith("<!--") or s == "---" or not s:
            continue
        if sec == "active" and s.startswith("### "):
            flush(); sub = strip_wikilink(s[4:].strip()); tasks = []; continue
        if sec == "active" and "- [ ]" in line:
            t = strip_wikilink(re.sub(r"^[\s-]+\[ \]\s*", "", line).strip())
            if sub is None:
                sub = "Other"; tasks = []
            tasks.append(t); continue
        if sec == "blocked" and "- [ ]" in line:
            t = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting = since = ""
            m = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$", t)
            if m:
                t, waiting, since = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", t)
                if m2:
                    t, waiting = m2.group(1).strip(), m2.group(2).strip()
            sd = parse_date(since)
            blocked.append({"task": strip_wikilink(t), "waiting": waiting, "since_date": sd, "days": days_ago(sd)}); continue
        if sec == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            t = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            d = None
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", t)
            if m:
                d = parse_date(m.group(1)); t = t[:m.start()].strip()
            completed.append({"task": strip_wikilink(t), "date": d}); continue

    flush()
    return active, blocked, completed


# ── Charts ───────────────────────────────────────────────────────────────────

def sparkline_bars(completed, days=14):
    today = date.today()
    counts = defaultdict(int)
    for c in completed:
        if c["date"] and (today - c["date"]).days <= days:
            counts[c["date"]] += 1
    data = [counts[today - timedelta(days=i)] for i in range(days - 1, -1, -1)]
    total = sum(data)
    mx = max(data) if max(data) > 0 else 1
    w, h, gap = 260, 48, 3
    bw = (w - gap * (len(data) - 1)) / len(data)
    bars = ""
    for i, v in enumerate(data):
        bh = max(3, int((v / mx) * h))
        x = i * (bw + gap)
        y = h - bh
        col = "#34c759" if v > 0 else "#e5e5ea"
        bars += f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" rx="2" fill="{col}"/>'
    return f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block">{bars}</svg>', total


def donut_chart(active):
    counts = [(s["section"], len(s["tasks"])) for s in active if s["tasks"]]
    if not counts:
        return '<svg viewBox="0 0 72 72"><circle cx="36" cy="36" r="26" fill="none" stroke="#e5e5ea" stroke-width="10"/></svg>', []
    colors = ["#0071e3", "#34c759", "#ff9500", "#af52de", "#ff3b30"]
    total = sum(c for _, c in counts)
    circ = 2 * 3.14159265 * 26
    arcs = ""
    off = 0
    legend = []
    for i, (name, cnt) in enumerate(counts):
        dash = (cnt / total) * circ
        arcs += (f'<circle cx="36" cy="36" r="26" fill="none" stroke="{colors[i%len(colors)]}" '
                 f'stroke-width="10" stroke-dasharray="{dash:.2f} {circ:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 36 36)"/>')
        legend.append({"name": name, "cnt": cnt, "color": colors[i % len(colors)]})
        off += dash
    return f'<svg viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">{arcs}</svg>', legend


# ── Build HTML ────────────────────────────────────────────────────────────────

def build_html(active, blocked, completed, live_data):
    today = date.today()
    total_active  = sum(len(s["tasks"]) for s in active)
    total_blocked = len(blocked)
    total_done    = len(completed)
    done_week     = sum(1 for c in completed if c["date"] and (today - c["date"]).days <= 7)
    oldest_block  = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    spark, spark_n = sparkline_bars(completed)
    donut, legend  = donut_chart(active)
    updated = datetime.now().strftime("%b %-d at %H:%M")

    emails    = live_data.get("emails", [])
    deadlines = live_data.get("deadlines", [])

    # ── KPI strip
    def kpi(val, label, color="default"):
        color_map = {
            "blue":   ("kpi-blue",),
            "green":  ("kpi-green",),
            "orange": ("kpi-orange",),
            "red":    ("kpi-red",),
            "default":("",),
        }
        cls = color_map.get(color, ("",))[0]
        return f'<div class="kpi-card {cls}"><div class="kpi-val">{val}</div><div class="kpi-lbl">{label}</div></div>'

    blocked_color = "red" if oldest_block >= 14 else ("orange" if oldest_block >= 3 else "default")
    kpi_html = (
        kpi(total_active, "Active", "blue") +
        kpi(total_blocked, "Blocked", "orange" if total_blocked else "default") +
        kpi(done_week, "Done this week", "green") +
        kpi(f"{oldest_block}d" if oldest_block else "—", "Oldest block", blocked_color)
    )

    # ── Blocked
    blocked_html = ""
    for b in sorted(blocked, key=lambda x: x["days"] or 0, reverse=True):
        d = b["days"]
        if d is not None and d >= 14:
            pill_cls, label = "pill-red", f"{d}d"
        elif d is not None and d >= 3:
            pill_cls, label = "pill-orange", f"{d}d"
        else:
            pill_cls, label = "pill-gray", f"{d or 0}d"
        waiting = f'<div class="sub-line">Waiting on {escape(b["waiting"])}</div>' if b["waiting"] else ""
        blocked_html += (
            f'<div class="list-item">'
            f'<div class="item-row"><span class="dot dot-orange"></span>'
            f'<span class="item-text">{escape(b["task"])}</span>'
            f'<span class="pill {pill_cls}">{label}</span></div>'
            f'{waiting}</div>'
        )
    if not blocked_html:
        blocked_html = '<p class="empty-msg">Nothing blocked.</p>'

    # ── Active
    active_html = ""
    for sec in active:
        if not sec["tasks"]:
            continue
        rows = "".join(
            f'<li class="task-li"><span class="dot dot-blue dot-sm"></span><span class="task-str">{escape(t)}</span></li>'
            for t in sec["tasks"]
        )
        active_html += (
            f'<div class="project-card">'
            f'<div class="project-hd"><span class="project-nm">{escape(sec["section"])}</span>'
            f'<span class="pill pill-gray">{len(sec["tasks"])}</span></div>'
            f'<ul class="task-ul">{rows}</ul></div>'
        )
    if not active_html:
        active_html = '<p class="empty-msg">No active tasks.</p>'

    # ── Deadlines
    deadline_html = ""
    for dl in deadlines:
        d = parse_date(dl["date"])
        if d and (d - today).days < 0:
            continue  # skip past
        label = rel_date(d, dl.get("time", ""))
        delta = (d - today).days if d else 99
        urgency = "deadline-red" if delta <= 1 else ("deadline-orange" if delta <= 3 else "")
        deadline_html += (
            f'<div class="list-item">'
            f'<div class="item-row">'
            f'<span class="deadline-date {urgency}">{escape(label)}</span>'
            f'<span class="deadline-title">{escape(dl["title"])}</span>'
            f'</div></div>'
        )
    if not deadline_html:
        deadline_html = '<p class="empty-msg">No upcoming deadlines.</p>'

    # ── Emails
    email_html = ""
    for em in emails:
        unread_dot = '<span class="unread-dot"></span>' if em.get("unread") else '<span class="unread-dot unread-dot-read"></span>'
        time_label = epoch_label(em.get("epoch", 0))
        email_html += (
            f'<div class="email-item">'
            f'{unread_dot}'
            f'<div class="email-body">'
            f'<div class="email-from">{escape(em["from"][:30])}</div>'
            f'<div class="email-subject">{escape(em["subject"][:60])}</div>'
            f'</div>'
            f'<div class="email-time">{escape(time_label)}</div>'
            f'</div>'
        )
    if not email_html:
        email_html = '<p class="empty-msg">No recent emails.</p>'

    # ── Legend
    legend_html = "".join(
        f'<div class="leg-row"><span class="leg-dot" style="background:{l["color"]}"></span>'
        f'<span class="leg-name">{escape(l["name"])}</span>'
        f'<span class="leg-n">{l["cnt"]}</span></div>'
        for l in legend
    ) or '<p class="empty-msg" style="font-size:12px">No active projects</p>'

    # ── Completed
    done_html = "".join(
        f'<li class="done-li">'
        f'<span class="done-check">✓</span>'
        f'<span class="done-txt">{escape(c["task"])}</span>'
        f'{"<span class=done-date>" + escape(str(c["date"])) + "</span>" if c["date"] else ""}'
        f'</li>'
        for c in reversed(completed)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Felix — Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:       #f5f5f7;
      --surface:  #ffffff;
      --border:   rgba(0,0,0,0.08);
      --text:     #1d1d1f;
      --muted:    #6e6e73;
      --subtle:   #aeaeb2;
      --blue:     #0071e3;
      --blue-bg:  #e8f0fd;
      --green:    #34c759;
      --green-bg: #e8f8ed;
      --orange:   #ff9500;
      --orange-bg:#fff4e0;
      --red:      #ff3b30;
      --red-bg:   #ffebe9;
      --shadow:   0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.06);
      --r: 14px;
    }}
    html {{ background: var(--bg); }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 32px 18px 72px;
      -webkit-font-smoothing: antialiased;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}

    /* Header */
    .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:28px; gap:12px; flex-wrap:wrap; }}
    .header-left {{ display:flex; align-items:center; gap:12px; }}
    .avatar {{ width:40px; height:40px; border-radius:12px; background:linear-gradient(135deg,#0071e3,#34aadc); display:flex; align-items:center; justify-content:center; font-size:16px; font-weight:700; color:#fff; flex-shrink:0; box-shadow: 0 2px 8px rgba(0,113,227,0.3); }}
    .hd-name {{ font-size:17px; font-weight:700; letter-spacing:-0.3px; color:var(--text); }}
    .hd-sub  {{ font-size:12px; color:var(--muted); margin-top:1px; }}
    .hd-time {{ font-size:12px; color:var(--muted); }}

    /* KPI strip */
    .kpi-strip {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:20px; }}
    .kpi-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:16px 14px; box-shadow:var(--shadow); }}
    .kpi-blue   {{ background:var(--blue-bg); border-color:rgba(0,113,227,0.2); }}
    .kpi-green  {{ background:var(--green-bg); border-color:rgba(52,199,89,0.2); }}
    .kpi-orange {{ background:var(--orange-bg); border-color:rgba(255,149,0,0.2); }}
    .kpi-red    {{ background:var(--red-bg); border-color:rgba(255,59,48,0.2); }}
    .kpi-val {{ font-size:26px; font-weight:700; letter-spacing:-0.8px; color:var(--text); line-height:1; margin-bottom:5px; }}
    .kpi-blue .kpi-val   {{ color:var(--blue); }}
    .kpi-green .kpi-val  {{ color:var(--green); }}
    .kpi-orange .kpi-val {{ color:var(--orange); }}
    .kpi-red .kpi-val    {{ color:var(--red); }}
    .kpi-lbl {{ font-size:11px; font-weight:500; color:var(--muted); }}

    /* Two col */
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:20px; }}
    .panel {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:18px; box-shadow:var(--shadow); }}
    .panel-lbl {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.8px; color:var(--muted); margin-bottom:12px; }}
    .spark-big {{ font-size:28px; font-weight:700; color:var(--green); letter-spacing:-0.8px; line-height:1; }}
    .spark-sub {{ font-size:11px; color:var(--muted); margin-top:3px; margin-bottom:14px; }}
    .donut-wrap {{ display:flex; align-items:center; gap:14px; }}
    .donut-svg {{ width:72px; height:72px; flex-shrink:0; }}
    .leg {{ display:flex; flex-direction:column; gap:8px; flex:1; min-width:0; }}
    .leg-row {{ display:flex; align-items:center; gap:8px; }}
    .leg-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
    .leg-name {{ font-size:12px; color:var(--text); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .leg-n {{ font-size:12px; font-weight:600; color:var(--muted); }}

    /* Sections */
    .sec {{ margin-bottom:20px; }}
    .sec-lbl {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.8px; color:var(--muted); margin-bottom:10px; padding-left:2px; }}
    .card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); box-shadow:var(--shadow); overflow:hidden; }}

    /* List items (blocked + deadlines) */
    .list-item {{ padding:12px 16px; border-bottom:1px solid var(--border); }}
    .list-item:last-child {{ border-bottom:none; }}
    .item-row {{ display:flex; align-items:center; gap:10px; }}
    .item-text {{ font-size:14px; flex:1; line-height:1.4; }}
    .sub-line {{ font-size:12px; color:var(--muted); margin-top:5px; padding-left:18px; }}

    /* Deadline widget */
    .deadline-date {{ font-size:11px; font-weight:600; color:var(--muted); min-width:80px; flex-shrink:0; }}
    .deadline-red {{ color:var(--red); }}
    .deadline-orange {{ color:var(--orange); }}
    .deadline-title {{ font-size:13px; color:var(--text); flex:1; }}

    /* Dots */
    .dot {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
    .dot-sm {{ width:5px; height:5px; margin-top:8px; }}
    .dot-orange {{ background:var(--orange); }}
    .dot-blue {{ background:var(--blue); }}

    /* Pills */
    .pill {{ font-size:11px; font-weight:600; border-radius:6px; padding:2px 7px; flex-shrink:0; }}
    .pill-gray   {{ background:#f2f2f7; color:var(--muted); }}
    .pill-orange {{ background:var(--orange-bg); color:var(--orange); }}
    .pill-red    {{ background:var(--red-bg); color:var(--red); }}

    /* Email widget */
    .email-item {{ display:flex; align-items:center; gap:10px; padding:12px 16px; border-bottom:1px solid var(--border); }}
    .email-item:last-child {{ border-bottom:none; }}
    .unread-dot {{ width:8px; height:8px; border-radius:50%; background:var(--blue); flex-shrink:0; }}
    .unread-dot-read {{ background:transparent; border:1px solid var(--border); }}
    .email-body {{ flex:1; min-width:0; }}
    .email-from {{ font-size:13px; font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .email-subject {{ font-size:12px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:1px; }}
    .email-time {{ font-size:11px; color:var(--muted); flex-shrink:0; white-space:nowrap; }}

    /* Projects */
    .project-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:14px 16px; margin-bottom:8px; box-shadow:var(--shadow); }}
    .project-hd {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }}
    .project-nm {{ font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; color:var(--muted); }}
    .task-ul {{ list-style:none; display:flex; flex-direction:column; gap:9px; }}
    .task-li {{ display:flex; align-items:flex-start; gap:10px; }}
    .task-str {{ font-size:14px; line-height:1.5; }}

    /* Completed */
    details {{ }}
    summary {{ cursor:pointer; user-select:none; list-style:none; display:flex; align-items:center; gap:7px; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.8px; color:var(--muted); margin-bottom:10px; padding-left:2px; }}
    summary::-webkit-details-marker {{ display:none; }}
    summary::after {{ content:''; display:inline-block; width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent; border-top:4px solid var(--muted); transition:transform 0.15s; }}
    details[open] summary::after {{ transform:rotate(180deg); }}
    .done-list {{ display:flex; flex-direction:column; gap:5px; list-style:none; }}
    .done-li {{ display:flex; align-items:center; gap:8px; padding:9px 12px; background:var(--surface); border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow); }}
    .done-check {{ color:var(--green); font-size:12px; flex-shrink:0; }}
    .done-txt {{ font-size:13px; color:var(--subtle); text-decoration:line-through; flex:1; }}
    .done-date {{ font-size:11px; color:var(--subtle); white-space:nowrap; flex-shrink:0; }}

    .empty-msg {{ font-size:13px; color:var(--muted); padding:12px 16px; font-style:italic; }}

    /* Footer */
    footer {{ margin-top:40px; padding-top:18px; border-top:1px solid var(--border); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
    .ft-name {{ font-size:12px; font-weight:600; color:var(--subtle); }}
    .ft-time {{ font-size:11px; color:var(--subtle); }}

    @media (max-width:520px) {{
      .kpi-strip {{ grid-template-columns:repeat(2,1fr); }}
      .two-col {{ grid-template-columns:1fr; }}
      .kpi-val {{ font-size:22px; }}
      .task-str, .item-text, .email-from {{ font-size:13px; }}
    }}
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="header-left">
      <div class="avatar">F</div>
      <div>
        <div class="hd-name">Felix Janssen</div>
        <div class="hd-sub">Second Brain</div>
      </div>
    </div>
    <div class="hd-time">Updated {updated}</div>
  </div>

  <div class="kpi-strip">{kpi_html}</div>

  <div class="two-col">
    <div class="panel">
      <div class="panel-lbl">Completed — last 14 days</div>
      <div class="spark-big">{spark_n}</div>
      <div class="spark-sub">tasks done</div>
      {spark}
    </div>
    <div class="panel">
      <div class="panel-lbl">Active by project</div>
      <div class="donut-wrap">
        <div class="donut-svg">{donut}</div>
        <div class="leg">{legend_html}</div>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-lbl">Upcoming</div>
    <div class="card">{deadline_html}</div>
  </div>

  <div class="sec">
    <div class="sec-lbl">Recent Emails</div>
    <div class="card">{email_html}</div>
  </div>

  <div class="sec">
    <div class="sec-lbl">Blocked</div>
    <div class="card">{blocked_html}</div>
  </div>

  <div class="sec">
    <div class="sec-lbl">Active</div>
    {active_html}
  </div>

  <div class="sec">
    <details>
      <summary>Completed &nbsp;({total_done})</summary>
      <ul class="done-list">{done_html}</ul>
    </details>
  </div>

  <footer>
    <span class="ft-name">felix.janssen</span>
    <span class="ft-time">Updated {updated}</span>
  </footer>

</div>
</body>
</html>"""


def main():
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks.md not found", file=sys.stderr); sys.exit(1)

    content   = TASKS_FILE.read_text(encoding="utf-8")
    live_data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

    active, blocked, completed = parse_tasks(content)
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(build_html(active, blocked, completed, live_data))
    print(f"Built: {OUTPUT_FILE}")
    print(f"  {sum(len(s['tasks']) for s in active)} active  |  {len(blocked)} blocked  |  {len(completed)} done")


if __name__ == "__main__":
    main()
