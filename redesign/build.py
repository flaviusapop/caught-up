#!/usr/bin/env python3
"""Drift redesign: static generator.

Writes the public site at the repo root from the weekly working files:

    python3 redesign/build.py                 # run from anywhere; paths are relative to this file
    python3 redesign/build.py --out /tmp/preview

add_week.py build and aie_brief.py render call this at the end, so the weekly
routine does not need an extra step.

Inputs:
  classic/index.html             Brief A (learning plan) and Brief B (Reddit), as add_week.py renders them
  weeks-data/aie-*.json          Brief C (AI Engineer talks and concepts)

Outputs (generated, do not edit by hand): index.html (latest week), week-NN.html,
search.html, search-data.js, assets/, and ideas.html + concepts.html (redirects to the week's Talks view).
"""
import argparse, datetime as dt, html, json, pathlib, re, shutil, sys
from html.parser import HTMLParser

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
esc = lambda s: html.escape(s or "", quote=True)
clean = lambda s: re.sub(r"\s+", " ", s or "").strip()
VIEWS = ("start", "plan", "reddit", "talks")

# ------------------------------------------------------------------ mini DOM
VOID = {"br", "img", "meta", "link", "input", "hr"}
INLINE_OK = {"b", "strong", "em", "i", "code", "br", "a"}


class N:
    __slots__ = ("tag", "a", "kids", "parent")

    def __init__(self, tag, a=None, parent=None):
        self.tag, self.a, self.kids, self.parent = tag, a or {}, [], parent

    def has(self, c):
        return c in (self.a.get("class") or "").split()

    def walk(self):
        for k in self.kids:
            if isinstance(k, N):
                yield k
                yield from k.walk()

    def all(self, tag=None, c=None):
        return [n for n in self.walk() if (tag is None or n.tag == tag) and (c is None or n.has(c))]

    def one(self, tag=None, c=None):
        r = self.all(tag, c)
        return r[0] if r else None

    def children(self, tag=None, c=None):
        return [k for k in self.kids if isinstance(k, N) and (tag is None or k.tag == tag) and (c is None or k.has(c))]

    def text(self):
        return "".join(k if isinstance(k, str) else k.text() for k in self.kids)

    def inner(self):
        """Inline HTML, re-escaped, with only harmless inline tags kept."""
        out = []
        for k in self.kids:
            if isinstance(k, str):
                out.append(html.escape(k, quote=False))
            elif k.tag == "br":
                out.append("<br>")
            elif k.tag == "a" and re.match(r"https?://", k.a.get("href") or ""):
                out.append(f'<a href="{esc(k.a["href"])}" target="_blank" rel="noopener">{k.inner()}</a>')
            elif k.tag in INLINE_OK and k.tag != "a":
                out.append(f"<{k.tag}>{k.inner()}</{k.tag}>")
            else:
                out.append(k.inner())
        return clean("".join(out))


class DOM(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = N("root")
        self.cur = self.root

    def handle_starttag(self, t, a):
        n = N(t, dict(a), self.cur)
        self.cur.kids.append(n)
        if t not in VOID:
            self.cur = n

    def handle_endtag(self, t):
        n = self.cur
        while n is not self.root and n.tag != t:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, d):
        self.cur.kids.append(d)


# ------------------------------------------------------------------ parsing
def badge_parts(badge):
    parts, cur = [], []
    for k in badge.kids if badge else []:
        if isinstance(k, N) and k.tag == "i" and clean(k.text()) == "/":
            parts.append(clean("".join(cur)))
            cur = []
        else:
            cur.append(k if isinstance(k, str) else k.text())
    parts.append(clean("".join(cur)))
    return [p for p in parts if p]


def parse_dur(t):
    h = re.search(r"(\d+(?:\.\d+)?)\s*h", t)
    m = re.search(r"(\d+)\s*m", t)
    mins = (round(float(h.group(1)) * 60) if h else 0) + (int(m.group(1)) if m else 0)
    return mins, ("read" if "read" in t else "watch")


def parse_plan(sec, year):
    hed = sec.one("div", "hed")
    title = clean(hed.one("h3").text())
    plan = {"title": title, "intro": [p.inner() for p in hed.all("p")], "groups": [], "order": None}
    m = re.search(r"about ([\d.]+) hours", title)
    plan["stated_h"] = float(m.group(1)) if m else None
    m = re.search(r"for ([A-Z][a-z]{2}) (\d+)", title)
    if m:
        try:
            plan["from"] = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {year}", "%b %d %Y").date()
        except ValueError:
            pass
    for g in sec.all("div", "grp"):
        spans = g.one("div", "grph").children("span")
        name = clean(spans[0].text())
        note = clean(spans[1].text()) if len(spans) > 1 else ""
        items, notes, steps = [], [], []
        for k in g.children():
            if k.has("grph"):
                continue
            if k.has("tcard"):
                a = k.one("a")
                t = clean(a.text())
                rank = None
                rm = re.match(r"(\d+)\.\s+(.*)", t)
                if rm:
                    rank, t = int(rm.group(1)), rm.group(2)
                parts = badge_parts(k.one("span", "badge"))
                tag = parts[-1] if len(parts) > 1 and re.match(r"(new|from your)", parts[-1], re.I) else ""
                mins, kind = parse_dur(parts[0]) if parts else (0, "watch")
                items.append({"title": t, "url": a.a.get("href", ""), "rank": rank, "mins": mins, "kind": kind,
                              "dur": parts[0] if parts else "", "by": " / ".join(parts[1:-1] if tag else parts[1:]),
                              "tag": tag, "summary": [p.inner() for p in k.all("p", "summary")]})
            elif k.tag == "p":
                notes.append(k.inner())
            elif k.tag in ("ol", "ul"):
                steps = [li.inner() for li in k.all("li")]
        if name.lower().startswith("suggested order"):
            plan["order"] = {"note": note, "steps": steps, "notes": notes}
        else:
            must = name.lower().startswith("must watch")
            plan["groups"].append({"name": "Must watch" if must else re.sub(r"^\d+\)\s*", "", name), "must": must,
                                   "note": "" if must else note, "items": items, "notes": notes})
    return plan


