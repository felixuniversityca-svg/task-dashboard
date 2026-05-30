#!/usr/bin/env python3
"""
build.py -- reads Tasks.md + dashboard-data.json, generates public/index.html
Run locally: python3 build.py  |  Netlify build command: python3 build.py
"""
import json, re, sys, calendar as cal_mod, html as html_mod
from pathlib import Path
from html import escape
from datetime import datetime, date, timedelta
from collections import defaultdict

TASKS_FILE  = Path(__file__).parent / "Tasks.md"
DATA_FILE   = Path(__file__).parent / "dashboard-data.json"
OUTPUT_DIR  = Path(__file__).parent / "public"
OUTPUT_FILE = OUTPUT_DIR / "index.html"


# ── Utilities ────────────────────────────────────────────────────────────────

def strip_wikilink(t):
    return re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split("|")[-1] if "|" in m.group(1) else m.group(1), t)

def parse_date(s):
    if not s: return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except ValueError: pass
    return None

def days_diff(d): return (date.today() - d).days if d else None

def rel_label(d, time_str=""):
    if not d: return ""
    t = f" {time_str}" if time_str else ""
    delta = (d - date.today()).days
    if delta < 0:  return f"{abs(delta)}d ago{t}"
    if delta == 0: return f"Today{t}"
    if delta == 1: return f"Tomorrow{t}"
    if delta <= 6: return f"{d.strftime('%A')}{t}"
    return f"{d.strftime('%b %-d')}{t}"

def epoch_str(epoch):
    if not epoch: return ""
    dt = datetime.fromtimestamp(epoch)
    delta = (date.today() - dt.date()).days
    if delta == 0: return dt.strftime("%-I:%M %p")
    if delta == 1: return "Yesterday"
    if delta <= 6: return dt.strftime("%A")
    return dt.strftime("%b %-d")

def clean_snippet(s):
    """Decode HTML entities and strip extra whitespace from email snippets."""
    return re.sub(r"\s+", " ", html_mod.unescape(s)).strip()[:150]


# ── Parse Tasks.md ─────────────────────────────────────────────────────────

def parse_tasks(content):
    active, blocked, completed = [], [], []
    sec = sub = None
    tasks = []

    def flush():
        if sub and tasks:
            active.append({"section": sub, "tasks": tasks[:]})

    for line in content.splitlines():
        s = line.strip()
        if s == "## Active":   sec="active";    sub=None; tasks=[]; continue
        if s == "## Blocked":  flush(); sub=None; sec="blocked";    continue
        if s == "## Completed":flush(); sub=None; sec="completed";  continue
        if s.startswith("## "): flush(); sec=None; continue
        if s.startswith("<!--") or s == "---" or not s: continue
        if sec == "active" and s.startswith("### "):
            flush(); sub=strip_wikilink(s[4:].strip()); tasks=[]; continue
        if sec == "active" and "- [ ]" in line:
            raw = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            due = None
            m = re.search(r"<!--\s*due:\s*(\d{4}-\d{2}-\d{2})\s*-->", raw)
            if m: due=parse_date(m.group(1)); raw=raw[:m.start()].strip()
            if sub is None: sub="Other"; tasks=[]
            tasks.append({"text": strip_wikilink(raw), "due": due, "section": sub})
            continue
        if sec == "blocked" and "- [ ]" in line:
            raw = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting=since=""
            m = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$", raw)
            if m: raw,waiting,since = m.group(1).strip(),m.group(2).strip(),m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", raw)
                if m2: raw,waiting = m2.group(1).strip(),m2.group(2).strip()
            sd = parse_date(since)
            blocked.append({"task":strip_wikilink(raw),"waiting":waiting,"since_date":sd,"days":days_diff(sd)})
            continue
        if sec == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            raw = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            d=None
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", raw)
            if m: d=parse_date(m.group(1)); raw=raw[:m.start()].strip()
            completed.append({"task":strip_wikilink(raw),"date":d})
            continue
    flush()
    return active, blocked, completed


# ── Charts ──────────────────────────────────────────────────────────────────

