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
    return re.sub(r"\[\[([^\]]+)\]\]",
                  lambda m: m.group(1).split("|")[-1] if "|" in m.group(1) else m.group(1), t)

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
    return re.sub(r"\s+", " ", html_mod.unescape(s or "")).strip()[:180]

# ── Panel helpers ─────────────────────────────────────────────────────────────

def panel(title, rows, subtitle="", color="#0071e3", note=""):
    """Build a structured panel dict for the drawer."""
    return {"t": title, "sub": subtitle, "color": color,
            "rows": [r for r in rows if r], "note": note}

def row(k, v, hl=""):
    """Key-value row. hl = red/orange/green/blue for value highlight."""
    if not v: return None
    return {"k": k, "v": str(v), "hl": hl}

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
        if s == "## Active":    sec="active";  sub=None; tasks=[]; continue
        if s == "## Blocked":   flush(); sub=None; sec="blocked";   continue
        if s == "## Completed": flush(); sub=None; sec="completed"; continue
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
            tasks.append({"text": strip_wikilink(raw), "due": due}); continue
        if sec == "blocked" and "- [ ]" in line:
            raw = re.sub(r"^[\s-]+\[ \]\s*", "", line).strip()
            waiting=since=""
            m = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+?)\s+--\s+since\s+(.+)$", raw)
            if m: raw,waiting,since = m.group(1).strip(),m.group(2).strip(),m.group(3).strip()
            else:
                m2 = re.match(r"^(.+?)\s+--\s+waiting:\s+(.+)$", raw)
                if m2: raw,waiting = m2.group(1).strip(),m2.group(2).strip()
            sd = parse_date(since)
            blocked.append({"task":strip_wikilink(raw),"waiting":waiting,
                            "since_date":sd,"days":days_diff(sd)}); continue
        if sec == "completed" and re.match(r"^[\s-]+\[[xX]\]", line):
            raw = re.sub(r"^[\s-]+\[[xX]\]\s*", "", line).strip()
            d = None
            m = re.search(r"✅\s*(\d{4}-\d{2}-\d{2})", raw)
            if m: d=parse_date(m.group(1)); raw=raw[:m.start()].strip()
            completed.append({"task":strip_wikilink(raw),"date":d}); continue
    flush()
    return active, blocked, completed

# ── Charts ────────────────────────────────────────────────────────────────────

def sparkline(completed, days=14):
    today = date.today()
    day_tasks = defaultdict(list)
    for c in completed:
        if c["date"] and (today-c["date"]).days <= days:
            day_tasks[c["date"]].append(c["task"])
    data = [(today-timedelta(days=i), day_tasks[today-timedelta(days=i)])
            for i in range(days-1,-1,-1)]
    mx = max((len(t) for _,t in data), default=1) or 1
    W,H,gap = 260,44,2
    bw = (W - gap*(len(data)-1)) / len(data)
    bars = ""
    for i,(d,tasks) in enumerate(data):
        v = len(tasks)
        bh = max(3, int(v/mx*H))
        fill = "#34c759" if v else "#e5e5ea"
        bars += (f'<rect data-key="spark-{i}" class="spark-bar" '
                 f'x="{i*(bw+gap):.1f}" y="{H-bh}" width="{bw:.1f}" height="{bh}" rx="2" '
                 f'fill="{fill}" style="cursor:pointer;animation-delay:{i*28}ms"/>')
    svg = (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="width:100%;display:block">{bars}</svg>')
    return svg, sum(len(t) for _,t in data), data

def donut_chart(active):
    counts = [(s["section"], len(s["tasks"]), s["tasks"]) for s in active if s["tasks"]]
    if not counts:
        return ('<svg viewBox="0 0 72 72"><circle cx="36" cy="36" r="26" fill="none" '
                'stroke="#e5e5ea" stroke-width="10"/></svg>'), []
    colors = ["#0071e3","#34c759","#ff9500","#af52de","#ff3b30"]
    total  = sum(c for _,c,_ in counts)
    circ   = 2*3.14159265*26
    arcs,off,legend = "",0,[]
    for i,(name,cnt,tasks) in enumerate(counts):
        dash = (cnt/total)*circ
        arcs += (f'<circle data-key="donut-{i}" cx="36" cy="36" r="26" fill="none" '
                 f'stroke="{colors[i%len(colors)]}" stroke-width="10" '
                 f'stroke-dasharray="{dash:.2f} {circ:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 36 36)" '
                 f'style="cursor:pointer"/>')
        legend.append({"name":name,"cnt":cnt,"color":colors[i%len(colors)],
                       "tasks":tasks,"idx":i})
        off += dash
    return f'<svg viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">{arcs}</svg>', legend

def mini_calendar(deadlines, active_all, completed_all, months=2):
    today = date.today()
    event_map = defaultdict(list)
    for dl in deadlines:
        d = parse_date(dl["date"])
        if d: event_map[d].append(("deadline", dl["title"]))
    for sec in active_all:
        for t in sec["tasks"]:
            if t["due"]: event_map[t["due"]].append(("task", t["text"]))
    for c in completed_all:
        if c["date"]: event_map[c["date"]].append(("done", c["task"]))

    DAY_NAMES   = ["M","T","W","T","F","S","S"]
    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]

    html = '<div class="cal-grid">'
    for mo in range(months):
        d0  = today.replace(day=1) + timedelta(days=32*mo)
        yr,mth = d0.year, d0.month
        first  = date(yr,mth,1)
        dim    = cal_mod.monthrange(yr,mth)[1]
        html  += (f'<div class="cal-month">'
                  f'<div class="cal-title">{MONTH_NAMES[mth-1]} {yr}</div>'
                  f'<div class="cal-days-hd">'
                  + "".join(f'<span>{d}</span>' for d in DAY_NAMES)
                  + '</div><div class="cal-days">')
        for _ in range(first.weekday()):
            html += '<div class="cal-cell cal-empty"></div>'
        for day in range(1, dim+1):
            d = date(yr,mth,day)
            events = event_map.get(d,[])
            is_today = d==today; is_past = d<today
            cls = ("cal-cell"
                   + (" cal-today" if is_today else " cal-past" if is_past else "")
                   + (" cal-has-ev" if events else ""))
            if events:
                delta = (d-today).days
                dcol  = "#ff3b30" if delta<=1 else ("#ff9500" if delta<=3 else "#0071e3")
                dot   = f'<span class="cal-dot" style="background:{dcol}"></span>'
                html += (f'<div class="{cls}" data-key="cal-{d.isoformat()}">'
                         f'<span class="cal-num">{day}</span>{dot}</div>')
            else:
                html += f'<div class="{cls}"><span class="cal-num">{day}</span></div>'
        html += '</div></div>'
    html += '</div>'
    return html, event_map


def hourly_calendar_html(agenda, deadlines, today):
    """Hour-by-hour day view. Falls back to timestamped list if <2 timed events."""
    START_H, END_H, SLOT_H = 8, 22, 44
    total_px = (END_H - START_H) * SLOT_H

    events = []
    for ev in (agenda or []):
        mt = re.match(r"(\d{1,2}):(\d{2})", ev.get("time", ""))
        if mt:
            h, mn = int(mt.group(1)), int(mt.group(2))
            if START_H <= h < END_H:
                events.append({"title": ev["title"], "h": h, "mn": mn,
                               "color": "#0071e3", "bg": "var(--blue-bg)"})
    for dl in (deadlines or []):
        if dl.get("time") and parse_date(dl.get("date", "")) == today:
            mt = re.match(r"(\d{1,2}):(\d{2})", dl["time"])
            if mt:
                h, mn = int(mt.group(1)), int(mt.group(2))
                if START_H <= h < END_H:
                    events.append({"title": dl["title"], "h": h, "mn": mn,
                                  "color": "#ff3b30", "bg": "var(--red-bg)"})

    # ── Full grid (always — blank grid is cleaner than a message) ────────────
    rows_h = ""
    for h in range(START_H, END_H + 1):
        top = (h - START_H) * SLOT_H
        lbl = f"{h%12 or 12}{'am' if h<12 else 'pm'}"
        rows_h += (f'<div class="dc-hrow" style="top:{top}px">'
                   f'<span class="dc-hlbl">{lbl}</span>'
                   f'<div class="dc-hline"></div></div>')
    ev_h = ""
    for ev in events:
        top = (ev["h"] - START_H + ev["mn"]/60) * SLOT_H
        ev_h += (f'<div class="dc-ev" style="top:{top:.1f}px;'
                 f'border-left-color:{ev["color"]};background:{ev["bg"]}">'
                 f'<span class="dc-ev-t">{ev["h"]:02d}:{ev["mn"]:02d}</span>'
                 f'<span class="dc-ev-n">{escape(ev["title"][:38])}</span></div>')
    return (f'<div class="dc-outer" id="dc-outer">'
            f'<div style="height:{total_px}px;position:relative;padding-left:44px">'
            f'{rows_h}'
            f'<div style="position:absolute;left:44px;right:0;top:0;bottom:0">'
            f'<div class="dc-now" id="dc-now"></div>{ev_h}</div></div></div>')