def parse_reddit(sec):
    subs = []
    for ss in sec.all("section", "subsrc"):
        name = clean(ss.one("h3").text())
        stat = clean(ss.one("span", "substat").text()) if ss.one("span", "substat") else ""
        tier = clean(ss.one("span", "subtier").text()) if ss.one("span", "subtier") else ""
        fm = re.search(r"(\d+) fetched", stat)
        threads = []
        for k in ss.children("div", "tcard"):
            a = k.one("a")
            url = a.a.get("href", "")
            parts = badge_parts(k.one("span", "badge"))
            num = lambda i: int(re.sub(r"\D", "", parts[i]) or 0) if len(parts) > i else 0
            idm = re.search(r"/comments/([a-z0-9]+)", url)
            quotes = []
            for q in k.all("div", "tc-item"):
                meta = q.one("p", "tc-meta")
                pl = q.one("a", "tc-pl")
                quotes.append({"by": clean(meta.one("b").text()) if meta and meta.one("b") else "",
                               "pts": clean(meta.one("span", "sc").text()) if meta and meta.one("span", "sc") else "",
                               "body": q.one("p", "tc-body").inner() if q.one("p", "tc-body") else "",
                               "url": pl.a.get("href", "") if pl else ""})
            threads.append({"id": idm.group(1) if idm else f"x{len(threads)}", "title": clean(a.text()), "url": url,
                            "pts": num(0), "comments": num(1), "date": parts[2] if len(parts) > 2 else "",
                            "summary": [p.inner() for p in k.children("p", "summary")],
                            "kp": [li.inner() for li in (k.one("ul", "kp").all("li") if k.one("ul", "kp") else [])],
                            "quotes": quotes})
        ny = ss.one("div", "notyet")
        why = ""
        if ny:
            why = clean(ny.text())
            why = re.sub(r"^Nothing kept this week\s*[—–-]\s*", "", why)
            why = re.sub(r"^r/\S+\s*[—–-]\s*", "", why)
        subs.append({"name": name, "tier": tier, "fetched": int(fm.group(1)) if fm else None,
                     "threads": threads, "why": why})
    if not subs:
        q = sec.one("div", "quiet")
        return {"missing": clean(q.one("p").text()) if q and q.one("p") else "Not collected for this week."}
    out = {"subs": subs, "headline": "", "method": "", "read": [], "note": "", "setup": []}
    syn = sec.one("section", "bbsynth")
    if syn:
        hed = syn.one("div", "hed")
        if hed:
            out["headline"] = clean(hed.one("h3").text())
            out["method"] = " ".join(p.inner() for p in hed.all("p"))
        for g in syn.all("div", "grp"):
            name = clean(g.one("div", "grph").children("span")[0].text()).lower()
            if "setup" in name:
                out["setup"] = [li.inner() for li in g.all("li")]
            else:
                out["read"] += [p.inner() for p in g.children("p")]
                co = g.one("aside", "callout")
                if co and co.one("p"):
                    out["note"] = co.one("p").inner()
    return out


