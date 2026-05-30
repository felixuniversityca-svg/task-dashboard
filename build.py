#!/usr/bin/env python3
"""
build.py -- reads Tasks.md + dashboard-data.json, generates public/index.html
Run locally: python3 build.py  |  Netlify build command: python3 build.py
"""
import json, re, sys, calendar as cal_mod
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
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None

def days_diff(d):
    return (date.today() - d).days if d else None

def rel_label(d, time_str=""):
    if not d:
        return ""
    t = f" {time_str}" if time_str else ""
    delta = (d - date.today()).days
    if delta < 0:   return f"{abs(delta)}d ago{t}"
    if delta == 0:  return f"Today{t}"
    if delta == 1:  return f"Tomorrow{t}"
    if delta <= 6:  return f"{d.strftime('%A')}{t}"
    return f"{d.strftime('%b %-d')}{t}"

def epoch_str(epoch):
    if not epoch:
        return ""
    dt = datetime.fromtimestamp(epoch)
    delta = (date.today() - dt.date()).days
    if delta == 0:  return dt.strftime("%-I:%M %p")
    if delta == 1:  return "Yesterday"
    if delta <= 6:  return dt.strftime("%A")
    return dt.strftime("%b %-d")


# ── Parse Tasks.md ────────────────────────────────────────────────────────────

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
            sec="active"; sub=None; tasks=[]; continue
        if s == "## Blocked":
            flush(); sub=None; sec="blocked"; continue
        if s == "## Completed":
            flush(); sub=None; sec="completed"; continue
        if s.startswith("## "):
            flush(); sec=None; continue
        if s.startswith("<!--") or s == "---" or not s:
            continue
        if sec == "active" and s.startswith("### "):
            flush(); sub=strip_wikilink(s[4:].strip()); tasks=[]; continue
        if sec == "active" and "- [ ]" in line:
            raw = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            due = None
            m = re.search(r"<!--\s*due:\s*(\d{4}-\d{2}-\d{2})\s*-->", raw)
            if m:
                due = parse_date(m.group(1))
                raw = raw[:m.start()].strip()
            if sub is None:
                sub="Other"; tasks=[]
            tasks.append({"text": strip_wikilink(raw), "due": due})
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


# ── Charts ────────────────────────────────────────────────────────────────────

def sparkline(completed, days=14):
    today = date.today()
    counts = defaultdict(int)
    for c in completed:
        if c["date"] and (today-c["date"]).days <= days:
            counts[c["date"]] += 1
    data = [counts[today-timedelta(days=i)] for i in range(days-1,-1,-1)]
    total = sum(data)
    mx = max(data) if max(data)>0 else 1
    W,H,gap = 260,44,2
    bw = (W - gap*(len(data)-1)) / len(data)
    bars = "".join(
        f'<rect x="{i*(bw+gap):.1f}" y="{H-max(3,int(v/mx*H))}" width="{bw:.1f}" height="{max(3,int(v/mx*H))}" rx="2" fill="{"#34c759" if v else "#e5e5ea"}"/>'
        for i,v in enumerate(data)
    )
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block">{bars}</svg>', total


def donut(active):
    counts = [(s["section"], len(s["tasks"])) for s in active if s["tasks"]]
    if not counts:
        return '<svg viewBox="0 0 72 72"><circle cx="36" cy="36" r="26" fill="none" stroke="#e5e5ea" stroke-width="10"/></svg>', []
    colors = ["#0071e3","#34c759","#ff9500","#af52de","#ff3b30"]
    total = sum(c for _,c in counts)
    circ = 2*3.14159265*26
    arcs,off,legend = "",0,[]
    for i,(name,cnt) in enumerate(counts):
        dash = (cnt/total)*circ
        arcs += (f'<circle cx="36" cy="36" r="26" fill="none" stroke="{colors[i%len(colors)]}" '
                 f'stroke-width="10" stroke-dasharray="{dash:.2f} {circ:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 36 36)"/>')
        legend.append({"name":name,"cnt":cnt,"color":colors[i%len(colors)]})
        off += dash
    return f'<svg viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">{arcs}</svg>', legend


