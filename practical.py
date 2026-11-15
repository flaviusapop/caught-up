#!/usr/bin/env python3
"""Practical: the week's top practical workflows and skills from X and Reddit.

Each week page on Caught Up opens with a "Practical" block (top of Start here, above the
plan, Reddit and talks). It lists up to 5 workflows or skills people shared that week,
ranked by engagement, leaving out anything already in that week's Brief A (plan) or
Brief B (Reddit).

    python3 practical.py check  2026-11-09        # validate + show what the skip rule keeps; writes nothing
    python3 practical.py render 2026-11-09        # write the week's Practical block, then rebuild the site
    python3 practical.py render                   # every week that has a weeks-data/*-practical.json

Data: weeks-data/<monday>-practical.json (see README, "Practical section").
Order: items (by rank), then runners_up (in list order). The skip rule walks that order,
drops entries whose URL (or normalised title) already appears in Brief A or Brief B of
the same week in classic/index.html, and keeps the first 5 left.

The block lives in classic/index.html between <!-- Practical:start wk-NN --> and
<!-- Practical:end wk-NN -->, right after the week header. Rerunning replaces it in
place, so the output is the same on every run. add_week.py build keeps it on rebuild.
"""
import argparse, datetime as dt, html, json, pathlib, re, subprocess, sys
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parent
WDATA = ROOT / "weeks-data"
INDEX = ROOT / "classic" / "index.html"
TOP_N = 5
esc = lambda s: html.escape(s or "", quote=True)

ENG_KEYS = {"x": ("likes", "reposts", "replies", "bookmarks"), "reddit": ("score", "comments")}
ITEM_KEYS = {"rank", "title", "platform", "author", "community", "url", "posted_at", "engagement",
             "native_score", "percentile", "summary", "try_it", "caveats"}
TOP_KEYS = {"week", "start", "window", "method", "pools", "items", "runners_up"}


# ---------------------------------------------------------------- data
def path_for(start):
    return WDATA / f"{start}-practical.json"


def all_starts():
    return sorted((p.name[:10] for p in WDATA.glob("????-??-??-practical.json")), reverse=True)


def native(platform, e):
    """X: likes + reposts x 2 + replies. Reddit: score + comments x 2. None if a count is missing."""
    try:
        if platform == "x":
            return e["likes"] + e["reposts"] * 2 + e["replies"]
        return e["score"] + e["comments"] * 2
    except (KeyError, TypeError):
        return None