def put(path, text, **_):
    """Write UTF-8 with LF line ends on every platform and Python version."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load(classic, data):
    src = classic.read_text(encoding="utf-8")
    d = DOM()
    d.feed(src)
    years = {}
    for a in d.root.all("a", "week-row"):
        wk = int(re.search(r"\d+", a.one("span", "week-name").text()).group())
        ym = re.search(r"(20\d\d)", a.one("span", "week-meta").text())
        years[wk] = int(ym.group(1)) if ym else dt.date.today().year
    weeks = {}
    for sec in d.root.all("section", "wk"):
        wk = int(sec.a["id"].split("-")[1])
        year = years.get(wk, dt.date.today().year)
        start = dt.date.fromisocalendar(year, wk, 1)
        w = {"wk": wk, "start": start, "end": start + dt.timedelta(days=6), "plan": None, "reddit": None, "talks": None}
        for s in sec.all("section", "src"):
            sid = s.a.get("id", "")
            if sid.startswith("learning"):
                w["plan"] = parse_plan(s, year)
            elif sid.startswith("reddit"):
                w["reddit"] = parse_reddit(s)
        weeks[wk] = w
    for p in sorted(data.glob("aie-*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        wk = t["week"]
        if wk not in weeks:
            start = dt.date.fromisoformat(t["start"])
            weeks[wk] = {"wk": wk, "start": start, "end": start + dt.timedelta(days=6), "plan": None, "reddit": None}
        weeks[wk]["talks"] = t
    return sorted(weeks.values(), key=lambda w: w["start"], reverse=True)


# ------------------------------------------------------------------ formatting
def rng(a, b, year=True):
    s = f"{a:%b} {a.day} – " + (f"{b.day}" if a.month == b.month else f"{b:%b} {b.day}")
    return s + (f", {b.year}" if year else "")


def fmt_min(m):
    h, mm = divmod(m, 60)
    if h and mm:
        return f"{h} h {mm} min"
    return f"{h} h" if h else f"{mm} min"


def fmt_h(x):
    return f"{x:g} h"


def split_title(t):
    t = t.replace("\xa0", " ")
    m = re.match(r"^(.*\S)\s+[—–-]\s+(\S.*)$", t)
    return (m.group(1), m.group(2)) if m else (t, "")


def icon(n, cls=""):
    return f'<svg class="i{" " + cls if cls else ""}" aria-hidden="true"><use href="#i-{n}"/></svg>'


def out_link(title, url, raw=False):
    return (f'<a href="{esc(url)}" target="_blank" rel="noopener">{title if raw else esc(title)}'
            f'&nbsp;{icon("out", "i-out")}</a>')


def strip(h):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", h or "")))


SPRITE = """<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
<symbol id="i-check" viewBox="0 0 20 20"><path d="M4.6 10.6l3.5 3.5 7.3-8.1" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-out" viewBox="0 0 20 20"><path d="M6 14l8-8M7.5 6H14v6.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-prev" viewBox="0 0 20 20"><path d="M12 4.5L6.5 10l5.5 5.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-next" viewBox="0 0 20 20"><path d="M8 4.5l5.5 5.5L8 15.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-open" viewBox="0 0 20 20"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-search" viewBox="0 0 20 20"><circle cx="8.8" cy="8.8" r="5.3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12.9 12.9l3.6 3.6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
</defs></svg>"""

HEAD_JS = """(function(){var d=document,r=d.documentElement,V=['start','plan','reddit','talks'];r.classList.add('js');
try{var t=localStorage.getItem('drift.theme');if(t)r.dataset.theme=t;if(localStorage.getItem('drift.titles')==='1')r.dataset.density='compact'}catch(e){}
var h0=decodeURIComponent(location.hash.slice(1));r.dataset.view=V.indexOf(h0)>-1?h0:'start';
function set(v){r.dataset.view=v;var a=d.querySelectorAll('.tabs a');for(var i=0;i<a.length;i++){if(a[i].getAttribute('href')==='#'+v)a[i].setAttribute('aria-current','page');else a[i].removeAttribute('aria-current')}}
function resolve(){var h=decodeURIComponent(location.hash.slice(1));if(!h){set('start');return}
if(V.indexOf(h)>-1){set(h);return}
var el=d.getElementById(h);if(!el&&h.indexOf('aie-')===0)el=d.getElementById('t-'+h.slice(4));if(!el)return;
var p=el.closest('.panel');if(p)set(p.id);
for(var x=el;x;x=x.parentElement)if(x.tagName==='DETAILS')x.open=true;
el.scrollIntoView()}
d.addEventListener('DOMContentLoaded',resolve);window.addEventListener('load',function(){if(V.indexOf(decodeURIComponent(location.hash.slice(1)))>-1)window.scrollTo(0,0)});window.addEventListener('hashchange',resolve);window.addEventListener('popstate',resolve);
d.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('.tabs a, a.to-view');if(!a)return;
var h=a.getAttribute('href').slice(1);if(V.indexOf(h)<0)return;e.preventDefault();history.pushState(null,'','#'+h);set(h);
var tb=d.querySelector('.tabs'),p=d.getElementById(h);if(tb&&p&&(tb.getBoundingClientRect().top<=1||a.classList.contains('to-view')))window.scrollTo(0,p.getBoundingClientRect().top+window.scrollY-tb.offsetHeight-16)});
})();"""

CONTRACT = """<!--
THESIS: One week is one page with four views (Start here, Plan, Reddit, Talks), not seven weeks stacked on one scroll. Refuses the endless feed with everything unfolded.
OWN-WORLD: Eye-ease ledger paper. Pale green ground, green-black ink, ballpoint-blue links, a highlighter stroke for "you are here". A left margin column carries the one number that matters per row (minutes, points, date) with a tick box under it. Section bands instead of rules. Recia for titles, Supreme for text and figures.
STORY: The reader knows in a minute what the week said, what to change, what to watch first; then works the plan against a time budget and ticks items off.
FIRST VIEWPORT: Week number at display size with its date range; one sentence tallying the week; four tabs; the week's lead sentence; the action list. Week ledger in the left rail on desktop.
FORM: Ledger / run sheet. Chosen from seven candidates grounded in a trader's and product owner's paperwork; the seed script printed nothing on this machine, so no roll was dealt.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
-->"""


def page(title, desc, body, weeks, cur=None, extra_head="", extra_tail=""):
    i = next((n for n, w in enumerate(weeks) if w["wk"] == cur), None)
    newer = weeks[i - 1] if i not in (None, 0) else None
    older = weeks[i + 1] if i is not None and i + 1 < len(weeks) else None
    nav = ""
    if i is not None:
        prev_ = (f'<a class="wn-a" href="week-{older["wk"]}.html" aria-label="Older: week {older["wk"]}">{icon("prev")}</a>'
                 if older else f'<span class="wn-a is-off" aria-hidden="true">{icon("prev")}</span>')
        next_ = (f'<a class="wn-a" href="week-{newer["wk"]}.html" aria-label="Newer: week {newer["wk"]}">{icon("next")}</a>'
                 if newer else f'<span class="wn-a is-off" aria-hidden="true">{icon("next")}</span>')
        nav = f'<nav class="weeknav" aria-label="Week">{prev_}<a class="wn-c" href="#weeks">Week {cur}</a>{next_}</nav>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="color-scheme" content="light dark">
<link rel="preconnect" href="https://api.fontshare.com">
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=recia@1&amp;f[]=supreme@1&amp;display=swap">
<link rel="stylesheet" href="assets/style.css">
<script>{HEAD_JS}</script>{extra_head}
</head>
<body>
{CONTRACT}
{SPRITE}
<a class="skip" href="#main">Skip to content</a>
<header class="bar">
  <a class="mark" href="index.html" aria-label="Drift, latest week">Drift</a>
  {nav}
  <form class="find" action="search.html" role="search">
    <label class="vh" for="q">Search all weeks</label>
    {icon("search")}<input id="q" name="q" type="search" placeholder="Search all weeks" autocomplete="off">
  </form>
  <div class="bar-t">
    <button type="button" class="txt" data-theme-toggle>Night</button>
  </div>
</header>
<div class="frame">
<main id="main">
{body}
</main>
{ledger(weeks, cur)}
</div>
<footer class="foot">
  <p>The learning plan comes from the published Weekly AI learning plan editions. Reddit is collected each week, read-only, from the same ten subreddits; threads are kept for real signal, not score alone. Talk summaries are machine-generated drafts from the <a href="https://www.youtube.com/@aidotengineer" target="_blank" rel="noopener">AI Engineer YouTube channel</a>, not human-reviewed; claims belong to the speakers.</p>
  <p>What you tick off is stored only in this browser. The earlier single-page layout is still at <a href="classic/index.html">classic view</a>.</p>
</footer>
<script src="assets/app.js" defer></script>{extra_tail}
</body>
</html>
"""