# ── Panel Data ────────────────────────────────────────────────────────────────

def build_panels(active, blocked, completed, live_data, spark_data, legend, event_map):
    today    = date.today()
    pd       = {}
    deadlines = live_data.get("deadlines", [])
    emails    = live_data.get("emails", [])

    # KPI — Active
    proj_lines = [f"{s['section']}: {len(s['tasks'])} task{'s' if len(s['tasks'])!=1 else ''}"
                  for s in active if s["tasks"]]
    pd["kpi-active"] = panel(
        "Active Tasks",
        [row("Total open", f"{sum(len(s['tasks']) for s in active)} tasks"),
         *[row(s["section"], f"{len(s['tasks'])} task{'s' if len(s['tasks'])!=1 else ''}") for s in active if s["tasks"]]],
        subtitle="All open work across your projects",
        color="#0071e3"
    )

    # KPI — Blocked
    if blocked:
        pd["kpi-blocked"] = panel(
            "Blocked Tasks",
            [row(b["task"][:40], f"{b['days']}d waiting" if b["days"] is not None else "waiting",
                 "red" if (b["days"] or 0)>=14 else "orange") for b in blocked],
            subtitle=f"{len(blocked)} tasks waiting on external dependencies",
            color="#ff9500"
        )
    else:
        pd["kpi-blocked"] = panel("Blocked Tasks",
            [row("Status", "Nothing blocked right now", "green")],
            subtitle="All clear", color="#34c759")

    # KPI — Done this week
    done_wk = [c for c in completed if c["date"] and (today-c["date"]).days<=7]
    pd["kpi-week"] = panel(
        "Done This Week",
        [row("Total", f"{len(done_wk)} tasks completed"),
         *[row(c["date"].strftime("%b %-d"), c["task"][:45]) for c in done_wk[:6]]],
        subtitle=f"Last 7 days · {len(done_wk)} tasks",
        color="#34c759"
    )

    # KPI — Oldest block
    oldest = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    if oldest > 0 and blocked:
        ob = max(blocked, key=lambda b: b["days"] or 0)
        pd["kpi-oldest"] = panel(
            "Oldest Blocker",
            [row("Task",         ob["task"][:50]),
             row("Waiting on",   ob["waiting"][:50]),
             row("Blocked since",ob["since_date"].strftime("%A, %b %-d") if ob["since_date"] else "unknown"),
             row("Duration",     f"{ob['days']} days", "red" if ob["days"]>=14 else "orange")],
            subtitle=f"{oldest} days — needs a decision",
            color="#ff3b30" if oldest>=14 else "#ff9500"
        )
    else:
        pd["kpi-oldest"] = panel("Oldest Blocker",
            [row("Status","No blockers — clear runway","green")], color="#34c759")

    # Sparkline bars
    for i,(d,tasks) in enumerate(spark_data):
        if tasks:
            pd[f"spark-{i}"] = panel(
                d.strftime("%A, %B %-d"),
                [row("Tasks completed", str(len(tasks)), "green"),
                 *[row(f"#{j+1}", t[:55]) for j,t in enumerate(tasks[:6])]],
                subtitle=f"{len(tasks)} task{'s' if len(tasks)!=1 else ''} done",
                color="#34c759"
            )
        else:
            pd[f"spark-{i}"] = panel(
                d.strftime("%A, %B %-d"),
                [row("Status","No tasks completed this day")],
                color="#aeaeb2"
            )

    # Donut segments
    for l in legend:
        pd[f"donut-{l['idx']}"] = panel(
            l["name"],
            [row("Open tasks", str(l["cnt"]), "blue"),
             *[row(f"  {j+1}.", t["text"][:55]) for j,t in enumerate(l["tasks"][:6])]],
            subtitle=f"{l['cnt']} task{'s' if l['cnt']!=1 else ''} in progress",
            color=l["color"]
        )

    # Calendar days
    for d, events in event_map.items():
        rows_cal = []
        for kind, title in events:
            icon = "Deadline" if kind=="deadline" else ("Completed" if kind=="done" else "Due")
            hl   = "red" if kind=="deadline" else ("green" if kind=="done" else "blue")
            rows_cal.append(row(icon, title[:55], hl))
        pd[f"cal-{d.isoformat()}"] = panel(
            d.strftime("%A, %B %-d"),
            rows_cal,
            subtitle=f"{len(events)} event{'s' if len(events)!=1 else ''}",
            color="#0071e3"
        )

    # Deadlines
    for i,dl in enumerate(deadlines):
        d = parse_date(dl["date"])
        lbl = rel_label(d, dl.get("time",""))
        delta = (d-today).days if d else 99
        hl = "red" if delta<=1 else ("orange" if delta<=3 else "blue")
        pd[f"deadline-{i}"] = panel(
            dl["title"][:60],
            [row("When",  lbl, hl),
             row("Date",  dl["date"] + (f" at {dl['time']}" if dl.get("time") else "")),
             row("In",    f"{delta} day{'s' if delta!=1 else ''}" if delta>=0 else "Past due", hl)],
            subtitle="Upcoming deadline",
            color="#ff3b30" if delta<=1 else ("#ff9500" if delta<=3 else "#0071e3")
        )

    # Emails
    for i,em in enumerate(emails):
        snippet = clean_snippet(em.get("snippet",""))
        pd[f"email-{i}"] = panel(
            em["from"][:40],
            [row("Subject", em["subject"][:60]),
             row("Preview", snippet[:120] if snippet else "(no preview)"),
             row("Received", epoch_str(em.get("epoch",0))),
             row("Status",  "Unread" if em.get("unread") else "Read",
                 "blue" if em.get("unread") else "")],
            subtitle="Email",
            color="#0071e3"
        )

    # Blocked
    for i,b in enumerate(blocked):
        since_str = b["since_date"].strftime("%A, %b %-d") if b["since_date"] else "unknown"
        days_str  = f"{b['days']} day{'s' if (b['days'] or 0)!=1 else ''}" if b["days"] is not None else "unknown"
        hl = "red" if (b["days"] or 0)>=14 else ("orange" if (b["days"] or 0)>=3 else "")
        pd[f"blocked-{i}"] = panel(
            b["task"][:60],
            [row("Waiting on", b["waiting"][:60] if b["waiting"] else "Not specified"),
             row("Blocked since", since_str),
             row("Duration", days_str, hl),
             row("Action needed", "Escalate or re-scope" if (b["days"] or 0)>=7 else "Follow up soon" if (b["days"] or 0)>=3 else "Monitor")],
            subtitle="Blocked task",
            color="#ff3b30" if (b["days"] or 0)>=14 else "#ff9500"
        )

    # Active tasks
    for si,sec in enumerate(active):
        for ti,t in enumerate(sec["tasks"]):
            due_str = rel_label(t["due"]) if t["due"] else "No deadline set"
            delta   = (t["due"]-today).days if t["due"] else None
            due_hl  = "red" if delta is not None and delta<=1 else ("orange" if delta is not None and delta<=3 else "blue" if t["due"] else "")
            pd[f"active-{si}-{ti}"] = panel(
                t["text"][:60],
                [row("Project", sec["section"]),
                 row("Due",     due_str, due_hl),
                 row("Status",  "Overdue" if delta is not None and delta<0 else "Due soon" if delta is not None and delta<=3 else "On track",
                     "red" if delta is not None and delta<0 else "orange" if delta is not None and delta<=3 else "green")],
                subtitle=f"Active · {sec['section']}",
                color="#0071e3"
            )

    # Completed
    for i,c in enumerate(reversed(completed)):
        date_str = c["date"].strftime("%A, %B %-d") if c["date"] else "Date not recorded"
        pd[f"done-{i}"] = panel(
            c["task"][:60],
            [row("Completed", date_str, "green"),
             row("Days ago",  str(days_diff(c["date"])) if c["date"] else "unknown")],
            subtitle="Completed task",
            color="#34c759"
        )

    return pd