def sparkline(completed, days=14):
    today = date.today()
    day_tasks = defaultdict(list)
    for c in completed:
        if c["date"] and (today-c["date"]).days <= days:
            day_tasks[c["date"]].append(c["task"])
    data = [(today-timedelta(days=i), day_tasks[today-timedelta(days=i)]) for i in range(days-1,-1,-1)]
    mx = max((len(t) for _,t in data), default=1) or 1
    W,H,gap = 260,44,2
    bw = (W - gap*(len(data)-1)) / len(data)
    bars = ""
    for i,(d,tasks) in enumerate(data):
        v = len(tasks)
        bh = max(3, int(v/mx*H))
        fill = "#34c759" if v else "#e5e5ea"
        bars += f'<rect data-key="spark-{i}" x="{i*(bw+gap):.1f}" y="{H-bh}" width="{bw:.1f}" height="{bh}" rx="2" fill="{fill}" style="cursor:pointer"/>'
    svg = f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block">{bars}</svg>'
    return svg, sum(len(t) for _,t in data), data


def donut(active):
    counts = [(s["section"], len(s["tasks"]), s["tasks"]) for s in active if s["tasks"]]
    if not counts:
        return '<svg viewBox="0 0 72 72"><circle cx="36" cy="36" r="26" fill="none" stroke="#e5e5ea" stroke-width="10"/></svg>', []
    colors = ["#0071e3","#34c759","#ff9500","#af52de","#ff3b30"]
    total  = sum(c for _,c,_ in counts)
    circ   = 2*3.14159265*26
    arcs,off,legend = "",0,[]
    for i,(name,cnt,tasks) in enumerate(counts):
        dash = (cnt/total)*circ
        arcs += (f'<circle data-key="donut-{i}" cx="36" cy="36" r="26" fill="none" stroke="{colors[i%len(colors)]}" '
                 f'stroke-width="10" stroke-dasharray="{dash:.2f} {circ:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 36 36)" style="cursor:pointer"/>')
        legend.append({"name":name,"cnt":cnt,"color":colors[i%len(colors)],"tasks":tasks,"idx":i})
        off += dash
    return f'<svg viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">{arcs}</svg>', legend


def mini_calendar(deadlines, active_all, completed, months=2):
    today = date.today()
    event_map = defaultdict(list)
    for dl in deadlines:
        d = parse_date(dl["date"])
        if d: event_map[d].append(("deadline", dl["title"]))
    for sec in active_all:
        for t in sec["tasks"]:
            if t["due"]: event_map[t["due"]].append(("task", t["text"]))
    for c in completed:
        if c["date"]: event_map[c["date"]].append(("done", c["task"]))

    DAY_NAMES = ["M","T","W","T","F","S","S"]
    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    html = '<div class="cal-grid">'
    for mo in range(months):
        d0  = (today.replace(day=1) + timedelta(days=32*mo))
        yr,mth = d0.year, d0.month
        first = date(yr,mth,1)
        dim   = cal_mod.monthrange(yr,mth)[1]
        offset = first.weekday()

        html += f'<div class="cal-month"><div class="cal-title">{MONTH_NAMES[mth-1]} {yr}</div>'
        html += '<div class="cal-days-hd">'+"".join(f'<span>{d}</span>' for d in DAY_NAMES)+'</div>'
        html += '<div class="cal-days">'
        for _ in range(offset):
            html += '<div class="cal-cell cal-empty"></div>'
        for day in range(1, dim+1):
            d = date(yr,mth,day)
            events = event_map.get(d,[])
            is_today = d==today; is_past = d<today
            cls = "cal-cell" + (" cal-today" if is_today else " cal-past" if is_past else "")
            has_ev = bool(events)
            if has_ev:
                delta = (d-today).days
                dot_col = "#ff3b30" if delta<=1 else ("#ff9500" if delta<=3 else "#0071e3")
                dot = f'<span class="cal-dot" style="background:{dot_col}"></span>'
                key = f"cal-{d.isoformat()}"
                html += f'<div class="{cls} cal-clickable" data-key="{key}"><span class="cal-num">{day}</span>{dot}</div>'
            else:
                html += f'<div class="{cls}"><span class="cal-num">{day}</span></div>'
        html += '</div></div>'
    html += '</div>'
    return html, event_map


# ── Panel Data Builder ───────────────────────────────────────────────────────