def stats(w):
    p, r, t = w["plan"], w["reddit"], w["talks"]
    items = [it for g in p["groups"] for it in g["items"]] if p else []
    listed = sum(it["mins"] for it in items)
    kept = sum(len(s["threads"]) for s in r["subs"]) if r and "subs" in r else None
    return {"items": items, "listed": listed,
            "hours": (p["stated_h"] if p and p["stated_h"] else round(listed / 60, 1)) if p else None,
            "kept": kept, "talks": len(t["videos"]) if t else None}


def ledger(weeks, cur):
    # A list of grid links, not a table: a stretched link inside a table row covers
    # the whole page in browsers that do not position table rows.
    rows = ""
    for w in weeks:
        s = stats(w)
        n = w["wk"]
        ac = ' aria-current="page"' if n == cur else ""
        hours = fmt_h(s["hours"]) if s["hours"] is not None else "–"
        kept = str(s["kept"]) if s["kept"] is not None else "–"
        talks = str(s["talks"]) if s["talks"] is not None else "–"
        rows += (f'<li><a class="lw" href="week-{n}.html"{ac}><span class="lw-n"><b>{n}</b> '
                 f'<span>{rng(w["start"], w["end"], False)}</span></span>'
                 f'<span><span class="vh">plan </span>{hours}</span>'
                 f'<span><span class="vh">Reddit </span>{kept}</span>'
                 f'<span><span class="vh">talks </span>{talks}</span></a></li>')
    return f"""<nav class="ledger" id="weeks" aria-label="All weeks">
  <h2 class="ledger-h">All weeks</h2>
  <div class="lw lw-h" aria-hidden="true"><span class="lw-n">Week</span><span>Plan</span><span>Reddit</span><span>Talks</span></div>
  <ol class="lws">{rows}</ol>
  <p class="ledger-k">Plan in hours. Reddit in threads kept. Talks in summaries. A dash means not collected.</p>
</nav>"""


def titles_btn():
    return ('<button type="button" class="chk" data-titles aria-pressed="false">'
            '<span class="chk-b">' + icon("check") + '</span>Titles only</button>')


def band(title, note="", hid=""):
    return (f'<div class="band"><h3>{esc(title)}</h3>'
            + (f'<span>{esc(note)}</span>' if note else "") + "</div>")


# ------------------------------------------------------------------ plan
def margin_dur(m):
    h, mm = divmod(m, 60)
    return (f"<b>{h} h {mm:02d}</b>" if h else f"<b>{mm}</b> min") if m else ""


def tick(iid, title, what="done"):
    return (f'<button class="tick" type="button" data-id="{esc(iid)}" aria-pressed="false" '
            f'aria-label="Mark as {what}: {esc(title)}">{icon("check")}</button>')


