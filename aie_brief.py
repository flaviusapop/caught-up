#!/usr/bin/env python3
"""Brief C — AI Engineer: talk summaries from the AI Engineer YouTube channel.

Optional third brief. Brief A and Brief B (add_week.py) work without it.
Data lives in weeks-data/aie-<monday>.json (derived summaries + reviewed
concepts only; never transcripts, private URLs or local paths).

  import-historical PACK.json   one file per ISO week from a historical pack
  import-preview PREVIEW.html   rolling-window preview: each talk is placed in
                                the Mon–Sun week of its publish date; talks
                                already on any week are skipped (by video id)
  render [MONDAY ...]           insert/replace Brief C inside those week blocks
                                of index.html (all weeks with data if none given),
                                create a Brief-C-only week block if the week is
                                not on the page yet, and rebuild concepts.html
  check                         validate data (ids, links, counts, leaks)

add_week.py build renders Brief C automatically when weeks-data/aie-<monday>.json
exists, so re-running build for a week keeps its Brief C.
"""
import argparse, datetime as dt, html, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
WDATA = ROOT / "weeks-data"
INDEX = ROOT / "index.html"
CONCEPTS = ROOT / "concepts.html"
CHANNEL = "https://www.youtube.com/@aidotengineer"
YT = re.compile(r"^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$")
HUE = "mlreddit"
esc = lambda s: html.escape(s or "", quote=True)
LEAK = re.compile(r"\.ts\.net\b|/home/|\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\bgh[opsu]_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY", re.I)

# Weeks whose inventory is known to be possibly incomplete (publisher-listed
# videos that are now private; their historical eligibility is unknown).
KNOWN_GAPS = {
    41: "One video the channel listed for this week is now private, and whether it belongs to this week can no longer be checked. This week may be incomplete.",
    42: "One video the channel listed for this week is now private, and whether it belongs to this week can no longer be checked. This week may be incomplete.",
}

def monday(year, wk): return dt.date.fromisocalendar(year, wk, 1)
def md(d): return d.strftime("%b %-d")
def path_for(start): return WDATA / f"aie-{start}.json"
def all_weeks():
    return sorted((json.loads(p.read_text()) for p in WDATA.glob("aie-*.json")), key=lambda w: w["start"], reverse=True)

def clean_video(v, week_start, date=None):
    m = YT.match(v["url"])
    if not m or m.group(1) != v["id"]:
        sys.exit(f"video link does not match id: {v['id']} {v['url']}")
    return {
        "id": v["id"], "url": v["url"], "title": v["title"], "date": date or v.get("date"),
        "topics": v.get("topics") or [],
        "caption_source": v.get("caption_source"),  # True = automatic YouTube captions; None = not reported
        "overview": v.get("overview", ""), "key_points": v.get("key_points") or [],
        "summary": v.get("summary") or [], "caveats": v.get("caveats") or [],
        "action_items": v.get("action_items") or [],
    }

# ---------------------------------------------------------------- import
def cmd_import_historical(a):
    pack = json.loads(pathlib.Path(a.pack).read_text())
    total = 0
    for w in pack["weeks"]:
        wk = int(w["week"]); start = monday(a.year, wk)
        vids = [clean_video(v, start) for v in w["videos"]]
        ids = {v["id"] for v in vids}
        concepts = []
        for c in w["concepts"]:
            sts = []
            for s in c["statements"]:
                ev = []
                for e in s["evidence"]:
                    if e["id"] not in ids: sys.exit(f"week {wk}: evidence {e['id']} not among the week's videos")
                    if not YT.match(e["url"]) or YT.match(e["url"]).group(1) != e["id"]: sys.exit(f"bad evidence link {e}")
                    ev.append({"id": e["id"], "title": e["title"], "url": e["url"], "excerpt": e["excerpt"]})
                sts.append({"text": s["text"], "evidence": ev})
            concepts.append({"title": c["title"], "statements": sts, "paragraphs": [], "videos": []})
        titles = [c["title"] for c in concepts]
        top = [titles.index(t) for t in w["top_three"] if t in titles]
        out = {
            "week": wk, "start": start.isoformat(), "end": (start + dt.timedelta(days=6)).isoformat(),
            "coverage": f"Talks the channel published {md(start)}–{md(start + dt.timedelta(days=6))}, {start.year} (Europe/Bucharest).",
            "concept_kind": "reviewed",
            "concept_note": w.get("selection_note") or "Concepts kept after an automated review of each statement against the derived summaries (not the original transcripts). Not human-approved.",
            "gap": KNOWN_GAPS.get(wk), "partial": None,
            "top": top, "concepts": concepts, "videos": vids,
        }
        path_for(start).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        total += len(vids)
        print(f"week {wk} ({start}): {len(vids)} summaries, {len(concepts)} concepts, "
              f"{sum(1 for v in vids if v['caption_source'] is True)} auto-caption")
    print("total", total)