# ── Build HTML ────────────────────────────────────────────────────────────────

def build_html(active, blocked, completed, live_data):
    today      = date.today()
    t_active   = sum(len(s["tasks"]) for s in active)
    t_block    = len(blocked)
    t_done     = len(completed)
    done_wk    = sum(1 for c in completed if c["date"] and (today-c["date"]).days<=7)
    oldest     = max((b["days"] for b in blocked if b["days"] is not None), default=0)
    spark_svg, spark_n, spark_data = sparkline(completed)
    donut_svg, legend   = donut_chart(active)
    deadlines  = live_data.get("deadlines", [])
    emails     = live_data.get("emails", [])
    pipeline   = live_data.get("pipeline", [])
    replies    = live_data.get("replies", [])
    agenda     = live_data.get("agenda", [])
    cal_html, event_map = mini_calendar(deadlines, active, completed, months=2)
    updated    = datetime.now().strftime("%b %-d at %H:%M")
    build_epoch = int(datetime.now().timestamp())
    hourly_cal  = hourly_calendar_html(agenda, deadlines, today)
    # Velocity stats (done_today also used later by weekly progress bar)
    done_today  = sum(1 for c in completed if c["date"] and (today-c["date"]).days == 0)
    done_2wk    = sum(1 for c in completed if c["date"] and (today-c["date"]).days <= 14)
    daily_avg   = round(done_2wk / 14, 1)
    unread_count= sum(1 for e in emails if e.get("unread"))
    # Pipeline pills
    stage_seen  = {}
    for a in pipeline:
        s = a.get("stage","")
        if s not in stage_seen:
            stage_seen[s] = {"count": 0, "color": a["color"], "label": a["label"]}
        stage_seen[s]["count"] += 1
    pipeline_pills = "".join(
        f'<span class="act-pill" style="background:{v["color"]}22;color:{v["color"]}">'
        f'{v["count"]} {v["label"]}</span>'
        for v in stage_seen.values()
    ) if stage_seen else '<span style="font-size:12px;color:var(--muted)">No articles</span>'
    # Velocity delta label
    vel_color  = "vel-green" if done_today >= daily_avg else "vel-muted"
    vel_delta  = done_today - daily_avg
    vel_sign   = "+" if vel_delta >= 0 else ""
    vel_trend  = f"{vel_sign}{vel_delta:.1f} vs avg"
    # Weekly stats for progress bar
    done_last_wk = sum(1 for c in completed if c["date"] and 7 < (today-c["date"]).days <= 14)
    done_today   = sum(1 for c in completed if c["date"] and (today-c["date"]).days == 0)
    # Session status bar
    fetched_at = live_data.get("fetched_at", "")
    try:
        sync_dt     = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M")
        minutes_ago = max(int((datetime.now() - sync_dt).total_seconds() / 60), 0)
    except Exception:
        minutes_ago = 0
    if minutes_ago < 15:
        sb_label = "Session active"; sb_color = "#34c759"
    elif minutes_ago < 45:
        sb_label = f"Session cooling · {minutes_ago}m ago"; sb_color = "#ff9500"
    else:
        sb_label = f"Session idle · {minutes_ago // 60}h {minutes_ago % 60}m ago"; sb_color = "#aeaeb2"
    sb_pct = max(100 - int(minutes_ago * 1.2), 4)  # battery-style: drains over ~80 min
    panels     = build_panels(active, blocked, completed, live_data,
                              spark_data, legend, event_map)
    panels_js  = json.dumps(panels, ensure_ascii=False)

    # KPI
    def kpi(val, lbl, cls, key, tip, countup=None):
        cu = f' data-countup="{countup}"' if countup is not None else ""
        return (f'<div class="kpi-card {cls} interactive" data-key="{key}" '
                f'data-tip="{escape(tip)}">'
                f'<div class="kpi-val"{cu}>{val}</div>'
                f'<div class="kpi-lbl">{escape(lbl)}</div></div>')
    kpi_html = (
        kpi(t_active, "Active",         "kpi-blue",                              "kpi-active",  "Tap for breakdown", t_active) +
        kpi(t_block,  "Blocked",        "kpi-orange" if t_block else "",         "kpi-blocked", "Tap for details",   t_block) +
        kpi(done_wk,  "Done this week", "kpi-green",                             "kpi-week",    "Tap to see tasks",  done_wk) +
        kpi(f"{oldest}d" if oldest else "None", "Oldest block",
            "kpi-red" if oldest>=14 else ("kpi-orange" if oldest>=3 else ""),    "kpi-oldest",  "Tap for details")
    )

    # Deadlines
    deadline_rows = ""
    for i,dl in enumerate(deadlines):
        d = parse_date(dl["date"])
        if d and (d-today).days < 0: continue
        lbl   = rel_label(d, dl.get("time",""))
        delta = (d-today).days if d else 99
        dt_cls = "dt-red" if delta<=1 else ("dt-orange" if delta<=3 else "dt-blue")
        deadline_rows += (f'<div class="list-row interactive" data-key="deadline-{i}">'
                          f'<span class="dt-badge {dt_cls}">{escape(lbl)}</span>'
                          f'<span class="list-text">{escape(dl["title"])}</span>'
                          f'<span class="chevron">›</span></div>')
    if not deadline_rows:
        deadline_rows = '<p class="empty-p">No upcoming deadlines.</p>'

    # Emails
    email_rows = ""
    for i,em in enumerate(emails):
        dot = ('<span class="e-dot"></span>' if em.get("unread")
               else '<span class="e-dot e-dot-read"></span>')
        email_rows += (f'<div class="email-row interactive" data-key="email-{i}">{dot}'
                       f'<div class="e-body">'
                       f'<div class="e-from">{escape(em["from"][:28])}</div>'
                       f'<div class="e-sub">{escape(em["subject"][:50])}</div>'
                       f'</div>'
                       f'<div class="e-time">{escape(epoch_str(em.get("epoch",0)))}</div>'
                       f'<span class="chevron">›</span></div>')
    if not email_rows:
        email_rows = '<p class="empty-p">No recent emails.</p>'

    # Blocked
    blocked_rows = ""
    for i,b in enumerate(sorted(blocked, key=lambda x: x["days"] or 0, reverse=True)):
        d = b["days"]
        if d is not None and d>=14:  pill_cls,plbl="pill-red",    f"{d}d"
        elif d is not None and d>=3: pill_cls,plbl="pill-orange",  f"{d}d"
        else:                        pill_cls,plbl="pill-gray",    f"{d or 0}d"
        since = f"Since {b['since_date'].strftime('%b %-d')}" if b["since_date"] else ""
        blocked_rows += (f'<div class="list-row interactive" data-key="blocked-{i}">'
                         f'<span class="dot dot-orange"></span>'
                         f'<div class="list-main">'
                         f'<div class="list-text">{escape(b["task"])}</div>'
                         f'<div class="list-meta">{escape(b["waiting"])}'
                         f'{"  ·  " + since if since else ""}</div>'
                         f'</div>'
                         f'<span class="pill {pill_cls}">{plbl}</span>'
                         f'<span class="chevron">›</span></div>')
    if not blocked_rows:
        blocked_rows = '<p class="empty-p">Nothing blocked.</p>'

    # Active
    active_cards = ""
    for si,sec in enumerate(active):
        if not sec["tasks"]: continue
        rows = ""
        for ti,t in enumerate(sec["tasks"]):
            due_html = ""
            if t["due"]:
                delta  = (t["due"]-today).days
                d_cls  = "due-red" if delta<=1 else ("due-orange" if delta<=3 else "due-blue")
                due_html = f'<span class="due-tag {d_cls}">{rel_label(t["due"])}</span>'
            rows += (f'<li class="task-li interactive" data-key="active-{si}-{ti}">'
                     f'<span class="dot dot-blue dot-sm"></span>'
                     f'<span class="task-text">{escape(t["text"])}</span>'
                     f'{due_html}'
                     f'<span class="chevron">›</span></li>')
        active_cards += (f'<div class="proj-card">'
                         f'<div class="proj-hd">'
                         f'<span class="proj-nm">{escape(sec["section"])}</span>'
                         f'<span class="pill pill-gray">{len(sec["tasks"])}</span>'
                         f'</div>'
                         f'<ul class="task-ul">{rows}</ul></div>')
    if not active_cards:
        active_cards = '<p class="empty-p">No active tasks.</p>'

    # Legend
    legend_html = "".join(
        f'<div class="leg-row interactive" data-key="donut-{l["idx"]}">'
        f'<span class="leg-dot" style="background:{l["color"]}"></span>'
        f'<span class="leg-name">{escape(l["name"])}</span>'
        f'<span class="leg-n">{l["cnt"]}</span>'
        f'<span class="chevron" style="font-size:10px;margin-left:2px">›</span>'
        f'</div>'
        for l in legend
    ) or '<p class="empty-p" style="font-size:12px">No active projects</p>'

    # Article pipeline widget
    pipeline_html = ""
    for i,a in enumerate(pipeline):
        days_str = f" · {a['days_ago']}d" if a.get("days_ago") else ""
        contact_str = f" · {a['contact']}" if a.get("contact") else ""
        pd_key = f"pipeline-{i}"
        panels[pd_key] = {
            "t": a["name"], "sub": a["label"], "color": a["color"],
            "rows": [
                {"k": "Stage",   "v": a["label"]},
                {"k": "Contact", "v": a["contact"]} if a.get("contact") else None,
                {"k": "Sent",    "v": a["sent_date"] + days_str} if a.get("sent_date") else None,
                {"k": "Status",  "v": a["desc"][:80]}
            ]
        }
        pipeline_html += (
            f'<div class="pipe-card interactive" data-key="{pd_key}" '
            f'style="border-top:3px solid {a["color"]}">'
            f'<div class="pipe-name">{escape(a["name"])}</div>'
            f'<div class="pipe-badge" style="color:{a["color"]}">{escape(a["label"])}{escape(contact_str)}{escape(days_str)}</div>'
            f'</div>'
        )
    if not pipeline_html:
        pipeline_html = '<p class="empty-p">No articles tracked.</p>'

    # Pending replies widget
    replies_html = ""
    for i,r in enumerate(replies):
        days = int(r["days"]) if r.get("days") else 0
        hl   = "red" if days >= 7 else ("orange" if days >= 3 else "")
        pill_cls = "pill-red" if days>=7 else ("pill-orange" if days>=3 else "pill-gray")
        pd_key = f"reply-{i}"
        panels[pd_key] = {
            "t": r["item"], "sub": f"Waiting on {r['waiting_on']}",
            "color": "#ff9500",
            "rows": [
                {"k": "Item",        "v": r["item"]},
                {"k": "Waiting on",  "v": r["waiting_on"]},
                {"k": "Since",       "v": r["since"]} if r.get("since") else None,
                {"k": "Days waiting","v": f"{days} days", "hl": hl} if days else None,
                {"k": "Context",     "v": r.get("desc","")[:80]}
            ]
        }
        replies_html += (
            f'<div class="list-row interactive" data-key="{pd_key}">'
            f'<span class="dot dot-orange"></span>'
            f'<div class="list-main">'
            f'<div class="list-text">{escape(r["item"])}</div>'
            f'<div class="list-meta">Waiting on {escape(r["waiting_on"])}</div>'
            f'</div>'
            f'<span class="pill {pill_cls}">{r.get("label","")}</span>'
            f'<span class="chevron">›</span></div>'
        )
    if not replies_html:
        replies_html = '<p class="empty-p">No pending replies.</p>'

    # Today's agenda widget
    agenda_html = ""
    for i,ev in enumerate(agenda):
        t = ev.get("time","")
        time_html = f'<span class="ag-time">{escape(t)}</span>' if t else '<span class="ag-time ag-allday">all day</span>'
        pd_key = f"agenda-{i}"
        panels[pd_key] = {
            "t": ev["title"], "sub": f"Today{' at ' + t if t else ''}",
            "color": "#0071e3",
            "rows": [{"k": "Time", "v": t if t else "All day"}, {"k": "Date", "v": str(today)}]
        }
        agenda_html += (
            f'<div class="list-row interactive" data-key="{pd_key}">'
            f'{time_html}'
            f'<span class="list-text">{escape(ev["title"])}</span>'
            f'<span class="chevron">›</span></div>'
        )
    if not agenda_html:
        agenda_html = '<p class="empty-p">Nothing scheduled today.</p>'

    # Weekly progress bar
    wk_max   = max(done_wk, done_last_wk, 5)
    wk_pct   = min(int(done_wk / wk_max * 100), 100)
    lw_pct   = min(int(done_last_wk / wk_max * 100), 100)
    wk_color = "#34c759" if done_wk >= done_last_wk else "#ff9500"

    # Rebuild panels_js with new entries
    panels_js = json.dumps(panels, ensure_ascii=False)

    # Completed
    done_rows = ""
    for i,c in enumerate(reversed(completed)):
        dh = f'<span class="done-dt">{c["date"].strftime("%b %-d")}</span>' if c["date"] else ""
        done_rows += (f'<li class="done-li interactive" data-key="done-{i}">'
                      f'<span class="done-ck">✓</span>'
                      f'<span class="done-txt">{escape(c["task"])}</span>'
                      f'{dh}'
                      f'<span class="chevron">›</span></li>')

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
      --bg:#f5f5f7;--surface:#ffffff;
      --border:rgba(0,0,0,0.08);--border2:rgba(0,0,0,0.14);
      --text:#1d1d1f;--muted:#6e6e73;--subtle:#aeaeb2;
      --blue:#0071e3;--blue-bg:#e8f0fd;--blue-bdr:rgba(0,113,227,0.20);
      --green:#34c759;--green-bg:#e8f8ed;--green-bdr:rgba(52,199,89,0.20);
      --orange:#ff9500;--orange-bg:#fff4e0;--orange-bdr:rgba(255,149,0,0.20);
      --red:#ff3b30;--red-bg:#ffebe9;--red-bdr:rgba(255,59,48,0.20);
      --shadow:0 1px 2px rgba(0,0,0,0.04),0 4px 14px rgba(0,0,0,0.06);
      --r:14px;--touch:44px
    }}
    html{{background:var(--bg)}}
    body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
          background:
            radial-gradient(ellipse 55% 28% at 15% 0%,rgba(0,113,227,0.07) 0%,transparent 65%),
            radial-gradient(ellipse 45% 22% at 85% 0%,rgba(52,199,89,0.06) 0%,transparent 65%),
            var(--bg);
          color:var(--text);min-height:100vh;
          padding:28px 20px 80px;-webkit-font-smoothing:antialiased}}
    .wrap{{max-width:1140px;margin:0 auto}}

    /* ─ Header ─ */
    .header{{display:flex;justify-content:space-between;align-items:center;
             margin-bottom:22px;gap:12px;flex-wrap:wrap}}
    .hd-left{{display:flex;align-items:center;gap:12px}}
    .avatar{{width:42px;height:42px;border-radius:13px;flex-shrink:0;
             background:linear-gradient(135deg,#0071e3,#34aadc);
             display:flex;align-items:center;justify-content:center;
             font-size:16px;font-weight:700;color:#fff;
             box-shadow:0 2px 10px rgba(0,113,227,0.30)}}
    .hd-name{{font-size:17px;font-weight:700;letter-spacing:-.3px}}
    .hd-sub{{font-size:12px;color:var(--muted);margin-top:1px}}
    .hd-time{{font-size:12px;color:var(--muted)}}

    /* ─ KPI ─ */
    .kpi-strip{{display:grid;grid-template-columns:repeat(4,1fr);
               gap:10px;margin-bottom:16px}}
    .kpi-card{{background:var(--surface);border:1px solid var(--border);
               border-radius:var(--r);padding:16px 15px;box-shadow:var(--shadow);
               min-height:var(--touch)}}
    .kpi-blue  {{background:var(--blue-bg);  border-color:var(--blue-bdr)}}
    .kpi-green {{background:var(--green-bg); border-color:var(--green-bdr)}}
    .kpi-orange{{background:var(--orange-bg);border-color:var(--orange-bdr)}}
    .kpi-red   {{background:var(--red-bg);   border-color:var(--red-bdr)}}
    .kpi-val{{font-size:30px;font-weight:700;letter-spacing:-1px;
              line-height:1;margin-bottom:4px}}
    .kpi-blue   .kpi-val{{color:var(--blue)}}
    .kpi-green  .kpi-val{{color:var(--green)}}
    .kpi-orange .kpi-val{{color:var(--orange)}}
    .kpi-red    .kpi-val{{color:var(--red)}}
    .kpi-lbl{{font-size:11px;font-weight:500;color:var(--muted)}}

    /* Tooltip */
    [data-tip]{{position:relative}}
    [data-tip]::after{{content:attr(data-tip);position:absolute;
      bottom:calc(100% + 7px);left:50%;transform:translateX(-50%);
      background:#1d1d1f;color:#fff;font-size:11px;padding:5px 10px;
      border-radius:7px;white-space:nowrap;pointer-events:none;
      opacity:0;transition:opacity .15s;z-index:60;
      box-shadow:0 2px 8px rgba(0,0,0,0.2)}}
    [data-tip]:hover::after{{opacity:1}}

    /* Interactive */
    .interactive{{cursor:pointer;-webkit-tap-highlight-color:transparent}}
    .interactive:hover{{background:rgba(0,0,0,0.025)}}
    .interactive:active{{background:rgba(0,0,0,0.06)}}
    .chevron{{color:var(--subtle);font-size:16px;font-weight:400;
              flex-shrink:0;margin-left:auto;padding-left:6px}}

    /* ─ Top row ─ */
    .top-row{{display:grid;grid-template-columns:1fr 1fr 1fr;
              gap:12px;margin-bottom:16px}}
    .panel{{background:var(--surface);border:1px solid var(--border);
            border-radius:var(--r);padding:18px;box-shadow:var(--shadow)}}
    .p-lbl{{font-size:10px;font-weight:700;text-transform:uppercase;
            letter-spacing:.9px;color:var(--muted);margin-bottom:12px}}
    .spark-big{{font-size:30px;font-weight:700;color:var(--green);
                letter-spacing:-1px;line-height:1}}
    .spark-sub{{font-size:11px;color:var(--muted);margin:3px 0 14px}}
    .donut-wrap{{display:flex;align-items:center;gap:14px}}
    .donut-svg{{width:74px;height:74px;flex-shrink:0}}
    .leg{{display:flex;flex-direction:column;gap:6px;flex:1;min-width:0}}
    .leg-row{{display:flex;align-items:center;gap:8px;
              border-radius:7px;padding:5px 6px;margin:-5px -6px;
              min-height:var(--touch)}}
    .leg-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
    .leg-name{{font-size:12px;color:var(--text);flex:1;overflow:hidden;
               text-overflow:ellipsis;white-space:nowrap}}
    .leg-n{{font-size:12px;font-weight:600;color:var(--muted)}}

    /* ─ Calendar ─ */
    .cal-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
    .cal-title{{font-size:12px;font-weight:700;margin-bottom:7px;
                letter-spacing:-.2px}}
    .cal-days-hd{{display:grid;grid-template-columns:repeat(7,1fr);
                  margin-bottom:3px}}
    .cal-days-hd span{{font-size:9px;font-weight:600;text-align:center;
                       color:var(--subtle);padding:1px 0}}
    .cal-days{{display:grid;grid-template-columns:repeat(7,1fr);gap:1px}}
    .cal-cell{{display:flex;flex-direction:column;align-items:center;
               padding:2px 1px;border-radius:6px;min-height:26px}}
    .cal-has-ev{{cursor:pointer}}
    .cal-has-ev:hover{{background:rgba(0,113,227,0.08)}}
    .cal-today .cal-num{{background:var(--blue);color:#fff;border-radius:50%;
                         width:18px;height:18px;display:flex;align-items:center;
                         justify-content:center}}
    .cal-past .cal-num{{color:var(--subtle)}}
    .cal-num{{font-size:10px;font-weight:500;line-height:1.8}}
    .cal-dot{{width:4px;height:4px;border-radius:50%;margin-top:1px}}

    /* ─ Main two-col ─ */
    .main-row{{display:grid;grid-template-columns:1fr 1fr;
               gap:12px;margin-bottom:16px}}
    .card{{background:var(--surface);border:1px solid var(--border);
           border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}}
    .sec{{margin-bottom:16px}}
    .sec-lbl{{font-size:10px;font-weight:700;text-transform:uppercase;
              letter-spacing:.9px;color:var(--muted);margin-bottom:8px;
              padding-left:2px}}

    /* List rows */
    .list-row{{display:flex;align-items:center;gap:10px;padding:12px 14px;
               border-bottom:1px solid var(--border);min-height:var(--touch)}}
    .list-row:last-child{{border-bottom:none}}
    .list-main{{flex:1;min-width:0}}
    .list-text{{font-size:13px;line-height:1.4;overflow:hidden;
                text-overflow:ellipsis;white-space:nowrap}}
    .list-meta{{font-size:11px;color:var(--muted);margin-top:2px;
                overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}

    /* Deadline badges */
    .dt-badge{{font-size:10px;font-weight:700;border-radius:6px;
               padding:3px 8px;flex-shrink:0;white-space:nowrap}}
    .dt-red   {{background:var(--red-bg);color:var(--red)}}
    .dt-orange{{background:var(--orange-bg);color:var(--orange)}}
    .dt-blue  {{background:var(--blue-bg);color:var(--blue)}}

    /* Due tags */
    .due-tag{{font-size:10px;font-weight:600;border-radius:5px;
              padding:2px 6px;flex-shrink:0;white-space:nowrap}}
    .due-red   {{background:var(--red-bg);color:var(--red)}}
    .due-orange{{background:var(--orange-bg);color:var(--orange)}}
    .due-blue  {{background:var(--blue-bg);color:var(--blue)}}

    /* Emails */
    .email-row{{display:flex;align-items:center;gap:10px;padding:12px 14px;
                border-bottom:1px solid var(--border);min-height:var(--touch)}}
    .email-row:last-child{{border-bottom:none}}
    .e-dot{{width:8px;height:8px;border-radius:50%;
            background:var(--blue);flex-shrink:0}}
    .e-dot-read{{background:transparent;border:1.5px solid var(--border2)}}
    .e-body{{flex:1;min-width:0}}
    .e-from{{font-size:13px;font-weight:600;overflow:hidden;
             text-overflow:ellipsis;white-space:nowrap}}
    .e-sub{{font-size:12px;color:var(--muted);overflow:hidden;
            text-overflow:ellipsis;white-space:nowrap;margin-top:2px}}
    .e-time{{font-size:11px;color:var(--muted);flex-shrink:0;white-space:nowrap}}

    /* Dots + pills */
    .dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
    .dot-sm{{width:5px;height:5px;margin-top:9px}}
    .dot-orange{{background:var(--orange)}}.dot-blue{{background:var(--blue)}}
    .pill{{font-size:11px;font-weight:600;border-radius:6px;padding:2px 7px;flex-shrink:0}}
    .pill-gray  {{background:#f2f2f7;color:var(--muted)}}
    .pill-orange{{background:var(--orange-bg);color:var(--orange)}}
    .pill-red   {{background:var(--red-bg);color:var(--red)}}

    /* Project cards */
    .proj-card{{background:var(--surface);border:1px solid var(--border);
                border-radius:var(--r);padding:14px 15px;margin-bottom:8px;
                box-shadow:var(--shadow)}}
    .proj-hd{{display:flex;align-items:center;justify-content:space-between;
              margin-bottom:10px}}
    .proj-nm{{font-size:11px;font-weight:700;text-transform:uppercase;
              letter-spacing:.5px;color:var(--muted)}}
    .task-ul{{list-style:none;display:flex;flex-direction:column;gap:2px}}
    .task-li{{display:flex;align-items:flex-start;gap:9px;padding:8px 7px;
              border-radius:8px;min-height:var(--touch)}}
    .task-text{{font-size:13px;line-height:1.45;flex:1}}

    /* Completed */
    details{{}}
    summary{{cursor:pointer;user-select:none;list-style:none;
             display:flex;align-items:center;gap:7px;
             font-size:10px;font-weight:700;text-transform:uppercase;
             letter-spacing:.9px;color:var(--muted);
             margin-bottom:8px;padding-left:2px}}
    summary::-webkit-details-marker{{display:none}}
    summary::after{{content:'';display:inline-block;width:0;height:0;
                    border-left:4px solid transparent;
                    border-right:4px solid transparent;
                    border-top:4px solid var(--muted);
                    transition:transform .15s}}
    details[open] summary::after{{transform:rotate(180deg)}}
    .done-list{{display:flex;flex-direction:column;gap:4px;list-style:none}}
    .done-li{{display:flex;align-items:center;gap:8px;padding:9px 13px;
              background:var(--surface);border:1px solid var(--border);
              border-radius:9px;box-shadow:var(--shadow);
              min-height:var(--touch)}}
    .done-ck{{color:var(--green);font-size:12px;flex-shrink:0}}
    .done-txt{{font-size:13px;color:var(--subtle);text-decoration:line-through;flex:1}}
    .done-dt{{font-size:11px;color:var(--subtle);white-space:nowrap;flex-shrink:0}}

    .empty-p{{font-size:13px;color:var(--muted);padding:14px 15px;font-style:italic}}

    footer{{margin-top:32px;padding-top:14px;border-top:1px solid var(--border);
            display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
    .ft-name{{font-size:12px;font-weight:600;color:var(--subtle)}}
    .ft-time{{font-size:11px;color:var(--subtle)}}

    /* ─ Drawer / modal ─ */
    .overlay{{position:fixed;inset:0;background:rgba(0,0,0,0);
              pointer-events:none;z-index:200;transition:background .22s}}
    .overlay.open{{background:rgba(0,0,0,0.30);pointer-events:all}}

    .drawer{{
      position:fixed;bottom:0;left:0;right:0;z-index:201;
      background:var(--surface);border-radius:22px 22px 0 0;
      box-shadow:0 -8px 40px rgba(0,0,0,0.14);
      max-height:78vh;overflow-y:auto;
      transform:translateY(100%);
      transition:transform .30s cubic-bezier(.32,.72,0,1)
    }}
    .drawer.open{{transform:translateY(0)}}

    .dr-handle{{width:36px;height:4px;background:var(--border2);
                border-radius:2px;margin:12px auto 0}}
    .dr-accent{{height:3px;margin:14px 0 0;border-radius:0}}
    .dr-inner{{padding:16px 20px 32px}}
    .dr-header{{display:flex;align-items:flex-start;
                justify-content:space-between;gap:12px;margin-bottom:16px}}
    .dr-titles{{flex:1;min-width:0}}
    .dr-title{{font-size:17px;font-weight:700;letter-spacing:-.3px;
               line-height:1.3;word-break:break-word}}
    .dr-sub{{font-size:12px;color:var(--muted);margin-top:3px}}
    .dr-close{{width:30px;height:30px;border-radius:50%;
               background:#f2f2f7;border:none;cursor:pointer;
               display:flex;align-items:center;justify-content:center;
               font-size:14px;color:var(--muted);flex-shrink:0;
               -webkit-tap-highlight-color:transparent}}
    .dr-close:hover{{background:#e5e5ea}}
    .dr-divider{{height:1px;background:var(--border);margin-bottom:14px}}
    .dr-rows{{display:flex;flex-direction:column;gap:0}}
    .dr-row{{display:flex;align-items:baseline;gap:12px;
             padding:11px 0;border-bottom:1px solid var(--border)}}
    .dr-row:last-child{{border-bottom:none}}
    .dr-key{{font-size:12px;font-weight:600;color:var(--muted);
             min-width:90px;flex-shrink:0}}
    .dr-val{{font-size:13px;color:var(--text);flex:1;line-height:1.5}}
    .dr-val.hl-red{{color:var(--red);font-weight:600}}
    .dr-val.hl-orange{{color:var(--orange);font-weight:600}}
    .dr-val.hl-green{{color:var(--green);font-weight:600}}
    .dr-val.hl-blue{{color:var(--blue);font-weight:600}}
    .dr-note{{font-size:12px;color:var(--muted);margin-top:14px;
              padding-top:12px;border-top:1px solid var(--border);
              line-height:1.5}}

    /* Desktop: centered modal */
    @media(min-width:640px){{
      .drawer{{
        bottom:auto;top:50%;left:50%;right:auto;
        transform:translate(-50%,-44%);
        width:440px;max-width:calc(100vw - 32px);
        border-radius:20px;max-height:82vh;
        opacity:0;transition:opacity .18s,transform .18s
      }}
      .drawer.open{{transform:translate(-50%,-50%);opacity:1}}
      .dr-handle{{display:none}}
    }}

    /* ─ Responsive ─ */

    /* iPad landscape + small laptop (900–1140px) */
    @media(max-width:1140px){{
      .wrap{{max-width:900px}}
    }}

    /* iPad portrait (600–900px) */
    @media(max-width:900px){{
      .wrap{{max-width:100%}}
      .top-row{{grid-template-columns:1fr 1fr}}
      .cal-grid{{grid-template-columns:1fr}}
      .tri-row{{grid-template-columns:1fr 1fr}}
      .pipeline-grid{{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}}
    }}

    /* Large phone / small iPad (480–640px) */
    @media(max-width:640px){{
      body{{padding:20px 14px 72px}}
      .kpi-strip{{grid-template-columns:repeat(2,1fr);gap:8px}}
      .kpi-val{{font-size:24px}}
      .top-row{{grid-template-columns:1fr}}
      .main-row{{grid-template-columns:1fr}}
      .tri-row{{grid-template-columns:1fr}}
      .cal-grid{{grid-template-columns:1fr 1fr}}
      .sb-mid{{display:none}}
    }}

    /* iPhone (max 480px) */
    @media(max-width:480px){{
      body{{padding:16px 12px 64px}}
      .kpi-strip{{grid-template-columns:repeat(2,1fr);gap:7px}}
      .kpi-val{{font-size:22px}}
      .kpi-card{{padding:13px 12px}}
      .task-text,.list-text,.e-from{{font-size:13px}}
      .cal-grid{{grid-template-columns:1fr}}
      [data-tip]::after{{display:none}}
    }}

    /* ─ Status bar ─ */
    .sb-wrap{{background:var(--surface);border:1px solid var(--border);
              border-radius:var(--r);padding:11px 16px;box-shadow:var(--shadow);
              margin-bottom:16px}}
    .sb-row{{display:flex;justify-content:space-between;align-items:center;
             flex-wrap:wrap;gap:6px}}
    .sb-left{{display:flex;align-items:center;gap:8px}}
    .sb-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
    .sb-label{{font-size:12px;font-weight:600;color:var(--text)}}
    .sb-mid{{font-size:11px;color:var(--muted)}}
    .sb-right{{font-size:11px;color:var(--muted)}}
    .sb-track{{height:6px;background:#f2f2f7;border-radius:3px;
               margin-top:10px;overflow:hidden}}
    .sb-fill{{height:100%;border-radius:3px;
              transition:width 1.2s cubic-bezier(.16,1,.3,1)}}

    /* ─ Article pipeline ─ */
    .pipeline-grid{{display:grid;
                    grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
                    gap:10px}}
    .pipe-card{{background:var(--surface);border:1px solid var(--border);
               border-radius:var(--r);padding:13px 14px;box-shadow:var(--shadow);
               display:flex;flex-direction:column;gap:6px}}
    .pipe-name{{font-size:13px;font-weight:600;color:var(--text);
               overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .pipe-badge{{font-size:10px;font-weight:700;overflow:hidden;
                text-overflow:ellipsis;white-space:nowrap}}

    /* ─ Three-column main row ─ */
    .tri-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px}}
    .tri-row>*,.top-row>*{{min-width:0}}

    /* ─ Agenda ─ */
    .ag-time{{font-size:11px;font-weight:700;color:var(--blue);min-width:44px;
              flex-shrink:0;background:var(--blue-bg);border-radius:5px;
              padding:2px 6px;text-align:center}}
    .ag-allday{{color:var(--muted);background:#f2f2f7}}

    /* ─ Progress bar ─ */
    .progress-wrap{{background:var(--surface);border:1px solid var(--border);
                   border-radius:var(--r);padding:16px 18px;box-shadow:var(--shadow)}}
    .progress-header{{display:flex;justify-content:space-between;align-items:baseline;
                      margin-bottom:12px}}
    .progress-title{{font-size:10px;font-weight:700;text-transform:uppercase;
                     letter-spacing:.9px;color:var(--muted)}}
    .progress-stats{{font-size:12px;color:var(--muted)}}
    .progress-bar-row{{display:flex;flex-direction:column;gap:6px}}
    .bar-label{{font-size:11px;color:var(--muted);display:flex;
               justify-content:space-between;margin-bottom:2px}}
    .bar-track{{height:8px;background:#f2f2f7;border-radius:4px;overflow:hidden}}
    .bar-fill{{height:100%;border-radius:4px;transition:width 1s cubic-bezier(.16,1,.3,1)}}
    .bar-fill-week{{background:var(--green)}}
    .bar-fill-last{{background:#e5e5ea}}

    /* ─ Animations ─ */
    @keyframes fadeUp{{
      from{{opacity:0;transform:translateY(10px)}}
      to  {{opacity:1;transform:translateY(0)}}
    }}
    @keyframes fadeIn{{
      from{{opacity:0}} to{{opacity:1}}
    }}
    @keyframes growBar{{
      from{{transform:scaleY(0);opacity:0}}
      to  {{transform:scaleY(1);opacity:1}}
    }}
    @keyframes countPulse{{
      0%{{transform:scale(1)}} 40%{{transform:scale(1.08)}} 100%{{transform:scale(1)}}
    }}

    /* Header */
    .header{{animation:fadeUp .45s cubic-bezier(.16,1,.3,1) both}}

    /* KPI stagger */
    .kpi-card{{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both}}
    .kpi-strip>:nth-child(1){{animation-delay:60ms}}
    .kpi-strip>:nth-child(2){{animation-delay:120ms}}
    .kpi-strip>:nth-child(3){{animation-delay:180ms}}
    .kpi-strip>:nth-child(4){{animation-delay:240ms}}

    /* Top row */
    .top-row>:nth-child(1){{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) 300ms both}}
    .top-row>:nth-child(2){{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) 360ms both}}
    .top-row>:nth-child(3){{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) 420ms both}}

    /* Main columns */
    .main-row>:nth-child(1){{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) 480ms both}}
    .main-row>:nth-child(2){{animation:fadeUp .5s cubic-bezier(.16,1,.3,1) 540ms both}}

    /* Completed section */
    .sec:last-of-type{{animation:fadeIn .5s ease 600ms both}}

    /* Sparkline bar grow */
    .spark-bar{{transform-origin:center bottom;animation:growBar .5s cubic-bezier(.16,1,.3,1) backwards}}

    /* Hover lift -- cards and panels */
    .kpi-card,.panel,.proj-card{{
      transition:transform .22s cubic-bezier(.16,1,.3,1),
                 box-shadow .22s ease,
                 border-color .15s ease
    }}
    .kpi-card:hover,.panel:hover,.proj-card:hover{{
      transform:translateY(-2px);
      box-shadow:0 6px 28px rgba(0,0,0,0.10)
    }}
    .card{{transition:box-shadow .22s ease}}
    .card:hover{{box-shadow:0 4px 20px rgba(0,0,0,0.09)}}

    /* Live clock pulse dot */
    .live-dot{{display:inline-block;width:6px;height:6px;border-radius:50%;
               background:var(--green);margin-right:5px;vertical-align:middle;
               animation:pulse 2.4s ease-in-out infinite}}
    @keyframes pulse{{
      0%,100%{{opacity:1;transform:scale(1)}}
      50%{{opacity:.5;transform:scale(.85)}}
    }}

    /* Count-up flash */
    .kpi-val.popped{{animation:countPulse .4s ease}}

    /* ─ Extra row (day cal + velocity) ─ */
    .extra-row{{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:16px}}
    .extra-row>*{{min-width:0}}

    /* ─ Day calendar ─ */
    .dc-outer{{max-height:360px;overflow-y:auto;scrollbar-width:thin;
               scrollbar-color:var(--border2) transparent}}
    .dc-outer::-webkit-scrollbar{{width:4px}}
    .dc-outer::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:2px}}
    .dc-hrow{{position:absolute;left:0;right:0;display:flex;align-items:flex-start}}
    .dc-hlbl{{font-size:10px;color:var(--subtle);width:36px;text-align:right;
              padding-right:7px;margin-top:-6px;flex-shrink:0}}
    .dc-hline{{flex:1;height:1px;background:var(--border)}}
    .dc-ev{{position:absolute;left:4px;right:4px;min-height:22px;
            border-left:3px solid;padding:3px 7px;border-radius:0 5px 5px 0;
            display:flex;align-items:center;gap:6px}}
    .dc-ev-t{{font-size:10px;color:var(--muted);flex-shrink:0}}
    .dc-ev-n{{font-size:12px;font-weight:500;overflow:hidden;
              text-overflow:ellipsis;white-space:nowrap;color:var(--text)}}
    .dc-now{{position:absolute;left:-2px;right:0;height:2px;background:var(--red);display:none}}
    .dc-now::before{{content:'';position:absolute;left:-3px;top:-3px;
                     width:8px;height:8px;border-radius:50%;background:var(--red)}}

    /* ─ Velocity card ─ */
    .vel-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}}
    .vel-stat{{background:#f9f9fb;border:1px solid var(--border);border-radius:10px;
               padding:10px 11px;text-align:center}}
    .vel-val{{font-size:22px;font-weight:700;letter-spacing:-1px;line-height:1;
              display:block;margin-bottom:3px}}
    .vel-lbl{{font-size:10px;color:var(--muted);font-weight:500;line-height:1.3;display:block}}
    .vel-green{{color:var(--green)}}.vel-blue{{color:var(--blue)}}
    .vel-orange{{color:var(--orange)}}.vel-red{{color:var(--red)}}.vel-muted{{color:var(--subtle)}}
    .vel-delta{{display:flex;align-items:center;justify-content:space-between;
                font-size:11px;color:var(--muted);padding:8px 0;
                border-top:1px solid var(--border);margin-top:6px}}
    .vel-trend{{font-weight:600}}
    .act-pill{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:5px;
               display:inline-block;margin:2px}}

    @media(max-width:900px){{
      .extra-row{{grid-template-columns:1fr}}
    }}
    }}
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="hd-left">
      <div class="avatar">F</div>
      <div>
        <div class="hd-name">Felix Janssen</div>
        <div class="hd-sub">Second Brain</div>
      </div>
    </div>
    <div class="hd-time"><span class="live-dot"></span><span id="live-clock"></span></div>
  </div>

  <!-- Status bar -->
  <div class="sb-wrap">
    <div class="sb-row">
      <div class="sb-left">
        <span class="sb-dot" style="background:{sb_color}"></span>
        <span class="sb-label">{sb_label}</span>
      </div>
      <div class="sb-mid">{t_active} active &nbsp;·&nbsp; {t_block} blocked &nbsp;·&nbsp; {t_done} done &nbsp;·&nbsp; {done_wk} this week</div>
      <div class="sb-right">CEST &nbsp;·&nbsp; {updated}</div>
    </div>
    <div class="sb-track"><div class="sb-fill" id="sb-fill" data-pct="{sb_pct}" style="width:0%;background:{sb_color}"></div></div>
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

  <div class="sec">
    <div class="sec-lbl">Article Pipeline</div>
    <div class="pipeline-grid">{pipeline_html}</div>
  </div>

  <div class="tri-row">
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
        <div class="sec-lbl">Today's Agenda</div>
        <div class="card">{agenda_html}</div>
      </div>
      <div class="sec">
        <div class="sec-lbl">Pending Replies</div>
        <div class="card">{replies_html}</div>
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

  <div class="extra-row">
    <div class="panel">
      <div class="p-lbl">Today &nbsp;·&nbsp; {today.strftime("%A %b %-d")}</div>
      {hourly_cal}
    </div>
    <div class="panel">
      <div class="p-lbl">Today's Velocity</div>
      <div class="vel-grid">
        <div class="vel-stat">
          <span class="vel-val {vel_color}">{done_today}</span>
          <span class="vel-lbl">done today</span>
        </div>
        <div class="vel-stat">
          <span class="vel-val vel-muted">{daily_avg}</span>
          <span class="vel-lbl">daily avg (14d)</span>
        </div>
        <div class="vel-stat">
          <span class="vel-val vel-blue">{t_active}</span>
          <span class="vel-lbl">active tasks</span>
        </div>
        <div class="vel-stat">
          <span class="vel-val {'vel-orange' if t_block else 'vel-muted'}">{t_block}</span>
          <span class="vel-lbl">blocked</span>
        </div>
      </div>
      <div class="vel-delta">
        <span>Emails unread: <b>{unread_count}</b></span>
        <span class="vel-trend {'vel-green' if vel_delta >= 0 else 'vel-muted'}">{vel_trend}</span>
      </div>
      <div style="margin-top:12px">
        <div class="sec-lbl" style="margin-bottom:7px">Articles</div>
        <div>{pipeline_pills}</div>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="progress-wrap">
      <div class="progress-header">
        <span class="progress-title">Weekly Progress</span>
        <span class="progress-stats">{done_wk} this week &nbsp;·&nbsp; {done_last_wk} last week &nbsp;·&nbsp; {done_today} today</span>
      </div>
      <div class="progress-bar-row">
        <div>
          <div class="bar-label"><span>This week</span><span>{done_wk} tasks</span></div>
          <div class="bar-track"><div class="bar-fill bar-fill-week" id="bar-week" style="width:0%;background:{wk_color}" data-pct="{wk_pct}"></div></div>
        </div>
        <div>
          <div class="bar-label"><span>Last week</span><span>{done_last_wk} tasks</span></div>
          <div class="bar-track"><div class="bar-fill bar-fill-last" id="bar-last" data-pct="{lw_pct}"></div></div>
        </div>
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
    <span class="ft-name">felix.janssen · second brain</span>
    <span class="ft-time">Last synced <span id="sync-ago" data-ts="{build_epoch}">{updated}</span></span>
  </footer>

</div>

<!-- Drawer -->
<div class="overlay" id="overlay"></div>
<div class="drawer" id="drawer">
  <div class="dr-handle"></div>
  <div class="dr-accent" id="dr-accent"></div>
  <div class="dr-inner">
    <div class="dr-header">
      <div class="dr-titles">
        <div class="dr-title" id="dr-title"></div>
        <div class="dr-sub"   id="dr-sub"></div>
      </div>
      <button class="dr-close" id="dr-close">&#x2715;</button>
    </div>
    <div class="dr-divider"></div>
    <div class="dr-rows" id="dr-rows"></div>
    <div class="dr-note" id="dr-note" style="display:none"></div>
  </div>
</div>

<script>
const PD = {panels_js};

const overlay = document.getElementById('overlay');
const drawer  = document.getElementById('drawer');
const drTitle = document.getElementById('dr-title');
const drSub   = document.getElementById('dr-sub');
const drRows  = document.getElementById('dr-rows');
const drNote  = document.getElementById('dr-note');
const drAccent= document.getElementById('dr-accent');

function openDrawer(key) {{
  const d = PD[key];
  if (!d) return;
  drTitle.textContent = d.t;
  drSub.textContent   = d.sub || '';
  drAccent.style.background = d.color || '#0071e3';
  drRows.innerHTML = (d.rows || []).map(r => {{
    const hlCls = r.hl ? ` hl-${{r.hl}}` : '';
    return `<div class="dr-row">
      <span class="dr-key">${{r.k}}</span>
      <span class="dr-val${{hlCls}}">${{r.v}}</span>
    </div>`;
  }}).join('');
  if (d.note) {{
    drNote.textContent = d.note;
    drNote.style.display = 'block';
  }} else {{
    drNote.style.display = 'none';
  }}
  overlay.classList.add('open');
  drawer.classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function closeDrawer() {{
  overlay.classList.remove('open');
  drawer.classList.remove('open');
  document.body.style.overflow = '';
}}

document.getElementById('dr-close').addEventListener('click', closeDrawer);
overlay.addEventListener('click', closeDrawer);
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeDrawer(); }});

document.addEventListener('click', e => {{
  if (e.target.closest('#drawer')) return;
  const el = e.target.closest('[data-key]');
  if (el && PD[el.dataset.key]) {{ e.stopPropagation(); openDrawer(el.dataset.key); }}
}});

let startY = 0;
drawer.addEventListener('touchstart', e => {{ startY = e.touches[0].clientY; }}, {{passive:true}});
drawer.addEventListener('touchend',   e => {{ if (e.changedTouches[0].clientY - startY > 55) closeDrawer(); }}, {{passive:true}});

// ── Status bar + progress bars ───────────────────────────────────────────────
(function() {{
  function animateBar(id, delay) {{
    const el = document.getElementById(id);
    if (!el) return;
    const pct = parseInt(el.dataset.pct || '0', 10);
    setTimeout(() => {{ el.style.width = pct + '%'; }}, delay || 400);
  }}
  animateBar('sb-fill',   200);
  animateBar('bar-week',  700);
  animateBar('bar-last',  800);
}})();

// ── Live clock ──────────────────────────────────────────────────────────────
(function() {{
  const el = document.getElementById('live-clock');
  if (!el) return;
  function tick() {{
    const n = new Date();
    const h = String(n.getHours()).padStart(2,'0');
    const m = String(n.getMinutes()).padStart(2,'0');
    const s = String(n.getSeconds()).padStart(2,'0');
    el.textContent = `${{h}}:${{m}}:${{s}}`;
  }}
  tick();
  setInterval(tick, 1000);
}})();

// ── KPI count-up ────────────────────────────────────────────────────────────
document.querySelectorAll('[data-countup]').forEach(el => {{
  const target = parseInt(el.dataset.countup, 10);
  if (isNaN(target) || target === 0) return;
  const duration = 700;
  const start    = performance.now();
  const ease = t => 1 - Math.pow(1 - t, 3); // ease-out cubic
  function frame(now) {{
    const p = Math.min((now - start) / duration, 1);
    el.textContent = Math.round(ease(p) * target);
    if (p < 1) requestAnimationFrame(frame);
    else {{ el.textContent = target; el.classList.add('popped'); }}
  }}
  // Small delay so animation starts after card fade-in
  setTimeout(() => requestAnimationFrame(frame), 350);
}});

// ── Relative "last synced" time ─────────────────────────────────────────────
(function() {{
  const el = document.getElementById('sync-ago');
  if (!el) return;
  const epoch = parseInt(el.dataset.ts, 10);
  function update() {{
    const diff = Math.floor(Date.now() / 1000 - epoch);
    if (diff < 60)       el.textContent = 'just now';
    else if (diff < 3600) el.textContent = Math.floor(diff/60) + 'm ago';
    else                  el.textContent = Math.floor(diff/3600) + 'h ' + Math.floor((diff%3600)/60) + 'm ago';
  }}
  update();
  setInterval(update, 30000);
}})();

// ── Day calendar: current-time line + auto-scroll ───────────────────────────
(function() {{
  const nowEl = document.getElementById('dc-now');
  const outer = document.getElementById('dc-outer');
  if (!nowEl || !outer) return;
  const START_H = 8, END_H = 22, SLOT_H = 44;
  function placeLine() {{
    const n = new Date();
    const top = (n.getHours() - START_H + n.getMinutes()/60) * SLOT_H;
    if (top < 0 || top > (END_H - START_H) * SLOT_H) {{ nowEl.style.display = 'none'; return; }}
    nowEl.style.top = top.toFixed(1) + 'px';
    nowEl.style.display = 'block';
  }}
  placeLine();
  setInterval(placeLine, 60000);
  // Scroll so current time is near top of visible area
  const n = new Date();
  outer.scrollTop = Math.max(0, (n.getHours() - START_H - 0.5) * SLOT_H);
}})();
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