def mini_calendar(deadlines, months=2):
    """Generate a compact calendar showing current + next month with event dots."""
    today = date.today()
    event_map = defaultdict(list)
    for dl in deadlines:
        d = parse_date(dl["date"])
        if d:
            event_map[d].append(dl["title"][:25])

    DAY_NAMES = ["M","T","W","T","F","S","S"]
    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    html = '<div class="cal-grid">'
    for mo in range(months):
        yr  = (today.replace(day=1) + timedelta(days=32*mo)).year
        mth = (today.replace(day=1) + timedelta(days=32*mo)).month
        first_day = date(yr, mth, 1)
        days_in_month = cal_mod.monthrange(yr, mth)[1]
        # Monday=0 offset
        start_offset = first_day.weekday()

        html += f'<div class="cal-month"><div class="cal-title">{MONTH_NAMES[mth-1]} {yr}</div>'
        html += '<div class="cal-days-hd">' + "".join(f'<span>{d}</span>' for d in DAY_NAMES) + '</div>'
        html += '<div class="cal-days">'

        # Empty cells before first day
        for _ in range(start_offset):
            html += '<div class="cal-cell cal-empty"></div>'

        for day in range(1, days_in_month + 1):
            d = date(yr, mth, day)
            is_today = d == today
            is_past  = d < today
            events   = event_map.get(d, [])
            cell_cls = "cal-cell"
            if is_today:  cell_cls += " cal-today"
            elif is_past: cell_cls += " cal-past"
            tooltip  = " ".join(events[:2]) if events else ""
            dots     = ""
            if events:
                delta = (d - today).days
                dot_col = "#ff3b30" if delta <= 1 else ("#ff9500" if delta <= 3 else "#0071e3")
                dots = f'<span class="cal-dot" style="background:{dot_col}"></span>'
            title_attr = f' title="{escape(tooltip)}"' if tooltip else ""
            html += f'<div class="{cell_cls}"{title_attr}><span class="cal-num">{day}</span>{dots}</div>'

        html += '</div></div>'

    html += '</div>'
    return html


# ── HTML ─────────────────────────────────────────────────────────────────────