def text(s): return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()

def parse_preview(src):
    cards = re.findall(r'<article class="tcard aie-card" id="aie-[^"]+" data-video-id="([^"]+)">(.*?)</article>', src, re.S)
    vids = []
    for vid, body in cards:
        h = re.search(r'<h3><a href="([^"]+)"[^>]*>(.*?)</a></h3>', body, re.S)
        badge = text(re.search(r'<span class="badge">(.*?)</span>', body, re.S).group(1))
        date, _, topics = badge.partition("/")
        ov = re.search(r'<p class="summary">(.*?)</p>', body, re.S)
        det = re.search(r"<details>(.*?)</details>", body, re.S)
        det = det.group(1) if det else ""
        kp = [text(x) for x in re.findall(r"<li>(.*?)</li>", det, re.S)]
        paras = [text(x) for x in re.findall(r"<p>(.*?)</p>", det, re.S)]
        vids.append({"id": vid, "url": html.unescape(h.group(1)), "title": text(h.group(2)),
                     "date": date.strip(), "topics": [t.strip() for t in topics.split(",") if t.strip()],
                     "caption_source": None, "overview": text(ov.group(1)) if ov else "",
                     "key_points": kp, "summary": paras})
    ideas = []
    for iid, body in re.findall(r'<article class="tcard aie-idea" id="([^"]+)">(.*?)</article>', src, re.S):
        ps = re.findall(r'<p class="summary">(.*?)</p>', body, re.S)
        paras, links = [], []
        for p in ps:
            if "<strong>Videos:</strong>" in p:
                links = [{"url": html.unescape(u), "title": text(t), "id": YT.match(html.unescape(u)).group(1)}
                         for u, t in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', p, re.S)]
            else:
                paras.append(text(p))
        ideas.append({"anchor": iid, "title": text(re.search(r"<h3>(.*?)</h3>", body, re.S).group(1)),
                      "paragraphs": paras, "videos": links, "statements": []})
    three = re.search(r"If you read three things</h3>(.*?)</p>", src, re.S)
    top_anchors = re.findall(r'href="#([^"]+)"', three.group(1)) if three else []
    win = re.search(r"Window:\s*([^<]*?\(inclusive\))", src)
    return vids, ideas, top_anchors, (text(win.group(1)) if win else None)

def cmd_import_preview(a):
    src = pathlib.Path(a.preview).read_text()
    vids, ideas, top_anchors, win = parse_preview(src)
    if not vids: sys.exit("no talk cards found in the preview; nothing changed")
    seen = {v["id"]: w["week"] for w in all_weeks() for v in w["videos"]}
    placed, skipped = {}, []
    for v in vids:
        if v["id"] in seen: skipped.append((v["id"], seen[v["id"]])); continue
        d = dt.date.fromisoformat(v["date"])
        placed.setdefault(d - dt.timedelta(days=d.weekday()), []).append(v)
    window = f"rolling window {win}" if win else "a rolling 7-day window"
    for start, vs in sorted(placed.items()):
        p = path_for(start)
        w = json.loads(p.read_text()) if p.exists() else {
            "week": start.isocalendar()[1], "start": start.isoformat(), "end": (start + dt.timedelta(days=6)).isoformat(),
            "concept_kind": "editorial", "gap": None, "top": [], "concepts": [], "videos": []}
        w["videos"] += [clean_video(v, start, v["date"]) for v in vs]
        w["videos"].sort(key=lambda v: (v.get("date") or "", v["title"]), reverse=True)
        ds = sorted(v["date"] for v in w["videos"] if v.get("date"))
        w["coverage"] = (f"Talks published {md(dt.date.fromisoformat(ds[0]))}–{md(dt.date.fromisoformat(ds[-1]))}, {start.year}, "
                         f"taken from a draft preview that covers {window}. This is not a complete calendar-week inventory, "
                         f"and the preview says its completeness is not conclusively verified.")
        w["partial"] = "Partial week: talks published later in this week may be added when the next preview arrives."
        if ideas and start == max(placed):
            idx = {i["anchor"]: n for n, i in enumerate(ideas)}
            w["concepts"] = [{"title": i["title"], "statements": [], "paragraphs": i["paragraphs"], "videos": i["videos"]} for i in ideas]
            w["top"] = [idx[t] for t in top_anchors if t in idx]
            w["concept_kind"] = "editorial"
            w["concept_note"] = ("Editorial synthesis written for the draft preview, across all talks in its window (some are in the previous week). "
                                 "Speaker and company claims are reported as made, not independently fact-checked.")
        w["caption_note"] = "The preview does not say which summaries used automatic YouTube captions."
        p.write_text(json.dumps(w, indent=1, ensure_ascii=False) + "\n")
        print(f"week {w['week']} ({start}): +{len(vs)} talks, now {len(w['videos'])}")
    print(f"skipped {len(skipped)} talks already on the page:", ", ".join(f"{i} (wk {k})" for i, k in skipped))

# ---------------------------------------------------------------- render
def video_card(v):
    cap = ""
    if v.get("caption_source") is True:
        cap = '<i>/</i><b class="aie-cap" title="This summary was made from automatic YouTube captions, which can be inaccurate or incomplete.">Automatic captions</b>'
    bits = [esc(v["date"])] if v.get("date") else []
    if v.get("topics"): bits.append(esc(", ".join(v["topics"])))
    badge = "<i>/</i>".join(bits) + cap
    det = ""
    if v["key_points"]: det += '<ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["key_points"]) + "</ul>"
    det += "".join(f'<p class="tc-body">{esc(p)}</p>' for p in v["summary"])
    if v["action_items"]:
        det += '<p class="tc-meta"><b>Suggested actions (from the summary)</b></p><ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["action_items"]) + "</ul>"
    if v["caveats"]:
        det += '<p class="tc-meta"><b>Limits of this summary</b></p><ul class="kp">' + "".join(f"<li>{esc(k)}</li>" for k in v["caveats"]) + "</ul>"
    if v.get("caption_source") is True:
        det += '<p class="tc-body aie-capnote">Made from automatic YouTube captions, which can be inaccurate or incomplete.</p>'
    return (f'<article class="tcard aie-card" id="aie-{esc(v["id"])}" data-video-id="{esc(v["id"])}">'
            f'<h3><a href="{esc(v["url"])}" target="_blank" rel="noopener">{esc(v["title"])}</a></h3>'
            f'<span class="badge">{badge}</span><p class="summary">{esc(v["overview"])}</p>'
            f'<details class="tc aie-det"><summary class="tc-hd">Key points and full summary</summary>{det}</details></article>')

def src_links(vs):
    return " · ".join(f'<a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["title"])}</a> '
                      f'<a class="aie-jump" href="#aie-{esc(x["id"])}">summary</a>' for x in vs)

def concept_body(c, page=False):
    pre = "index.html" if page else ""
    out = ""
    for s in c["statements"]:
        seen, uniq = set(), []
        for e in s["evidence"]:
            if e["id"] not in seen: seen.add(e["id"]); uniq.append(e)
        links = " · ".join(f'<a href="{esc(e["url"])}" target="_blank" rel="noopener">{esc(e["title"])}</a> '
                           f'<a class="aie-jump" href="{pre}#aie-{esc(e["id"])}">summary</a>' for e in uniq)
        out += f'<p class="summary">{esc(s["text"])}</p><p class="summary aie-src"><b>Sources:</b> {links}</p>'
        if page:
            out += '<ul class="kp aie-ev">' + "".join(f'<li>“{esc(e["excerpt"])}” — {esc(e["title"])}</li>' for e in s["evidence"]) + "</ul>"
    for p in c["paragraphs"]:
        out += f'<p class="summary">{esc(p)}</p>'
    if c["videos"]:
        links = " · ".join(f'<a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["title"])}</a> '
                           f'<a class="aie-jump" href="{pre}#aie-{esc(x["id"])}">summary</a>' for x in c["videos"])
        out += f'<p class="summary aie-src"><b>Videos:</b> {links}</p>'
    return out

def brief_c_section(w):
    wk, n = w["week"], len(w["videos"])
    caps = sum(1 for v in w["videos"] if v.get("caption_source") is True)
    if "caption_note" in w: cap_line = w["caption_note"]
    elif caps: cap_line = f"{caps} of {n} summaries were made from automatic YouTube captions, which can be inaccurate or incomplete; each one is labelled."
    else: cap_line = f"None of the {n} summaries used automatic YouTube captions."
    hed = (f'<div class="sum hed"><h3 class="issuehed">AI Engineer talks, Week {wk}: {n} summaries</h3>'
           f'<p>{esc(w["coverage"])} Source: the <a href="{CHANNEL}" target="_blank" rel="noopener">AI Engineer YouTube channel</a>.</p>'
           f'<p>Draft. Summaries are machine-generated from the talks and not human-reviewed. Claims belong to the speakers and their companies and are not independently verified. {esc(cap_line)}</p></div>')
    notes = ""
    for label, t in (("May be incomplete", w.get("gap")), ("Partial week", w.get("partial"))):
        if t: notes += f'<aside class="callout aie-gap"><span class="boxlabel">{label}</span><p>{esc(t)}</p></aside>'
    cs = w["concepts"]
    top = [i for i in w["top"] if i < len(cs)] or list(range(min(3, len(cs))))
    kind = "reviewed concepts" if w["concept_kind"] == "reviewed" else "editorial synthesis"
    ideas = ""
    if cs:
        cards = "".join(f'<article class="tcard aie-idea" id="aie-{wk}-c{i+1}"><h3><a href="concepts.html#c-{wk}-{i+1}">{n_+1}. {esc(cs[i]["title"])}</a></h3>'
                        f'{concept_body(cs[i])}</article>' for n_, i in enumerate(top))
        ideas = (f'<div class="grp aie-ideas"><div class="grph"><span>Strongest ideas</span><span>{len(top)} of {len(cs)} · {kind}</span></div>'
                 f'<p style="padding:0 20px" class="aie-note">{esc(w.get("concept_note", ""))}</p>{cards}</div>')
        rest = [i for i in range(len(cs)) if i not in top]
        lis = "".join(f'<li><a href="concepts.html#c-{wk}-{i+1}">{esc(cs[i]["title"])}</a></li>' for i in rest)
        ideas += (f'<div class="grp aie-more"><div class="grph"><span>All concepts this week</span><span><a href="concepts.html#wk-{wk}">concept page</a></span></div>'
                  + (f'<ol class="ed">{lis}</ol>' if lis else "") + "</div>")
    vids = (f'<div class="grp aie-videos"><div class="grph"><span>Video summaries</span><span>{n} talks'
            + (f" · {caps} automatic captions" if caps else "") + '</span></div>'
            + "".join(video_card(v) for v in w["videos"]) + "</div>")
    return (f'<!-- Brief C:start wk-{wk} -->\n  <section class="src" id="aie-{wk}" data-fold="false" style="color:var(--h-{HUE})">\n'
            f'    <div class="srch"><div class="in"><h2><button class="srtoggle" aria-expanded="true">Brief C — AI Engineer</button></h2></div></div>\n'
            f'    <div class="fold-wrap"><div>\n{hed}\n{notes}\n{ideas}\n{vids}\n    </div></div>\n  </section>\n  <!-- Brief C:end wk-{wk} -->')

def row_suffix(w): return f" · BRIEF C: {len(w['videos'])} TALKS"

def find_week(src, wk):
    m = re.search(rf'<section class="wk" id="wk-{wk}">', src)
    if not m: return None
    depth = 0
    for t in re.finditer(r"<section\b|</section>", src[m.start():]):
        depth += 1 if t.group(0) == "<section" else -1
        if depth == 0: return m.start(), m.start() + t.end()
    sys.exit(f"unbalanced sections in wk-{wk}")

def apply_to_block(block, w):
    """Insert or replace Brief C inside one week block (string)."""
    wk = w["week"]
    rx = re.compile(rf"\n*\s*<!-- Brief C:start wk-{wk} -->.*?<!-- Brief C:end wk-{wk} -->", re.S)
    block = rx.sub("", block)
    i = block.rstrip().rfind("</section>")
    return block[:i].rstrip() + "\n\n  " + brief_c_section(w) + "\n  " + block[i:]

def stub_block(w):
    s = dt.date.fromisoformat(w["start"]); e = dt.date.fromisoformat(w["end"]); wk = w["week"]
    return f'''<section class="wk" id="wk-{wk}">
    <div class="wkhead"><div class="in">
      <span class="no">Week {wk}</span><span class="dt">{md(s)} — {md(e)}</span>
      <span class="strip" aria-hidden="true"><i data-on="true"></i><i data-on="true"></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>
      <button class="fold" data-fold-all="{wk}">Fold all</button>
    </div></div>
    <div class="quiet">
      <p class="topics">Brief A and Brief B for this week arrive with the Sunday {md(e)} edition.</p>
      <div class="qrow"><b>Brief A — AI Learning</b><span>arrives {md(e)}</span></div>
      <div class="qrow"><b>Brief B — Reddit Deep-Dive</b><span>arrives {md(e)}</span></div>
    </div>
  </section>'''

def set_row(src, w, stub=False):
    wk = w["week"]; s = dt.date.fromisoformat(w["start"]); e = dt.date.fromisoformat(w["end"])
    rx = re.compile(rf'(<li><a class="week-row" href="#wk-{wk}">.*?<span class="week-meta">)(.*?)(</span>)')
    m = rx.search(src)
    if m:
        meta = re.sub(r" · BRIEF C: \d+ TALKS$", "", m.group(2)) + row_suffix(w)
        return src[:m.start()] + m.group(1) + meta + m.group(3) + src[m.end():]
    row = (f'<li><a class="week-row" href="#wk-{wk}"><span class="week-name">Week {wk}</span>'
           f'<span class="week-meta">{md(s)} — {md(e)}, {e.year} · BRIEF A+B PENDING{row_suffix(w)}</span><span class="arr" aria-hidden="true">↓</span></a></li>')
    rows = [(int(x.group(1)), x.start()) for x in re.finditer(r'<li><a class="week-row" href="#wk-(\d+)">', src)]
    pos = next((p for n, p in rows if n < wk), None)
    if pos is None:
        pos = src.index("</ul>", src.index('class="week-list"')); return src[:pos] + "  " + row + "\n    " + src[pos:]
    return src[:pos] + row + "\n      " + src[pos:]

def render_into(src, w):
    loc = find_week(src, w["week"])
    if loc:
        src = src[:loc[0]] + apply_to_block(src[loc[0]:loc[1]], w) + src[loc[1]:]
    else:
        olds = [(int(m.group(1)), m.start()) for m in re.finditer(r'<section class="wk" id="wk-(\d+)">', src)]
        nxt = next((pos for n, pos in olds if n < w["week"]), None) or src.index('<section class="brk-band">')
        src = src[:nxt] + apply_to_block(stub_block(w), w) + "\n\n  " + src[nxt:]
    return set_row(src, w)

def load(start):
    p = path_for(start)
    return json.loads(p.read_text()) if p.exists() else None

def cmd_render(a):
    weeks = [load(s) for s in a.starts] if a.starts else all_weeks()
    src = INDEX.read_text()
    for w in weeks:
        if w is None: sys.exit("no Brief C data for a requested week")
        src = render_into(src, w)
    INDEX.write_text(src)
    write_concepts()
    print("rendered Brief C for weeks:", ", ".join(str(w["week"]) for w in weeks))

# ---------------------------------------------------------------- concepts page
def write_concepts():
    weeks = all_weeks()
    nav = "".join(f'<li><a class="week-row" href="#wk-{w["week"]}"><span class="week-name">Week {w["week"]}</span>'
                  f'<span class="week-meta">{len(w["concepts"])} CONCEPTS · {len(w["videos"])} TALKS</span><span class="arr" aria-hidden="true">↓</span></a></li>'
                  for w in weeks)
    secs = ""
    for w in weeks:
        wk = w["week"]; s = dt.date.fromisoformat(w["start"]); e = dt.date.fromisoformat(w["end"])
        kind = "Reviewed concepts" if w["concept_kind"] == "reviewed" else "Editorial synthesis"
        gap = "".join(f'<aside class="callout aie-gap"><span class="boxlabel">{l}</span><p>{esc(t)}</p></aside>'
                      for l, t in (("May be incomplete", w.get("gap")), ("Partial week", w.get("partial"))) if t)
        top = set(w["top"])
        arts = "".join(f'<article class="tcard aie-concept" id="c-{wk}-{i+1}"><h3>{esc(c["title"])}</h3>'
                       f'<span class="badge">{"<b>Strongest idea</b><i>/</i>" if i in top else ""}Week {wk}<i>/</i>{kind}</span>'
                       f'{concept_body(c, page=True)}</article>' for i, c in enumerate(w["concepts"]))
        if not arts: arts = '<div class="notyet">No concepts for this week yet.</div>'
        secs += (f'<section class="wk" id="wk-{wk}"><div class="wkhead"><div class="in"><span class="no">Week {wk}</span>'
                 f'<span class="dt">{md(s)} — {md(e)}</span><a class="fold" href="index.html#aie-{wk}">Brief C ↗</a></div></div>'
                 f'<div class="grp"><p style="padding:12px 20px 0" class="aie-note">{esc(w["coverage"])} {esc(w.get("concept_note", ""))}</p>{gap}{arts}</div></section>\n')
    CONCEPTS.write_text(f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Drift — Brief C concepts (AI Engineer)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chivo:wght@300;400;500;600;700;900&family=Sometype+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top"><div class="w"><span class="wm">Drift<em>/unified</em></span><span class="tools"><a class="back" href="index.html">← All weeks</a></span></div></header>
<main style="color:var(--h-{HUE})">
  <section class="w weeks" aria-labelledby="c-title">
    <h1 id="c-title">Brief C concepts</h1>
    <p class="sub">Ideas from AI Engineer talks, by week. Each idea links to the talks it comes from and to their summaries on the weekly page.</p>
    <p class="sub">Draft. Built from machine-generated summaries, not from the original transcripts, and not human-reviewed. Claims belong to the speakers and their companies and are not independently verified. Quoted excerpts are from the summaries.</p>
    <ul class="week-list">{nav}</ul>
  </section>
{secs}
  <footer><div class="w"><p>Talks from the <a href="{CHANNEL}">AI Engineer YouTube channel</a>. <a href="index.html">Back to all weeks</a></p></div></footer>
</main>
</body>
</html>
''')

# ---------------------------------------------------------------- check
def cmd_check(a):
    weeks = all_weeks(); ids = {}; bad = 0
    for w in weeks:
        for v in w["videos"]:
            if v["id"] in ids: print("duplicate", v["id"], w["week"], ids[v["id"]]); bad += 1
            ids[v["id"]] = w["week"]
            m = YT.match(v["url"])
            if not m or m.group(1) != v["id"]: print("bad link", v["id"]); bad += 1
        blob = json.dumps(w)
        for m in LEAK.finditer(blob): print("possible leak", w["week"], m.group(0)); bad += 1
    for w in weeks:
        print(f"week {w['week']}: {len(w['videos'])} talks, {len(w['concepts'])} concepts, "
              f"{sum(1 for v in w['videos'] if v.get('caption_source') is True)} auto-caption")
    print("total talks", len(ids), "problems", bad)
    sys.exit(1 if bad else 0)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    h = sp.add_parser("import-historical"); h.add_argument("pack"); h.add_argument("--year", type=int, default=2026)
    p = sp.add_parser("import-preview"); p.add_argument("preview")
    r = sp.add_parser("render"); r.add_argument("starts", nargs="*")
    sp.add_parser("check")
    a = ap.parse_args()
    {"import-historical": cmd_import_historical, "import-preview": cmd_import_preview,
     "render": cmd_render, "check": cmd_check}[a.cmd](a)

if __name__ == "__main__":
    main()