def render_plan(w, s):
    p, wk = w["plan"], w["wk"]
    if not p:
        return '<p class="none">No learning plan was collected for this week.</p>'
    total = s["listed"]
    n = 0
    segs, body, legend = "", "", ""
    for gi, g in enumerate(p["groups"]):
        gm = sum(it["mins"] for it in g["items"])
        gsegs, rows = "", ""
        for it in g["items"]:
            n += 1
            pid = f"p-{wk}-{n}"
            it["pid"] = pid
            gsegs += (f'<a class="rs" href="#{pid}" data-id="{pid}" style="flex-grow:{max(it["mins"], 1)}" '
                      f'data-label="{esc(it["title"])}, {fmt_min(it["mins"])}" aria-label="{esc(it["title"])}, {fmt_min(it["mins"])}"></a>')
            rk = f'<span class="rk">{it["rank"]}.</span> ' if it["rank"] else ""
            tag = (" · " if it["by"] else "") + f'<span class="tag">{esc(it["tag"])}</span>' if it["tag"] else ""
            rows += (f'<article class="it" id="{pid}" data-min="{it["mins"]}">'
                     f'<div class="m"><span class="m-n">{margin_dur(it["mins"])}</span>'
                     + ('<span class="m-k">to read</span>' if it["kind"] == "read" else "")
                     + tick(pid, it["title"]) + '</div>'
                     f'<div class="b"><h4>{rk}{out_link(it["title"], it["url"])}</h4>'
                     f'<p class="by">{esc(it["by"])}{tag}</p>'
                     + "".join(f'<p class="sum">{x}</p>' for x in it["summary"]) + '</div></article>')
        segs += (f'<div class="rg rg-{min(gi, 3)}" style="flex-grow:{max(gm, 1)}"><div class="rg-s">{gsegs}</div>'
                 f'<span class="rg-l">{esc(g["name"])}</span></div>')
        legend += f'<li class="rg-{min(gi, 3)}"><i></i>{esc(g["name"])} <span>{fmt_min(gm)}</span></li>'
        notes = "".join(f'<p class="gnote">{x}</p>' for x in g["notes"])
        body += (f'<section class="grp" data-grp>{band(g["name"], g["note"])}{notes}{rows}</section>')
    hours = total / 60
    ticks = "".join(f'<i style="left:{h * 60 / total * 100:.3f}%"><b>{h}</b></i>' for h in range(0, int(hours) + 1)) if total else ""
    stated = ""
    if p["stated_h"] and abs(p["stated_h"] * 60 - total) > 20:
        stated = (f' The plan budgets about {p["stated_h"]:g} hours; the listed runtimes add up to {fmt_min(total)} '
                  f'because some items are meant to be watched in part.')
    order = ""
    if p["order"] and p["order"]["steps"]:
        lis = ""
        for st in p["order"]["steps"]:
            m = re.match(r"^([A-Z][a-z]{2}):\s*(.*)$", st)
            lis += (f'<li data-day="{m.group(1)}"><b>{m.group(1)}</b><span>{m.group(2)}</span></li>' if m
                    else f'<li><b></b><span>{st}</span></li>')
        frm = f' data-from="{p["from"].isoformat()}"' if p.get("from") else ""
        order = (f'<section class="grp">{band("Day by day", p["order"]["note"])}'
                 f'<ol class="sched"{frm}>{lis}</ol></section>')
    intro = "".join(f"<p>{x}</p>" for x in p["intro"])
    return f"""<h2>{esc(p["title"])}</h2>
<div class="budget" data-total="{total}">
  <p class="budget-r" aria-live="polite"><b data-left>{fmt_min(total)}</b> <span data-left-l>listed</span><span class="budget-d" data-done-l>{n} items</span></p>
  <div class="ruler"><div class="ruler-s">{segs}</div><div class="ruler-t" aria-hidden="true">{ticks}</div></div>
  <ul class="legend">{legend}</ul>
  <p class="budget-h" data-readout data-default="Each block is one item, sized by its runtime. Hours run along the ruler.{esc(stated)}">Each block is one item, sized by its runtime. Hours run along the ruler.{esc(stated)}</p>
</div>
<div class="tools" data-time>
  <span class="tools-l" id="time-l">Time I have</span>
  <div class="pick" role="group" aria-labelledby="time-l">
    <button type="button" data-max="0" aria-pressed="true">Any</button><button type="button" data-max="15" aria-pressed="false">15 min</button><button type="button" data-max="30" aria-pressed="false">30 min</button><button type="button" data-max="60" aria-pressed="false">1 hour</button><button type="button" data-max="120" aria-pressed="false">2 hours</button>
  </div>
  <span class="tools-s" data-time-status aria-live="polite"></span>
  <button type="button" class="chk" data-titles aria-pressed="false"><span class="chk-b">{icon("check")}</span>Titles only</button>
</div>
{body}
{order}
<details class="about"><summary>{icon("open", "i-open")}How this plan was made</summary>{intro}</details>"""


# ------------------------------------------------------------------ reddit
def render_reddit(w):
    r = w["reddit"]
    if not r:
        return '<p class="none">Reddit was not collected for this week.</p>'
    if "missing" in r:
        return f'<p class="none">Reddit: {esc(r["missing"][0].lower() + r["missing"][1:])}</p>'
    kept = [s for s in r["subs"] if s["threads"]]
    empty = [s for s in r["subs"] if not s["threads"]]
    total = sum(len(s["threads"]) for s in kept)
    out = ""
    if r["headline"]:
        out += f'<h2>{esc(r["headline"])}</h2>'
    out += "".join(f'<p class="read">{x}</p>' for x in r["read"])
    if r["setup"]:
        out += (f'<details class="about"><summary>{icon("open", "i-open")}For our setup: {len(r["setup"])} changes</summary>'
                f'<ol class="acts">{"".join(f"<li>{x}</li>" for x in r["setup"])}</ol></details>')
    btns = f'<button type="button" data-sub="" aria-pressed="true">All <b>{total}</b></button>'
    for s in kept:
        btns += f'<button type="button" data-sub="{esc(s["name"])}" aria-pressed="false">{esc(s["name"])} <b>{len(s["threads"])}</b></button>'
    out += (f'<div class="tools" data-subs><span class="tools-l vh" id="sub-l">Subreddit</span>'
            f'<div class="togs" role="group" aria-labelledby="sub-l">{btns}</div>{titles_btn()}</div>')
    for s in kept:
        rows = ""
        for t in s["threads"]:
            q = ""
            if t["quotes"]:
                qs = "".join(
                    f'<div class="q"><p class="q-by"><b>{esc(x["by"])}</b>{" · " + esc(x["pts"]) if x["pts"] else ""}</p>'
                    f'<p>{x["body"]}</p>' + (f'<p class="q-l">{out_link("Open comment", x["url"])}</p>' if x["url"] else "") + '</div>'
                    for x in t["quotes"])
                nq = len(t["quotes"])
                q = (f'<details class="more"><summary>{icon("open", "i-open")}{nq} comment{"s" if nq != 1 else ""} quoted</summary>{qs}</details>')
            kp = f'<ul class="kp">{"".join(f"<li>{x}</li>" for x in t["kp"])}</ul>' if t["kp"] else ""
            meta = " · ".join(x for x in (f'{t["comments"]} comments' if t["comments"] else "", t["date"]) if x)
            rows += (f'<article class="it" id="r-{esc(t["id"])}"><div class="m"><span class="m-n"><b>{t["pts"]}</b> pts</span></div>'
                     f'<div class="b"><h4>{out_link(t["title"], t["url"])}</h4><p class="by">{esc(meta)}</p>'
                     + "".join(f'<p class="sum">{x}</p>' for x in t["summary"]) + kp + q + '</div></article>')
        note = " · ".join(x for x in (s["tier"], f'{len(s["threads"])} kept of {s["fetched"]} fetched' if s["fetched"] else "") if x)
        out += f'<section class="grp" data-sub="{esc(s["name"])}">{band(s["name"], note)}{rows}</section>'
    if empty:
        lis = "".join(f'<li><b>{esc(s["name"])}</b> {esc(s["why"]) if s["why"] else "nothing kept."}</li>' for s in empty)
        out += f'<section class="grp" data-sub-empty>{band("Nothing kept", f"{len(empty)} subreddits")}<ul class="nk">{lis}</ul></section>'
    about = "".join(f"<p>{x}</p>" for x in (r["method"], r["note"]) if x)
    if about:
        out += f'<details class="about"><summary>{icon("open", "i-open")}How this was collected</summary>{about}</details>'
    return out