def build_html(active, blocked, completed, live_data):
    today    = date.today()
    t_active = sum(len(s["tasks"]) for s in active)
    t_block  = len(blocked)
    t_done   = len(completed)
    done_wk  = sum(1 for c in completed if c["date"] and (today-c["date"]).days<=7)
    oldest   = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    spark_svg, spark_n = sparkline(completed)
    donut_svg, legend  = donut(active)
    emails    = live_data.get("emails", [])
    deadlines = live_data.get("deadlines", [])
    cal_html  = mini_calendar(deadlines, months=2)
    updated   = datetime.now().strftime("%b %-d at %H:%M")

    # KPI
    def kpi(val, lbl, cls=""):
        return f'<div class="kpi-card {cls}"><div class="kpi-val">{val}</div><div class="kpi-lbl">{lbl}</div></div>'
    kpi_html = (
        kpi(t_active, "Active", "kpi-blue") +
        kpi(t_block,  "Blocked", "kpi-orange" if t_block else "") +
        kpi(done_wk,  "Done this week", "kpi-green") +
        kpi(f"{oldest}d" if oldest else "None", "Oldest block", "kpi-red" if oldest>=14 else ("kpi-orange" if oldest>=3 else ""))
    )

    # Deadlines
    deadline_rows = ""
    for dl in deadlines:
        d = parse_date(dl["date"])
        if d and (d - today).days < 0:
            continue
        lbl   = rel_label(d, dl.get("time",""))
        delta = (d - today).days if d else 99
        dt_cls = "dt-red" if delta<=1 else ("dt-orange" if delta<=3 else "dt-blue")
        deadline_rows += (
            f'<div class="list-row">'
            f'<span class="dt-badge {dt_cls}">{escape(lbl)}</span>'
            f'<span class="list-text">{escape(dl["title"])}</span>'
            f'</div>'
        )
    if not deadline_rows:
        deadline_rows = '<p class="empty-p">No upcoming deadlines.</p>'

    # Emails
    email_rows = ""
    for em in emails:
        dot = '<span class="e-dot"></span>' if em.get("unread") else '<span class="e-dot e-dot-read"></span>'
        email_rows += (
            f'<div class="email-row">{dot}'
            f'<div class="e-body">'
            f'<div class="e-from">{escape(em["from"][:28])}</div>'
            f'<div class="e-sub">{escape(em["subject"][:55])}</div>'
            f'</div>'
            f'<div class="e-time">{escape(epoch_str(em.get("epoch",0)))}</div>'
            f'</div>'
        )
    if not email_rows:
        email_rows = '<p class="empty-p">No recent emails.</p>'

    # Blocked
    blocked_rows = ""
    for b in sorted(blocked, key=lambda x: x["days"] or 0, reverse=True):
        d = b["days"]
        if d is not None and d >= 14:   pill_cls,plbl = "pill-red",   f"{d}d"
        elif d is not None and d >= 3:  pill_cls,plbl = "pill-orange", f"{d}d"
        else:                           pill_cls,plbl = "pill-gray",   f"{d or 0}d"
        since_lbl = f'Since {b["since_date"].strftime("%b %-d")}' if b["since_date"] else ""
        waiting_html = f'<div class="list-sub">Waiting on {escape(b["waiting"])}{" · " + since_lbl if since_lbl else ""}</div>' if b["waiting"] else ""
        blocked_rows += (
            f'<div class="list-row">'
            f'<span class="dot dot-orange"></span>'
            f'<span class="list-text" style="flex:1">{escape(b["task"])}</span>'
            f'<span class="pill {pill_cls}">{plbl}</span>'
            f'</div>'
            f'{waiting_html}'
        )
    if not blocked_rows:
        blocked_rows = '<p class="empty-p">Nothing blocked.</p>'

    # Active
    active_cards = ""
    for sec in active:
        if not sec["tasks"]: continue
        rows = ""
        for t in sec["tasks"]:
            due_html = ""
            if t["due"]:
                delta = (t["due"] - today).days
                d_cls = "due-red" if delta<=1 else ("due-orange" if delta<=3 else "due-blue")
                due_html = f'<span class="due-tag {d_cls}">{rel_label(t["due"])}</span>'
            rows += (f'<li class="task-li">'
                     f'<span class="dot dot-blue dot-sm"></span>'
                     f'<span class="task-text">{escape(t["text"])}</span>'
                     f'{due_html}</li>')
        active_cards += (
            f'<div class="proj-card">'
            f'<div class="proj-hd"><span class="proj-nm">{escape(sec["section"])}</span>'
            f'<span class="pill pill-gray">{len(sec["tasks"])}</span></div>'
            f'<ul class="task-ul">{rows}</ul></div>'
        )
    if not active_cards:
        active_cards = '<p class="empty-p">No active tasks.</p>'

    # Legend
    legend_html = "".join(
        f'<div class="leg-row"><span class="leg-dot" style="background:{l["color"]}"></span>'
        f'<span class="leg-name">{escape(l["name"])}</span><span class="leg-n">{l["cnt"]}</span></div>'
        for l in legend
    ) or '<p class="empty-p" style="font-size:12px">No active projects</p>'

    # Completed
    done_rows = "".join(
        f'<li class="done-li"><span class="done-ck">✓</span>'
        f'<span class="done-txt">{escape(c["task"])}</span>'
        f'{"<span class=done-dt>" + c["date"].strftime("%b %-d") + "</span>" if c["date"] else ""}'
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
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    :root{{
      --bg:#f5f5f7;--surface:#fff;--border:rgba(0,0,0,0.08);--border2:rgba(0,0,0,0.12);
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

    /* KPI strip */
    .kpi-strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px}}
    .kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 15px;box-shadow:var(--shadow)}}
    .kpi-blue{{background:var(--blue-bg);border-color:var(--blue-bdr)}}
    .kpi-green{{background:var(--green-bg);border-color:var(--green-bdr)}}
    .kpi-orange{{background:var(--orange-bg);border-color:var(--orange-bdr)}}
    .kpi-red{{background:var(--red-bg);border-color:var(--red-bdr)}}
    .kpi-val{{font-size:28px;font-weight:700;letter-spacing:-.8px;line-height:1;margin-bottom:4px}}
    .kpi-blue .kpi-val{{color:var(--blue)}}.kpi-green .kpi-val{{color:var(--green)}}
    .kpi-orange .kpi-val{{color:var(--orange)}}.kpi-red .kpi-val{{color:var(--red)}}
    .kpi-lbl{{font-size:11px;font-weight:500;color:var(--muted)}}

    /* Top row: spark + donut + calendar */
    .top-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:18px}}
    .panel{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px;box-shadow:var(--shadow)}}
    .panel.double{{grid-column:span 2}}
    .p-lbl{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:12px}}
    .spark-big{{font-size:28px;font-weight:700;color:var(--green);letter-spacing:-.8px;line-height:1}}
    .spark-sub{{font-size:11px;color:var(--muted);margin:3px 0 14px}}
    .donut-wrap{{display:flex;align-items:center;gap:14px}}
    .donut-svg{{width:72px;height:72px;flex-shrink:0}}
    .leg{{display:flex;flex-direction:column;gap:8px;flex:1;min-width:0}}
    .leg-row{{display:flex;align-items:center;gap:8px}}
    .leg-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
    .leg-name{{font-size:12px;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .leg-n{{font-size:12px;font-weight:600;color:var(--muted)}}

    /* Mini calendar */
    .cal-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
    .cal-month{{}}
    .cal-title{{font-size:12px;font-weight:700;color:var(--text);margin-bottom:8px;letter-spacing:-.2px}}
    .cal-days-hd{{display:grid;grid-template-columns:repeat(7,1fr);margin-bottom:4px}}
    .cal-days-hd span{{font-size:9px;font-weight:600;text-align:center;color:var(--subtle);padding:2px 0}}
    .cal-days{{display:grid;grid-template-columns:repeat(7,1fr);gap:1px}}
    .cal-cell{{display:flex;flex-direction:column;align-items:center;padding:3px 1px;border-radius:5px;cursor:default;min-height:26px}}
    .cal-today .cal-num{{background:var(--blue);color:#fff;border-radius:50%;width:18px;height:18px;display:flex;align-items:center;justify-content:center}}
    .cal-past .cal-num{{color:var(--subtle)}}
    .cal-num{{font-size:10px;font-weight:500;line-height:1.6}}
    .cal-dot{{width:4px;height:4px;border-radius:50%;margin-top:1px}}
    .cal-empty{{}}

    /* Main two-column layout */
    .main-row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}}

    /* Reusable card + list */
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden;margin-bottom:0}}
    .sec{{margin-bottom:18px}}
    .sec-lbl{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:9px;padding-left:2px}}
    .list-row{{display:flex;align-items:center;gap:10px;padding:11px 15px;border-bottom:1px solid var(--border)}}
    .list-row:last-child{{border-bottom:none}}
    .list-text{{font-size:13px;line-height:1.4;flex:1}}
    .list-sub{{font-size:11px;color:var(--muted);padding:0 15px 10px 35px;border-bottom:1px solid var(--border)}}
    .list-sub:last-child{{border-bottom:none}}

    /* Date badges in deadline list */
    .dt-badge{{font-size:10px;font-weight:700;border-radius:5px;padding:2px 7px;flex-shrink:0;white-space:nowrap}}
    .dt-red{{background:var(--red-bg);color:var(--red)}}
    .dt-orange{{background:var(--orange-bg);color:var(--orange)}}
    .dt-blue{{background:var(--blue-bg);color:var(--blue)}}

    /* Due tags on tasks */
    .due-tag{{font-size:10px;font-weight:600;border-radius:5px;padding:2px 6px;flex-shrink:0;white-space:nowrap;margin-left:auto}}
    .due-red{{background:var(--red-bg);color:var(--red)}}
    .due-orange{{background:var(--orange-bg);color:var(--orange)}}
    .due-blue{{background:var(--blue-bg);color:var(--blue)}}

    /* Emails */
    .email-row{{display:flex;align-items:center;gap:10px;padding:11px 15px;border-bottom:1px solid var(--border)}}
    .email-row:last-child{{border-bottom:none}}
    .e-dot{{width:8px;height:8px;border-radius:50%;background:var(--blue);flex-shrink:0}}
    .e-dot-read{{background:transparent;border:1.5px solid var(--border2)}}
    .e-body{{flex:1;min-width:0}}
    .e-from{{font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .e-sub{{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:1px}}
    .e-time{{font-size:11px;color:var(--muted);flex-shrink:0;white-space:nowrap}}

    /* Dots */
    .dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
    .dot-sm{{width:5px;height:5px;margin-top:8px}}
    .dot-orange{{background:var(--orange)}}
    .dot-blue{{background:var(--blue)}}

    /* Pills */
    .pill{{font-size:11px;font-weight:600;border-radius:6px;padding:2px 7px;flex-shrink:0}}
    .pill-gray{{background:#f2f2f7;color:var(--muted)}}
    .pill-orange{{background:var(--orange-bg);color:var(--orange)}}
    .pill-red{{background:var(--red-bg);color:var(--red)}}

    /* Project cards */
    .proj-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:14px 15px;margin-bottom:8px;box-shadow:var(--shadow)}}
    .proj-hd{{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}}
    .proj-nm{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}}
    .task-ul{{list-style:none;display:flex;flex-direction:column;gap:9px}}
    .task-li{{display:flex;align-items:flex-start;gap:9px}}
    .task-text{{font-size:13px;line-height:1.5;flex:1}}

    /* Completed */
    details{{}}
    summary{{cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:7px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:9px;padding-left:2px}}
    summary::-webkit-details-marker{{display:none}}
    summary::after{{content:'';display:inline-block;width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-top:4px solid var(--muted);transition:transform .15s}}
    details[open] summary::after{{transform:rotate(180deg)}}
    .done-list{{display:flex;flex-direction:column;gap:5px;list-style:none}}
    .done-li{{display:flex;align-items:center;gap:8px;padding:9px 12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow)}}
    .done-ck{{color:var(--green);font-size:12px;flex-shrink:0}}
    .done-txt{{font-size:13px;color:var(--subtle);text-decoration:line-through;flex:1}}
    .done-dt{{font-size:11px;color:var(--subtle);white-space:nowrap;flex-shrink:0}}

    .empty-p{{font-size:13px;color:var(--muted);padding:12px 15px;font-style:italic}}

    footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
    .ft-name{{font-size:12px;font-weight:600;color:var(--subtle)}}
    .ft-time{{font-size:11px;color:var(--subtle)}}

    /* Responsive */
    @media(max-width:860px){{
      .top-row{{grid-template-columns:1fr 1fr}}
      .panel.double{{grid-column:span 2}}
    }}
    @media(max-width:640px){{
      .kpi-strip{{grid-template-columns:repeat(2,1fr)}}
      .top-row{{grid-template-columns:1fr}}
      .panel.double{{grid-column:span 1}}
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
      <div class="sec">
        <div class="sec-lbl">Active Tasks</div>
        {active_cards}
      </div>
      <div class="sec">
        <div class="sec-lbl">Blocked</div>
        <div class="card">{blocked_rows}</div>
      </div>
    </div>
    <div>
      <div class="sec">
        <div class="sec-lbl">Upcoming</div>
        <div class="card">{deadline_rows}</div>
      </div>
      <div class="sec">
        <div class="sec-lbl">Recent Emails</div>
        <div class="card">{email_rows}</div>
      </div>
    </div>
  </div>

  <div class="sec">
    <details>
      <summary>Completed &nbsp;({t_done})</summary>
      <ul class="done-list">{done_rows}</ul>
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