def build_panel_data(active, blocked, completed, live_data, spark_data, legend, event_map):
    """Build the PANEL_DATA JS object embedded in the page."""
    today = date.today()
    pd = {}

    # KPI panels
    proj_breakdown = ", ".join(f"{s['section']} ({len(s['tasks'])})" for s in active if s["tasks"]) or "None"
    pd["kpi-active"] = {"t": "Active Tasks", "l": [
        f"<strong>{sum(len(s['tasks']) for s in active)}</strong> open tasks across your projects",
        proj_breakdown
    ]}

    if blocked:
        bl = ", ".join(f"{b['task'][:30]} ({b['days']}d)" for b in blocked)
        pd["kpi-blocked"] = {"t": "Blocked Tasks", "l": [
            f"<strong>{len(blocked)}</strong> tasks waiting on external dependencies",
            bl
        ]}
    else:
        pd["kpi-blocked"] = {"t": "Blocked Tasks", "l": ["No tasks currently blocked.", "Clear runway."]}

    done_wk = [c for c in completed if c["date"] and (today-c["date"]).days<=7]
    pd["kpi-week"] = {"t": "Done This Week", "l": [
        f"<strong>{len(done_wk)}</strong> tasks completed in the last 7 days",
        *[f"✓ {c['task'][:50]}" for c in done_wk[:5]]
    ]}

    oldest = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    if oldest > 0 and blocked:
        ob = max(blocked, key=lambda b: b["days"] or 0)
        pd["kpi-oldest"] = {"t": "Oldest Block", "l": [
            f"<strong>{ob['task'][:50]}</strong>",
            f"Blocked <strong>{ob['days']} days</strong>",
            f"Waiting on: {ob['waiting']}"
        ]}
    else:
        pd["kpi-oldest"] = {"t": "Oldest Block", "l": ["No tasks currently blocked."]}

    # Sparkline bars
    for i,(d,tasks) in enumerate(spark_data):
        if tasks:
            pd[f"spark-{i}"] = {"t": f"{d.strftime('%A, %b %-d')}",
                                  "l": [f"<strong>{len(tasks)}</strong> tasks completed",
                                        *[f"✓ {t[:55]}" for t in tasks[:6]]]}
        else:
            pd[f"spark-{i}"] = {"t": f"{d.strftime('%A, %b %-d')}", "l": ["No tasks completed this day."]}

    # Donut segments
    for l in legend:
        pd[f"donut-{l['idx']}"] = {"t": l["name"],
            "l": [f"<strong>{l['cnt']}</strong> active tasks",
                  *[f"• {t['text'][:55]}" for t in l["tasks"][:6]]]}

    # Calendar days
    for d, events in event_map.items():
        lines = []
        for kind, title in events:
            icon = "🔴" if kind=="deadline" else ("✓" if kind=="done" else "•")
            lines.append(f"{icon} {title[:60]}")
        pd[f"cal-{d.isoformat()}"] = {"t": d.strftime("%A, %B %-d"), "l": lines}

    # Deadlines
    deadlines = live_data.get("deadlines", [])
    for i,dl in enumerate(deadlines):
        d = parse_date(dl["date"])
        lbl = rel_label(d, dl.get("time",""))
        pd[f"deadline-{i}"] = {"t": dl["title"][:60], "l": [
            f"<strong>When:</strong> {lbl}",
            f"<strong>Date:</strong> {dl['date']}" + (f" at {dl['time']}" if dl.get('time') else "")
        ]}

    # Emails
    emails = live_data.get("emails", [])
    for i,em in enumerate(emails):
        snippet = clean_snippet(em.get("snippet",""))
        pd[f"email-{i}"] = {"t": em["from"][:40], "l": [
            f"<strong>{escape(em['subject'][:60])}</strong>",
            escape(snippet) if snippet else "(no preview)",
            f"<em>{epoch_str(em.get('epoch',0))}</em>"
        ]}

    # Blocked tasks
    for i,b in enumerate(blocked):
        since_str = b["since_date"].strftime("%b %-d") if b["since_date"] else "unknown"
        pd[f"blocked-{i}"] = {"t": b["task"][:60], "l": [
            f"<strong>Waiting on:</strong> {escape(b['waiting'])}" if b["waiting"] else "No specific dependency noted.",
            f"<strong>Since:</strong> {since_str} &middot; <strong>{b['days']} days</strong> blocked" if b["days"] is not None else f"Since: {since_str}",
            "This blocker will be flagged at session start if it exceeds 3 days." if (b["days"] or 0) >= 3 else ""
        ]}

    # Active tasks
    for si,sec in enumerate(active):
        for ti,t in enumerate(sec["tasks"]):
            due_str = rel_label(t["due"]) if t["due"] else "No deadline set"
            pd[f"active-{si}-{ti}"] = {"t": t["text"][:60], "l": [
                f"<strong>Project:</strong> {escape(sec['section'])}",
                f"<strong>Due:</strong> {due_str}"
            ]}

    # Completed tasks
    for i,c in enumerate(completed):
        date_str = c["date"].strftime("%A, %B %-d") if c["date"] else "Date unknown"
        pd[f"done-{i}"] = {"t": c["task"][:60], "l": [
            f"<strong>Completed:</strong> {date_str}"
        ]}

    return pd