# ------------------------------------------------------------------ talks
def talk_ref(v, where, pre=""):
    """Link to a talk summary on its own week page; falls back to YouTube."""
    wk = where.get(v["id"])
    t, who = split_title(v["title"])
    tail = f' <span class="who">{esc(who)}</span>' if who else ""
    if wk is None:
        return out_link(t, v["url"]) + tail
    return f'<a href="{pre if pre else ""}#t-{esc(v["id"])}">{esc(t)}</a>{tail}'


def idea_body(c, where, cur_wk):
    def ref(v):
        wk = where.get(v["id"])
        return talk_ref(v, where, "" if wk == cur_wk else f"week-{wk}.html")
    out = ""
    for st in c["statements"]:
        seen, uniq = set(), []
        for e in st["evidence"]:
            if e["id"] not in seen:
                seen.add(e["id"])
                uniq.append(e)
        out += f'<p>{esc(st["text"])}</p>'
        if uniq:
            out += '<ul class="refs">' + "".join(f"<li>{ref(e)}</li>" for e in uniq) + '</ul>'
    for par in c["paragraphs"]:
        out += f"<p>{esc(par)}</p>"
    if c["videos"]:
        out += '<ul class="refs">' + "".join(f"<li>{ref(v)}</li>" for v in c["videos"]) + '</ul>'
    return out


def top_ideas(t):
    cs = t["concepts"]
    top = t["top"] if isinstance(t["top"], list) else list(range(min(int(t["top"] or 3), len(cs))))
    top = [i for i in top if i < len(cs)] or list(range(min(3, len(cs))))
    return top, [i for i in range(len(cs)) if i not in top]