def validate(d, start):
    """Return a list of problems (empty when the file is fine)."""
    errs = []
    if not isinstance(d, dict):
        return ["top level must be an object"]
    for k in sorted(set(d) - TOP_KEYS):
        errs.append(f"unknown top-level key {k!r}")
    try:
        mon = dt.date.fromisoformat(d.get("start", ""))
        if mon.isoformat() != start:
            errs.append(f"start {d.get('start')!r} does not match the file name ({start})")
        if mon.weekday() != 0:
            errs.append(f"start {mon} is not a Monday")
        wk = mon.isocalendar()[1]
        if d.get("week") is not None and d["week"] != wk:
            errs.append(f"week {d['week']} does not match start {mon} (ISO week {wk})")
    except (TypeError, ValueError):
        errs.append("start must be the Monday as YYYY-MM-DD")
    if not isinstance(d.get("method"), str) or not d["method"].strip():
        errs.append("method must be a non-empty string")
    if d.get("pools") is not None and not (isinstance(d["pools"], dict) and all(
            k in ENG_KEYS and isinstance(v, int) and v >= 0 for k, v in d["pools"].items())):
        errs.append("pools must be like {\"reddit\": 13, \"x\": 5}")
    items, runners = d.get("items"), d.get("runners_up", [])
    if not isinstance(items, list):
        errs.append("items must be a list")
        items = []
    elif len(items) > TOP_N:
        errs.append(f"items has {len(items)} entries; at most {TOP_N}")
    if not isinstance(runners, list):
        errs.append("runners_up must be a list")
        runners = []
    seen = {}
    for where, lst in (("items", items), ("runners_up", runners)):
        for i, it in enumerate(lst):
            at = f"{where}[{i}]"
            if not isinstance(it, dict):
                errs.append(f"{at} must be an object")
                continue
            for k in sorted(set(it) - ITEM_KEYS):
                errs.append(f"{at}: unknown key {k!r}")
            for k in ("title", "url", "platform"):
                if not isinstance(it.get(k), str) or not it[k].strip():
                    errs.append(f"{at}: {k} is required")
            p = it.get("platform")
            if p not in ENG_KEYS:
                errs.append(f"{at}: platform must be 'x' or 'reddit'")
            url = it.get("url") or ""
            if url and not re.match(r"https://", url):
                errs.append(f"{at}: url must start with https://")
            key = url_key(url) if url else None
            if key and key in seen:
                errs.append(f"{at}: same post as {seen[key]}")
            elif key:
                seen[key] = at
            for k in ("author", "community", "summary", "try_it", "caveats"):
                if it.get(k) is not None and not isinstance(it[k], str):
                    errs.append(f"{at}: {k} must be a string or null")
            if it.get("rank") is not None and not (isinstance(it["rank"], int) and it["rank"] > 0):
                errs.append(f"{at}: rank must be a positive whole number or null")
            if where == "items" and it.get("rank") is None:
                errs.append(f"{at}: items need a rank")
            if it.get("posted_at") is not None:
                try:
                    t = dt.datetime.fromisoformat(it["posted_at"])
                    if t.tzinfo is None:
                        errs.append(f"{at}: posted_at needs a UTC offset (for example +02:00)")
                except (TypeError, ValueError):
                    errs.append(f"{at}: posted_at must be ISO 8601")
            e = it.get("engagement")
            if e is not None:
                if not isinstance(e, dict) or p not in ENG_KEYS:
                    errs.append(f"{at}: engagement must be an object or null")
                else:
                    for k, v in e.items():
                        if k not in ENG_KEYS[p]:
                            errs.append(f"{at}: engagement key {k!r} is not one of {', '.join(ENG_KEYS[p])}")
                        elif v is not None and not (isinstance(v, int) and v >= 0):
                            errs.append(f"{at}: engagement.{k} must be a whole number >= 0 or null")
            ns = it.get("native_score")
            if ns is not None and not isinstance(ns, int):
                errs.append(f"{at}: native_score must be a whole number or null")
            elif ns is not None and e and p in ENG_KEYS:
                calc = native(p, e)
                if calc is not None and calc != ns:
                    errs.append(f"{at}: native_score {ns} does not match the engagement counts ({calc})")
            pc = it.get("percentile")
            if pc is not None and not (isinstance(pc, (int, float)) and 0 <= pc <= 1):
                errs.append(f"{at}: percentile must be between 0 and 1, or null")
    ranks = [it.get("rank") for it in items if isinstance(it, dict)]
    if len(set(ranks)) != len(ranks):
        errs.append("items: ranks must be unique")
    return errs


def load(start, strict=True):
    p = path_for(start)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"practical.py: {p.name} is not valid JSON: {e}")
    errs = validate(d, start)
    if errs and strict:
        sys.exit(f"practical.py: {p.name} has {len(errs)} problem(s):\n  - " + "\n  - ".join(errs))
    return d


# ---------------------------------------------------------------- skip rule
def url_key(u):
    """Same post, whatever the host spelling: reddit thread id, X status id, else host+path."""
    m = re.search(r"reddit\.com/(?:r/[^/]+/)?comments/([a-z0-9]+)", u, re.I) or re.search(r"redd\.it/([a-z0-9]+)", u, re.I)
    if m:
        return "reddit:" + m.group(1).lower()
    m = re.search(r"(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d+)", u, re.I)
    if m:
        return "x:" + m.group(1)
    s = urlsplit(u.strip())
    host = re.sub(r"^(www|m|old|mobile)\.", "", s.netloc.lower())
    return host + s.path.rstrip("/").lower()


def title_key(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or "")).lower()
    t = re.sub(r"^\d+\.\s+", "", t.strip())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def find_week(src, wk):
    m = re.search(rf'<section class="wk" id="wk-{wk}">', src)
    if not m:
        return None
    depth = 0
    for t in re.finditer(r"<section\b|</section>", src[m.start():]):
        depth += 1 if t.group(0) == "<section" else -1
        if depth == 0:
            return m.start(), m.start() + t.end()
    sys.exit(f"practical.py: unbalanced sections in wk-{wk}")


def section(block, prefix):
    """Inner HTML of <section class="src" id="<prefix>..."> (Brief A: learning, Brief B: reddit)."""
    m = re.search(rf'<section class="src" id="{prefix}(?:-\d+)?"', block)
    if not m:
        return ""
    depth = 0
    for t in re.finditer(r"<section\b|</section>", block[m.start():]):
        depth += 1 if t.group(0) == "<section" else -1
        if depth == 0:
            return block[m.start():m.start() + t.end()]
    return ""