# ── HTML ─────────────────────────────────────────────────────────────────────

def build_html(active, blocked, completed, live_data):
    today     = date.today()
    t_active  = sum(len(s["tasks"]) for s in active)
    t_block   = len(blocked)
    t_done    = len(completed)
    done_wk   = sum(1 for c in completed if c["date"] and (today-c["date"]).days<=7)
    oldest    = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    spark_svg, spark_n, spark_data = sparkline(completed)
    donut_svg, legend = donut(active)
    deadlines = live_data.get("deadlines", [])
    emails    = live_data.get("emails", [])
    cal_html, event_map = mini_calendar(deadlines, active, completed, months=2)
    updated   = datetime.now().strftime("%b %-d at %H:%M")

    panel_data = build_panel_data(active, blocked, completed, live_data, spark_data, legend, event_map)
    panel_js   = json.dumps(panel_data, ensure_ascii=False)

    # ── KPI
    def kpi(val, lbl, cls, key, tip):
        return (f'<div class="kpi-card {cls} interactive" data-key="{key}" data-tip="{escape(tip)}">'
                f'<div class="kpi-val">{val}</div><div class="kpi-lbl">{lbl}</div></div>')
    kpi_html = (
        kpi(t_active, "Active",       "kpi-blue",                    "kpi-active", "Click for breakdown") +
        kpi(t_block,  "Blocked",      "kpi-orange" if t_block else "", "kpi-blocked","Click for details") +
        kpi(done_wk,  "Done this week","kpi-green",                   "kpi-week",  "Click to see tasks") +
        kpi(f"{oldest}d" if oldest else "None", "Oldest block",
            "kpi-red" if oldest>=14 else ("kpi-orange" if oldest>=3 else ""), "kpi-oldest","Click for details")
    )

    # ── Deadlines
    deadline_rows = ""
    for i,dl in enumerate(deadlines):
        d = parse_date(dl["date"])
        if d and (d-today).days < 0: continue
        lbl   = rel_label(d, dl.get("time",""))
        delta = (d-today).days if d else 99
        dt_cls = "dt-red" if delta<=1 else ("dt-orange" if delta<=3 else "dt-blue")
        deadline_rows += (f'<div class="list-row interactive" data-key="deadline-{i}">'
                          f'<span class="dt-badge {dt_cls}">{escape(lbl)}</span>'
                          f'<span class="list-text">{escape(dl["title"])}</span></div>')
    if not deadline_rows:
        deadline_rows = '<p class="empty-p">No upcoming deadlines.</p>'

    # ── Emails
    email_rows = ""
    for i,em in enumerate(emails):
        dot = '<span class="e-dot"></span>' if em.get("unread") else '<span class="e-dot e-dot-read"></span>'
        email_rows += (f'<div class="email-row interactive" data-key="email-{i}">{dot}'
                       f'<div class="e-body"><div class="e-from">{escape(em["from"][:28])}</div>'
                       f'<div class="e-sub">{escape(em["subject"][:55])}</div></div>'
                       f'<div class="e-time">{escape(epoch_str(em.get("epoch",0)))}</div></div>')
    if not email_rows:
        email_rows = '<p class="empty-p">No recent emails.</p>'

    # ── Blocked
    blocked_sorted = sorted(blocked, key=lambda x: x["days"] or 0, reverse=True)
    blocked_rows = ""
    for i,b in enumerate(blocked_sorted):
        d = b["days"]
        if d is not None and d>=14:  pill_cls,plbl="pill-red",   f"{d}d"
        elif d is not None and d>=3: pill_cls,plbl="pill-orange", f"{d}d"
        else:                        pill_cls,plbl="pill-gray",   f"{d or 0}d"
        since_lbl = f" · Since {b['since_date'].strftime('%b %-d')}" if b["since_date"] else ""
        blocked_rows += (f'<div class="list-row interactive" data-key="blocked-{i}">'
                         f'<span class="dot dot-orange"></span>'
                         f'<div style="flex:1;min-width:0">'
                         f'<div class="list-text">{escape(b["task"])}</div>'
                         f'<div class="list-sub-inline">Waiting on {escape(b["waiting"])}{since_lbl}</div>'
                         f'</div><span class="pill {pill_cls}">{plbl}</span></div>')
    if not blocked_rows:
        blocked_rows = '<p class="empty-p">Nothing blocked.</p>'

    # ── Active
    active_cards = ""
    for si,sec in enumerate(active):
        if not sec["tasks"]: continue
        rows = ""
        for ti,t in enumerate(sec["tasks"]):
            due_html=""
            if t["due"]:
                delta=(t["due"]-today).days
                d_cls="due-red" if delta<=1 else ("due-orange" if delta<=3 else "due-blue")
                due_html=f'<span class="due-tag {d_cls}">{rel_label(t["due"])}</span>'
            rows += (f'<li class="task-li interactive" data-key="active-{si}-{ti}">'
                     f'<span class="dot dot-blue dot-sm"></span>'
                     f'<span class="task-text">{escape(t["text"])}</span>'
                     f'{due_html}</li>')
        active_cards += (f'<div class="proj-card">'
                         f'<div class="proj-hd"><span class="proj-nm">{escape(sec["section"])}</span>'
                         f'<span class="pill pill-gray">{len(sec["tasks"])}</span></div>'
                         f'<ul class="task-ul">{rows}</ul></div>')
    if not active_cards:
        active_cards = '<p class="empty-p">No active tasks.</p>'

    # ── Legend
    legend_html = "".join(
        f'<div class="leg-row interactive" data-key="donut-{l["idx"]}">'
        f'<span class="leg-dot" style="background:{l["color"]}"></span>'
        f'<span class="leg-name">{escape(l["name"])}</span>'
        f'<span class="leg-n">{l["cnt"]}</span></div>'
        for l in legend
    ) or '<p class="empty-p" style="font-size:12px">No active projects</p>'

    # ── Completed
    done_rows = ""
    for i, c in enumerate(reversed(completed)):
        date_html = f'<span class="done-dt">{c["date"].strftime("%b %-d")}</span>' if c["date"] else ""
        done_rows += (f'<li class="done-li interactive" data-key="done-{i}">'
                      f'<span class="done-ck">&#10003;</span>'
                      f'<span class="done-txt">{escape(c["task"])}</span>'
                      f'{date_html}</li>')

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
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    :root{{
      --bg:#f5f5f7;--surface:#fff;--border:rgba(0,0,0,0.08);--border2:rgba(0,0,0,0.13);
      --text:#1d1d1f;--muted:#6e6e73;--subtle:#aeaeb2;
      --blue:#0071e3;--blue-bg:#e8f0fd;--blue-bdr:rgba(0,113,227,0.18);
      --green:#34c759;--green-bg:#e8f8ed;--green-bdr:rgba(52,199,89,0.18);
      --orange:#ff9500;--orange-bg:#fff4e0;--orange-bdr:rgba(255,149,0,0.18);
      --red:#ff3b30;--red-bg:#ffebe9;--red-bdr:rgba(255,59,48,0.18);
      --shadow:0 1px 3px rgba(0,0,0,0.05),0 4px 16px rgba(0,0,0,0.06);
      --r:14px
    }}
    html{{background:var(--bg)}}
    body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:28px 20px 72px;-webkit-font-smoothing:antialiased}}
    .wrap{{max-width:1100px;margin:0 auto}}

    /* Header */
    .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;gap:12px;flex-wrap:wrap}}
    .hd-left{{display:flex;align-items:center;gap:12px}}
    .avatar{{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#0071e3,#34aadc);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;color:#fff;flex-shrink:0;box-shadow:0 2px 8px rgba(0,113,227,0.28)}}
    .hd-name{{font-size:17px;font-weight:700;letter-spacing:-.3px}}
    .hd-sub{{font-size:12px;color:var(--muted);margin-top:1px}}
    .hd-time{{font-size:12px;color:var(--muted)}}

    /* KPI */
    .kpi-strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px}}
    .kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 15px;box-shadow:var(--shadow);position:relative}}
    .kpi-blue{{background:var(--blue-bg);border-color:var(--blue-bdr)}}.kpi-green{{background:var(--green-bg);border-color:var(--green-bdr)}}
    .kpi-orange{{background:var(--orange-bg);border-color:var(--orange-bdr)}}.kpi-red{{background:var(--red-bg);border-color:var(--red-bdr)}}
    .kpi-val{{font-size:28px;font-weight:700;letter-spacing:-.8px;line-height:1;margin-bottom:4px}}
    .kpi-blue .kpi-val{{color:var(--blue)}}.kpi-green .kpi-val{{color:var(--green)}}.kpi-orange .kpi-val{{color:var(--orange)}}.kpi-red .kpi-val{{color:var(--red)}}
    .kpi-lbl{{font-size:11px;font-weight:500;color:var(--muted)}}

    /* Tooltip */
    [data-tip]{{position:relative}}
    [data-tip]::after{{content:attr(data-tip);position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#1d1d1f;color:#fff;font-size:11px;padding:5px 9px;border-radius:6px;white-space:nowrap;pointer-events:none;opacity:0;transition:opacity .15s;z-index:50}}
    [data-tip]:hover::after{{opacity:1}}

    /* Interactive */
    .interactive{{cursor:pointer;transition:opacity .12s}}
    .interactive:hover{{opacity:.82}}
    .interactive:active{{opacity:.65}}

    /* Top row */
    .top-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:18px}}
    .panel{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px;box-shadow:var(--shadow)}}
    .p-lbl{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:12px}}
    .spark-big{{font-size:28px;font-weight:700;color:var(--green);letter-spacing:-.8px;line-height:1}}
    .spark-sub{{font-size:11px;color:var(--muted);margin:3px 0 14px}}
    .donut-wrap{{display:flex;align-items:center;gap:14px}}
    .donut-svg{{width:72px;height:72px;flex-shrink:0}}
    .leg{{display:flex;flex-direction:column;gap:8px;flex:1;min-width:0}}
    .leg-row{{display:flex;align-items:center;gap:8px;border-radius:6px;padding:3px 4px;margin:-3px -4px}}
    .leg-row:hover{{background:rgba(0,0,0,0.04)}}
    .leg-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
    .leg-name{{font-size:12px;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .leg-n{{font-size:12px;font-weight:600;color:var(--muted)}}

    /* Calendar */
    .cal-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
    .cal-title{{font-size:12px;font-weight:700;margin-bottom:7px}}
    .cal-days-hd{{display:grid;grid-template-columns:repeat(7,1fr);margin-bottom:3px}}
    .cal-days-hd span{{font-size:9px;font-weight:600;text-align:center;color:var(--subtle)}}
    .cal-days{{display:grid;grid-template-columns:repeat(7,1fr);gap:1px}}
    .cal-cell{{display:flex;flex-direction:column;align-items:center;padding:2px 1px;border-radius:5px;min-height:24px}}
    .cal-clickable{{cursor:pointer;border-radius:5px}}
    .cal-clickable:hover{{background:var(--blue-bg)}}
    .cal-today .cal-num{{background:var(--blue);color:#fff;border-radius:50%;width:17px;height:17px;display:flex;align-items:center;justify-content:center}}
    .cal-past .cal-num{{color:var(--subtle)}}
    .cal-num{{font-size:10px;font-weight:500;line-height:1.7}}
    .cal-dot{{width:4px;height:4px;border-radius:50%;margin-top:1px}}

    /* Main two-col */
    .main-row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}}
    .sec{{margin-bottom:18px}}
    .sec-lbl{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:9px;padding-left:2px}}

    /* List rows */
    .list-row{{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--border)}}
    .list-row:last-child{{border-bottom:none}}
    .list-row:hover{{background:rgba(0,0,0,0.02)}}
    .list-text{{font-size:13px;line-height:1.4;flex:1}}
    .list-sub-inline{{font-size:11px;color:var(--muted);margin-top:2px}}

    /* Deadline badges */
    .dt-badge{{font-size:10px;font-weight:700;border-radius:5px;padding:2px 7px;flex-shrink:0;white-space:nowrap}}
    .dt-red{{background:var(--red-bg);color:var(--red)}}.dt-orange{{background:var(--orange-bg);color:var(--orange)}}.dt-blue{{background:var(--blue-bg);color:var(--blue)}}

    /* Due tags */
    .due-tag{{font-size:10px;font-weight:600;border-radius:5px;padding:2px 6px;flex-shrink:0;white-space:nowrap;margin-left:auto}}
    .due-red{{background:var(--red-bg);color:var(--red)}}.due-orange{{background:var(--orange-bg);color:var(--orange)}}.due-blue{{background:var(--blue-bg);color:var(--blue)}}

    /* Emails */
    .email-row{{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--border)}}
    .email-row:last-child{{border-bottom:none}}
    .email-row:hover{{background:rgba(0,0,0,0.02)}}
    .e-dot{{width:8px;height:8px;border-radius:50%;background:var(--blue);flex-shrink:0}}
    .e-dot-read{{background:transparent;border:1.5px solid var(--border2)}}
    .e-body{{flex:1;min-width:0}}
    .e-from{{font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .e-sub{{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:1px}}
    .e-time{{font-size:11px;color:var(--muted);flex-shrink:0;white-space:nowrap}}

    /* Dots + pills */
    .dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
    .dot-sm{{width:5px;height:5px;margin-top:8px}}
    .dot-orange{{background:var(--orange)}}.dot-blue{{background:var(--blue)}}
    .pill{{font-size:11px;font-weight:600;border-radius:6px;padding:2px 7px;flex-shrink:0}}
    .pill-gray{{background:#f2f2f7;color:var(--muted)}}.pill-orange{{background:var(--orange-bg);color:var(--orange)}}.pill-red{{background:var(--red-bg);color:var(--red)}}

    /* Projects */
    .proj-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:14px 15px;margin-bottom:8px;box-shadow:var(--shadow)}}
    .proj-hd{{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}}
    .proj-nm{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}}
    .task-ul{{list-style:none;display:flex;flex-direction:column;gap:9px}}
    .task-li{{display:flex;align-items:flex-start;gap:9px;border-radius:6px;padding:4px 6px;margin:-4px -6px}}
    .task-li:hover{{background:rgba(0,0,0,0.03)}}
    .task-text{{font-size:13px;line-height:1.5;flex:1}}

    /* Completed */
    details{{}}
    summary{{cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:7px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:9px;padding-left:2px}}
    summary::-webkit-details-marker{{display:none}}
    summary::after{{content:'';display:inline-block;width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-top:4px solid var(--muted);transition:transform .15s}}
    details[open] summary::after{{transform:rotate(180deg)}}
    .done-list{{display:flex;flex-direction:column;gap:5px;list-style:none}}
    .done-li{{display:flex;align-items:center;gap:8px;padding:9px 12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow)}}
    .done-li:hover{{background:rgba(0,0,0,0.02)}}
    .done-ck{{color:var(--green);font-size:12px;flex-shrink:0}}
    .done-txt{{font-size:13px;color:var(--subtle);text-decoration:line-through;flex:1}}
    .done-dt{{font-size:11px;color:var(--subtle);white-space:nowrap;flex-shrink:0}}

    .empty-p{{font-size:13px;color:var(--muted);padding:12px 15px;font-style:italic}}

    footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
    .ft-name{{font-size:12px;font-weight:600;color:var(--subtle)}}.ft-time{{font-size:11px;color:var(--subtle)}}

    /* ── Drawer overlay ── */
    .overlay{{position:fixed;inset:0;background:rgba(0,0,0,0);pointer-events:none;z-index:200;transition:background .2s}}
    .overlay.open{{background:rgba(0,0,0,0.28);pointer-events:all}}
    .drawer{{
      position:fixed;bottom:0;left:0;right:0;
      background:var(--surface);border-radius:20px 20px 0 0;
      padding:0 20px 32px;max-height:70vh;overflow-y:auto;
      z-index:201;transform:translateY(100%);transition:transform .28s cubic-bezier(.32,.72,0,1);
      box-shadow:0 -4px 32px rgba(0,0,0,0.12)
    }}
    .drawer.open{{transform:translateY(0)}}
    .drawer-handle{{width:36px;height:4px;background:var(--border2);border-radius:2px;margin:12px auto 18px}}
    .drawer-title{{font-size:16px;font-weight:700;letter-spacing:-.2px;margin-bottom:14px}}
    .drawer-line{{font-size:14px;line-height:1.6;color:var(--text);padding:6px 0;border-bottom:1px solid var(--border)}}
    .drawer-line:last-child{{border-bottom:none}}
    .drawer-line strong{{color:var(--text)}}
    .drawer-line em{{color:var(--muted);font-style:normal}}
    @media(min-width:640px){{
      .drawer{{bottom:auto;top:50%;left:50%;right:auto;transform:translate(-50%,-42%);width:400px;border-radius:18px;opacity:0;transition:opacity .18s,transform .18s;max-height:80vh;padding-bottom:24px}}
      .drawer.open{{transform:translate(-50%,-50%);opacity:1}}
      .drawer-handle{{display:none}}
    }}

    /* Responsive */
    @media(max-width:860px){{.top-row{{grid-template-columns:1fr 1fr}}}}
    @media(max-width:640px){{
      .kpi-strip{{grid-template-columns:repeat(2,1fr)}}
      .top-row{{grid-template-columns:1fr}}
      .main-row{{grid-template-columns:1fr}}
      .cal-grid{{grid-template-columns:1fr}}
    }}
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="hd-left">
      <div class="avatar">F</div>
      <div><div class="hd-name">Felix Janssen</div><div class="hd-sub">Second Brain</div></div>
    </div>
    <div class="hd-time">Updated {updated}</div>
  </div>

  <div class="kpi-strip">{kpi_html}</div>

  <div class="top-row">
    <div class="panel">
      <div class="p-lbl">Completed — last 14 days</div>
      <div class="spark-big">{spark_n}</div>
      <div class="spark-sub">tasks done</div>
      {spark_svg}
    </div>
    <div class="panel">
      <div class="p-lbl">Active by project</div>
      <div class="donut-wrap">
        <div class="donut-svg">{donut_svg}</div>
        <div class="leg">{legend_html}</div>
      </div>
    </div>
    <div class="panel">
      <div class="p-lbl">Calendar</div>
      {cal_html}
    </div>
  </div>

  <div class="main-row">
    <div>
      <div class="sec"><div class="sec-lbl">Active Tasks</div>{active_cards}</div>
      <div class="sec"><div class="sec-lbl">Blocked</div><div class="card">{blocked_rows}</div></div>
    </div>
    <div>
      <div class="sec"><div class="sec-lbl">Upcoming</div><div class="card">{deadline_rows}</div></div>
      <div class="sec"><div class="sec-lbl">Recent Emails</div><div class="card">{email_rows}</div></div>
    </div>
  </div>

  <div class="sec">
    <details>
      <summary>Completed &nbsp;({t_done})</summary>
      <ul class="done-list">{done_rows}</ul>
    </details>
  </div>

  <footer><span class="ft-name">felix.janssen</span><span class="ft-time">Updated {updated}</span></footer>