def render_talks(w, where):
    t, wk = w["talks"], w["wk"]
    if not t:
        return '<p class="none">No talk summaries for this week.</p>'
    vids = t["videos"]
    n = len(vids)
    caps = sum(1 for v in vids if v.get("caption_source") is True)
    out = f'<h2>AI Engineer talks: {n} summaries</h2><p class="read">{esc(t["coverage"])}</p>'
    for x in (t.get("partial"), t.get("gap")):
        if x:
            out += f'<p class="warn">{esc(x)}</p>'
    cs = t["concepts"]
    if cs:
        top, rest = top_ideas(t)
        kind = "reviewed against the summaries" if t["concept_kind"] == "reviewed" else "editorial synthesis"
        ideas = ""
        for rank, i in enumerate(top + rest):
            ideas += (f'<details class="idea" id="idea-{wk}-{i + 1}"{" open" if rank == 0 else ""}>'
                      f'<summary>{icon("open", "i-open")}<span>{esc(cs[i]["title"])}</span>'
                      + ('<em>strongest</em>' if rank < len(top) else "") + '</summary>'
                      f'<div class="idea-b">{idea_body(cs[i], where, wk)}</div></details>')
        out += f'<section class="grp">{band("Ideas across the talks", f"{len(cs)} ideas · {kind}")}{ideas}</section>'
    counts = {}
    for v in vids:
        for tp in v["topics"]:
            counts[tp] = counts.get(tp, 0) + 1
    togs = "".join(f'<button type="button" data-topic="{esc(k)}" aria-pressed="false">{esc(k)} <b>{c}</b></button>'
                   for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    rows = ""
    for v in vids:
        title, who = split_title(v["title"])
        date = ""
        if v.get("date"):
            d = dt.date.fromisoformat(v["date"])
            date = f'<span class="m-n"><b>{d:%b} {d.day}</b></span>'
        det = ""
        if v["key_points"]:
            det += '<ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["key_points"]) + "</ul>"
        det += "".join(f"<p>{esc(x)}</p>" for x in v["summary"])
        if v["action_items"]:
            det += '<h5>Suggested actions, from the summary</h5><ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["action_items"]) + "</ul>"
        if v["caveats"]:
            det += '<h5>Limits of this summary</h5><ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["caveats"]) + "</ul>"
        cap = (" · " if who else "") + '<span class="tag">automatic captions</span>' if v.get("caption_source") is True else ""
        by = f'<p class="by">{esc(who)}{cap}</p>' if who or cap else ""
        rows += (f'<article class="it" id="t-{esc(v["id"])}" data-topics="{esc("|".join(v["topics"]))}" data-text="{esc(v["title"].lower())}">'
                 f'<div class="m">{date}{tick("t-" + v["id"], title, "watched")}</div>'
                 f'<div class="b"><h4>{out_link(title, v["url"])}</h4>{by}'
                 f'<p class="tp">{esc(" · ".join(v["topics"]))}</p><p class="sum">{esc(v["overview"])}</p>'
                 f'<details class="more"><summary>{icon("open", "i-open")}Key points and full summary</summary>{det}</details></div></article>')
    all_note = str(n) + " summaries"
    out += f"""<section class="grp" data-talks>{band("All talks", all_note)}
<div class="tools tools-col">
  <label class="filter"><span class="vh">Filter talks by title, speaker or company</span>{icon("search")}<input type="search" data-talk-q placeholder="Filter by title, speaker or company" autocomplete="off"></label>
  <div class="togs" role="group" aria-label="Topics">{togs}</div>
  <div class="tools-r"><span class="tools-s" data-talk-status aria-live="polite"></span><button type="button" class="chk" data-titles aria-pressed="false"><span class="chk-b">{icon("check")}</span>Titles only</button></div>
</div>
{rows}
<p class="none" data-talk-none hidden>No talks match these filters. <button type="button" class="txt" data-talk-clear>Clear filters</button></p>
</section>"""
    if "caption_note" in t:
        capline = t["caption_note"]
    elif caps:
        capline = f"{caps} of {n} summaries were made from automatic YouTube captions, which can be inaccurate or incomplete; each one is labelled."
    else:
        capline = f"None of the {n} summaries used automatic YouTube captions."
    about = ("<p>Draft. Summaries are machine-generated from the talks and not human-reviewed. Claims belong to the speakers "
             f"and their companies and are not independently verified. {esc(capline)}</p>")
    if t.get("concept_note"):
        about += f'<p>{esc(t["concept_note"])}</p>'
    out += f'<details class="about"><summary>{icon("open", "i-open")}About these summaries</summary>{about}</details>'
    return out


# ------------------------------------------------------------------ start
def render_start(w, s):
    p, r, t, wk = w["plan"], w["reddit"], w["talks"], w["wk"]
    out = '<h2 class="vh">Start here</h2>'
    has_r = bool(r and "subs" in r)
    if has_r and r["headline"]:
        out += (f'<p class="lede">{esc(r["headline"])}</p>'
                f'<p class="lede-s">The week on Reddit in one sentence. <a class="to-view" href="#reddit">Read the Reddit brief</a></p>')
    if has_r and r["setup"]:
        acts = "".join(f"<li>{x}</li>" for x in r["setup"])
        note = str(len(r["setup"])) + " changes from this week's threads"
        out += f'<section class="grp">{band("For our setup", note)}<ol class="acts">{acts}</ol></section>'
    if p:
        must = [it for g in p["groups"] if g["must"] for it in g["items"]]
        if must:
            rows = "".join(
                f'<li class="row"><span class="m-n">{margin_dur(it["mins"])}</span>'
                f'<span class="row-b"><a href="#{it["pid"]}">{esc(it["title"])}</a><span class="by">{esc(it["by"])}</span></span></li>'
                for it in must)
            note = f'{len(must)} of {len(s["items"])} items · {fmt_min(sum(it["mins"] for it in must))}'
            out += (f'<section class="grp">{band("Watch first", note)}<ol class="rows">{rows}</ol>'
                    f'<p class="go"><a class="to-view" href="#plan">Open the full plan, {fmt_h(s["hours"])}</a></p></section>')
    if t and t["concepts"]:
        top, _ = top_ideas(t)
        lis = "".join(f'<li><a href="#idea-{wk}-{i + 1}">{esc(t["concepts"][i]["title"])}</a></li>' for i in top)
        note = str(len(top)) + " of " + str(len(t["concepts"]))
        nv = len(t["videos"])
        out += (f'<section class="grp">{band("Strongest ideas from the talks", note)}'
                f'<ol class="acts acts-l">{lis}</ol>'
                f'<p class="go"><a class="to-view" href="#talks">Browse all {nv} talks</a></p></section>')
    missing = []
    if not p:
        missing.append("No learning plan was collected for this week.")
    if not has_r:
        missing.append("Reddit was not collected for this week.")
    if not t:
        missing.append("No talk summaries for this week.")
    out += "".join(f'<p class="none">{m}</p>' for m in missing)
    return out


def render_week(w, weeks, where, legacy=""):
    s = stats(w)
    wk = w["wk"]
    plan_html = render_plan(w, s)          # sets item ids used by the start view
    tally = []
    if s["hours"] is not None:
        tally.append(f'<li><b>{s["hours"]:g}</b> hours to watch and read</li>')
    if s["kept"] is not None:
        tally.append(f'<li><b>{s["kept"]}</b> Reddit threads kept</li>')
    if s["talks"] is not None:
        tally.append(f'<li><b>{s["talks"]}</b> talk summaries</li>')
    def tab(v, label, n):
        cur = ' aria-current="page"' if v == "start" else ""
        return f'<a href="#{v}"{cur}>{label}' + (f' <b>{n}</b>' if n is not None else "") + '</a>'
    body = f"""<header class="wkhead" id="wk-{wk}">
  <h1>Week {wk}</h1>
  <p class="wk-d">{rng(w["start"], w["end"])}</p>
  <ul class="tally">{"".join(tally)}</ul>
</header>
<nav class="tabs" aria-label="Views of this week">
  {tab("start", "Start here", None)}{tab("plan", "Plan", len(s["items"]) if w["plan"] else None)}{tab("reddit", "Reddit", s["kept"])}{tab("talks", "Talks", s["talks"])}
</nav>
<section class="panel" id="start">{render_start(w, s)}</section>
<section class="panel" id="plan">{plan_html}</section>
<section class="panel" id="reddit">{render_reddit(w)}</section>
<section class="panel" id="talks">{render_talks(w, where)}</section>"""
    desc = f"Week {wk}, {rng(w['start'], w['end'])}: learning plan, Reddit brief and AI Engineer talk summaries."
    return page(f"Week {wk} · Drift", desc, body, weeks, cur=wk, extra_head=legacy)


# ------------------------------------------------------------------ search
def search_data(weeks):
    rows = []
    for w in weeks:
        wk = w["wk"]
        if w["plan"]:
            for g in w["plan"]["groups"]:
                for it in g["items"]:
                    rows.append({"w": wk, "k": "Plan", "t": it["title"], "u": f"week-{wk}.html#{it['pid']}",
                                 "m": f'{it["by"]} · {fmt_min(it["mins"])}', "s": strip(" ".join(it["summary"]))})
        r = w["reddit"]
        if r and "subs" in r:
            for sub in r["subs"]:
                for t in sub["threads"]:
                    rows.append({"w": wk, "k": "Reddit", "t": t["title"], "u": f"week-{wk}.html#r-{t['id']}",
                                 "m": f'{sub["name"]} · {t["pts"]} pts',
                                 "s": strip(" ".join(t["summary"]) + " " + " ".join(t["kp"]))})
        t = w["talks"]
        if t:
            for v in t["videos"]:
                title, who = split_title(v["title"])
                rows.append({"w": wk, "k": "Talk", "t": title, "u": f"week-{wk}.html#t-{v['id']}",
                             "m": " · ".join(x for x in (who, ", ".join(v["topics"])) if x),
                             "s": v["overview"] + " " + " ".join(v["key_points"])})
            for i, c in enumerate(t["concepts"]):
                txt = " ".join(st["text"] for st in c["statements"]) + " " + " ".join(c["paragraphs"])
                rows.append({"w": wk, "k": "Idea", "t": c["title"], "u": f"week-{wk}.html#idea-{wk}-{i + 1}",
                             "m": "from the talks", "s": clean(txt)})
    return rows


def render_search(weeks):
    body = ('<header class="wkhead"><h1>Search</h1><p class="wk-d">Plans, Reddit threads, talks and ideas across every week</p></header>'
            '<form class="tools tools-col" action="search.html" role="search"><label class="filter filter-l"><span class="vh">Search all weeks</span>' + icon("search") +
            '<input type="search" name="q" data-search-q placeholder="Try evals, sandbox, Sierra Chart" autocomplete="off"></label>'
            '<span class="tools-s" data-search-status aria-live="polite">Type at least two letters.</span></form>'
            '<div data-search-out></div>'
            '<noscript><p class="none">Search needs JavaScript. Every week is still readable from the list of weeks.</p></noscript>')
    return page("Search · Drift", "Search every week of Drift.", body, weeks,
                extra_tail='\n<script src="search-data.js" defer></script>')


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classic", default=str(REPO / "classic" / "index.html"), help="the single-page file add_week.py maintains")
    ap.add_argument("--data", default=str(REPO / "weeks-data"), help="folder with aie-*.json")
    ap.add_argument("--out", default=str(REPO), help="where the site is written (default: repo root)")
    a = ap.parse_args()
    classic, data, out = pathlib.Path(a.classic), pathlib.Path(a.data), pathlib.Path(a.out)
    if not classic.exists():
        sys.exit(f"redesign/build.py: {classic} not found.")
    weeks = load(classic, data)
    if not weeks:
        sys.exit(f"redesign/build.py: no weeks found in {classic}; nothing written.")
    where = {v["id"]: w["wk"] for w in weeks if w["talks"] for v in w["talks"]["videos"]}
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for f in ("style.css", "app.js"):
        shutil.copyfile(HERE / "src" / f, out / "assets" / f)
    # old single-page anchors keep working from index.html
    legacy = ('\n<script>(function(){var h=decodeURIComponent(location.hash.slice(1)),m,W=' + json.dumps(where, separators=(",", ":")) +
              ';if(!h)return;if((m=h.match(/^wk-(\\d+)$/)))location.replace("week-"+m[1]+".html");'
              'else if((m=h.match(/^(learning|reddit|aie)-(\\d{1,2})$/)))location.replace("week-"+m[2]+".html#"+({learning:"plan",reddit:"reddit",aie:"talks"})[m[1]]);'
              'else if((m=h.match(/^sub-.*-(\\d{1,2})$/)))location.replace("week-"+m[1]+".html#reddit");'
              'else if((m=h.match(/^aie-(\\d+)-c(\\d+)$/)))location.replace("week-"+m[1]+".html#idea-"+m[1]+"-"+m[2]);'
              'else if((m=h.match(/^aie-(.+)$/))&&W[m[1]])location.replace("week-"+W[m[1]]+".html#t-"+m[1]);})();</script>')
    report = []
    for i, w in enumerate(weeks):
        doc = render_week(w, weeks, where)
        put(out / f"week-{w['wk']}.html", doc, encoding="utf-8", newline="\n")
        if i == 0:
            put(out / "index.html", render_week(w, weeks, where, legacy), encoding="utf-8", newline="\n")
        s = stats(w)
        report.append(f"week {w['wk']}: plan {len(s['items'])} items / {fmt_min(s['listed'])} listed, "
                      f"reddit {s['kept']}, talks {s['talks']}, {len(doc) // 1024} KB")
    put(out / "search.html", render_search(weeks), encoding="utf-8", newline="\n")
    data = search_data(weeks)
    put(out / "search-data.js", "window.DRIFT_SEARCH=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                        encoding="utf-8", newline="\n")
    # The Ideas page is gone: ideas live in each week's Talks view. Old links keep working.
    moved = ('<!doctype html><meta charset="utf-8"><title>Drift</title><meta name="viewport" content="width=device-width, initial-scale=1">'
             '<script>(function(){var h=location.hash.slice(1),m;'
             'if((m=h.match(/^c-(\\d+)-(\\d+)$/)))location.replace("week-"+m[1]+".html#idea-"+m[1]+"-"+m[2]);'
             'else if((m=h.match(/^wk-(\\d+)$/)))location.replace("week-"+m[1]+".html#talks");'
             'else location.replace("index.html#talks");})();</script>'
             '<p>Ideas now sit in each week under Talks. <a href="index.html#talks">Open the newest week</a></p>\n')
    put(out / "ideas.html", moved)
    put(out / "concepts.html", moved)
    print("\n".join(report))
    print(f"search index: {len(data)} entries. Wrote {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