def brief_refs(block):
    """URL keys and title keys of everything linked in Brief A and Brief B of one week block."""
    urls, titles = set(), set()
    for prefix in ("learning", "reddit"):
        sec = section(block, prefix)
        for href in re.findall(r'<a\s[^>]*href="(https?://[^"]+)"', sec):
            urls.add(url_key(html.unescape(href)))
        for t in re.findall(r'<h3><a\s[^>]*>(.*?)</a></h3>', sec, re.S):
            k = title_key(t)
            if len(k) >= 12:
                titles.add(k)
    return urls, titles


def pick(d, block):
    """Apply the skip rule. Returns (kept, skipped) with skipped = [(entry, reason)]."""
    order = sorted(d["items"], key=lambda it: it["rank"]) + list(d.get("runners_up") or [])
    urls, titles = brief_refs(block)
    kept, skipped = [], []
    for it in order:
        if len(kept) == TOP_N:
            break
        if url_key(it["url"]) in urls:
            skipped.append((it, "link already in Brief A or B"))
        elif title_key(it["title"]) in titles:
            skipped.append((it, "title already in Brief A or B"))
        else:
            kept.append(it)
    return kept, skipped


# ---------------------------------------------------------------- render (classic/index.html)
def code(s):
    """Escape, then turn `code` into <code>."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(s))


def text(s):
    """Escape, turn `code` into <code> and bare https links into links."""
    h = code(s)
    return re.sub(r"(https://[^\s<)]+[^\s<).,;:])",
                  lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>', h)


def fmt_n(n):
    return f"{n:,}"


def eng_line(it):
    e, p = it.get("engagement") or {}, it["platform"]
    names = {"likes": "likes", "reposts": "reposts", "replies": "replies", "bookmarks": "bookmarks",
             "score": "points", "comments": "comments"}
    return ", ".join(f"{fmt_n(e[k])} {names[k]}" for k in ENG_KEYS[p] if e.get(k) is not None)


def card(it, n, wk):
    p = it["platform"]
    where = "X" if p == "x" else "Reddit"
    who = " ".join(x for x in (it.get("author"), it.get("community") and f"in {it['community']}") if x)
    attrs = {"data-platform": p}
    if it.get("native_score") is not None:
        attrs["data-native"] = str(it["native_score"])
    if it.get("percentile") is not None:
        attrs["data-pct"] = f"{it['percentile']:g}"
    if it.get("posted_at"):
        attrs["data-posted"] = it["posted_at"]
    if it.get("author"):
        attrs["data-author"] = it["author"]
    if it.get("community"):
        attrs["data-community"] = it["community"]
    if it.get("engagement"):
        attrs["data-eng"] = json.dumps({k: v for k, v in it["engagement"].items() if v is not None}, separators=(",", ":"))
    a = "".join(f' {k}="{esc(v)}"' for k, v in attrs.items())
    badge = [f"<b>{where}</b>"]
    if who:
        badge.append(esc(who))
    if it.get("native_score") is not None:
        badge.append(f"score {fmt_n(it['native_score'])}")
    if it.get("posted_at"):
        t = dt.datetime.fromisoformat(it["posted_at"])
        badge.append(f"{t:%a} {t:%b} {t.day}")
    out = (f'<article class="tcard pr-card" id="pr-{wk}-{n}"{a}>'
           f'<h3><a href="{esc(it["url"])}" target="_blank" rel="noopener">{n}. {code(it["title"])}</a></h3>'
           f'<span class="badge">{"<i>/</i>".join(badge)}</span>')
    if eng_line(it):
        out += f'<p class="pr-eng">{esc(eng_line(it))}</p>'
    if it.get("summary"):
        out += f'<p class="summary">{text(it["summary"])}</p>'
    if it.get("try_it"):
        out += f'<p class="pr-try"><b>Try it:</b> {text(it["try_it"])}</p>'
    if it.get("caveats"):
        out += f'<p class="pr-cav"><b>Caveats:</b> {text(it["caveats"])}</p>'
    return out + "</article>"


def practical_section(d, kept, skipped, wk):
    cards = "".join(card(it, i + 1, wk) for i, it in enumerate(kept))
    if not cards:
        cards = '<div class="notyet">Nothing practical left after removing what Brief A and Brief B already cover.</div>'
    pools = d.get("pools") or {}
    pool = ", ".join(f"{v} {'X' if k == 'x' else 'Reddit'}" for k, v in pools.items())
    meta = []
    if d.get("window"):
        meta.append(f"Window: {d['window']}.")
    if pool:
        meta.append(f"Posts that passed the filter: {pool}.")
    if skipped:
        meta.append(f"Left out because Brief A or Brief B already has them: "
                    + "; ".join(code(it["title"]) for it, _ in skipped) + ".")
    return f'''<!-- Practical:start wk-{wk} -->
    <section class="src" id="practical-{wk}" data-fold="false" style="color:var(--h-xnetwork)">
      <div class="srch"><div class="in"><h2><button class="srtoggle" aria-expanded="true">Practical — workflows and skills</button></h2></div></div>
      <div class="fold-wrap"><div>
<div class="sum hed"><h3 class="issuehed">Practical this week: {len(kept)} workflow{"s" if len(kept) != 1 else ""} and skills from X and Reddit</h3><p class="pr-method">{text(d["method"])}</p><p class="pr-meta">{" ".join(meta)}</p></div>
<div class="grp pr-list"><div class="grph"><span>Top {len(kept)}</span><span>ranked by engagement</span></div>{cards}</div>
      </div></div>
    </section>
    <!-- Practical:end wk-{wk} -->'''


def apply_to_block(block, d, wk=None):
    """Insert or replace the Practical block inside one week block (string). Returns (block, kept, skipped)."""
    wk = wk or dt.date.fromisoformat(d["start"]).isocalendar()[1]
    block = re.sub(rf"\n*[ \t]*<!-- Practical:start wk-{wk} -->.*?<!-- Practical:end wk-{wk} -->", "", block, flags=re.S)
    kept, skipped = pick(d, block)
    m = re.search(r'<div class="wkhead">.*?</div></div>', block, re.S)
    if not m:
        sys.exit(f"practical.py: no week header in wk-{wk}")
    block = block[:m.end()] + "\n\n    " + practical_section(d, kept, skipped, wk) + block[m.end():]
    return block, kept, skipped


def report(wk, kept, skipped):
    print(f"week {wk}: practical {len(kept)} kept, {len(skipped)} skipped")
    for it, why in skipped:
        print(f"  skipped: {it['title']} ({why})")
    for i, it in enumerate(kept, 1):
        src = "items" if it.get("rank") and it["rank"] <= TOP_N else "runners_up"
        print(f"  {i}. {it['title']} [{it['platform']}, from {src}]")


# ---------------------------------------------------------------- commands
def cmd_check(a):
    src = INDEX.read_text(encoding="utf-8")
    bad = 0
    for start in a.starts or all_starts():
        d = load(start, strict=False)
        if d is None:
            print(f"{start}: no {path_for(start).name}")
            bad += 1
            continue
        errs = validate(d, start)
        if errs:
            print(f"{start}: {len(errs)} problem(s):\n  - " + "\n  - ".join(errs))
            bad += 1
            continue
        wk = dt.date.fromisoformat(start).isocalendar()[1]
        loc = find_week(src, wk)
        if not loc:
            print(f"{start}: valid, but week {wk} is not in classic/index.html yet (run add_week.py build first)")
            continue
        block = re.sub(rf"\n*[ \t]*<!-- Practical:start wk-{wk} -->.*?<!-- Practical:end wk-{wk} -->", "",
                       src[loc[0]:loc[1]], flags=re.S)
        report(wk, *pick(d, block))
    sys.exit(1 if bad else 0)


def cmd_render(a):
    starts = a.starts or all_starts()
    if not starts:
        sys.exit("practical.py: no weeks-data/*-practical.json found")
    datas = [(s, load(s)) for s in starts]          # validate everything before writing anything
    src = INDEX.read_text(encoding="utf-8")
    for start, d in datas:
        if d is None:
            sys.exit(f"practical.py: {path_for(start)} not found")
        wk = dt.date.fromisoformat(start).isocalendar()[1]
        loc = find_week(src, wk)
        if not loc:
            sys.exit(f"practical.py: week {wk} is not in classic/index.html; run add_week.py build first")
        block, kept, skipped = apply_to_block(src[loc[0]:loc[1]], d, wk)
        src = src[:loc[0]] + block + src[loc[1]:]
        report(wk, kept, skipped)
    with open(INDEX, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    sys.stdout.flush()
    if not a.no_build:
        subprocess.run([sys.executable, str(ROOT / "redesign" / "build.py")], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check", help="validate and show the skip result; writes nothing")
    c.add_argument("starts", nargs="*", metavar="MONDAY")
    r = sp.add_parser("render", help="write the Practical block into classic/index.html, then rebuild the site")
    r.add_argument("starts", nargs="*", metavar="MONDAY")
    r.add_argument("--no-build", action="store_true", help="skip redesign/build.py (for tests)")
    a = ap.parse_args()
    {"check": cmd_check, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