</div>

<!-- Drawer -->
<div class="overlay" id="overlay"></div>
<div class="drawer" id="drawer">
  <div class="drawer-handle"></div>
  <div class="drawer-title" id="drawer-title"></div>
  <div id="drawer-body"></div>
</div>

<script>
const PANEL_DATA = {panel_js};

const overlay = document.getElementById('overlay');
const drawer  = document.getElementById('drawer');
const dtitle  = document.getElementById('drawer-title');
const dbody   = document.getElementById('drawer-body');

function openDrawer(key) {{
  const data = PANEL_DATA[key];
  if (!data) return;
  dtitle.textContent = data.t;
  dbody.innerHTML = data.l.filter(Boolean).map(l => `<div class="drawer-line">${{l}}</div>`).join('');
  overlay.classList.add('open');
  drawer.classList.add('open');
}}

function closeDrawer() {{
  overlay.classList.remove('open');
  drawer.classList.remove('open');
}}

overlay.addEventListener('click', closeDrawer);
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeDrawer(); }});

document.addEventListener('click', e => {{
  if (e.target.closest('#drawer')) return;
  const el = e.target.closest('[data-key]');
  if (el && PANEL_DATA[el.dataset.key]) {{
    e.stopPropagation();
    openDrawer(el.dataset.key);
  }}
}});

// Swipe down to close on mobile
let startY = 0;
drawer.addEventListener('touchstart', e => {{ startY = e.touches[0].clientY; }}, {{passive:true}});
drawer.addEventListener('touchend', e => {{
  if (e.changedTouches[0].clientY - startY > 60) closeDrawer();
}}, {{passive:true}});
</script>
</body>
</html>"""


def main():
    if not TASKS_FILE.exists():
        print("ERROR: Tasks.md not found", file=sys.stderr); sys.exit(1)
    content   = TASKS_FILE.read_text(encoding="utf-8")
    live_data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
    active, blocked, completed = parse_tasks(content)
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(build_html(active, blocked, completed, live_data))
    print(f"Built: {OUTPUT_FILE}")
    print(f"  {sum(len(s['tasks']) for s in active)} active  |  {len(blocked)} blocked  |  {len(completed)} done")


if __name__ == "__main__":
    main()
