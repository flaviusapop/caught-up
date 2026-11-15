# Caught Up (formerly Drift Unified): the weekly site

> Renamed on Nov 15, 2026. The public pages say **Caught Up**, with the line "Catching up with AI, one week at a time."
> The name and the line are the constants `NAME` and `TAGLINE` at the top of `redesign/build.py`.
> The repo was renamed from `drift-unified-prototype` to `caught-up` the same day. The site address is now
> https://flaviusapop.github.io/caught-up/ ; the old address no longer serves the site.
> A local checkout keeps working (GitHub forwards the old git address), but set the new one once:
> `git remote set-url origin https://github.com/flaviusapop/caught-up.git`. The local folder name
> (`/workspace/drift-unified-prototype` in the commands below) does not need to change.
> The `classic/` page and the browser storage keys (`drift.*`) keep the old name.

> As of Oct 25, 2026 this is the official Drift version we keep updating (Zander). The older notes below are kept for history.

## Site layout since Nov 15, 2026 (redesign)

The public site is now **generated**. The weekly routine below is unchanged: same commands, same order.

- `classic/index.html` is the working file. `add_week.py build` and `aie_brief.py render` edit it exactly as
  they edited `index.html` before. `classic/` also holds the old `style.css`, `app.js` and `concepts.html`;
  the old single page stays viewable at `/classic/`.
- `redesign/build.py` reads `classic/index.html` and `weeks-data/aie-*.json` and writes the public pages at the
  repo root: `index.html` (the newest week), `week-NN.html` (one per week), `search.html`,
  `search-data.js`, `assets/`, and `ideas.html` + `concepts.html` (redirects: ideas live in each week's Talks view).
  **Both scripts call it at the end**, so there is no extra step. To run it alone: `python3 redesign/build.py`.
- Never edit the root `*.html`, `search-data.js` or `assets/` by hand: the next build overwrites them.
  Design changes go in `redesign/src/style.css`, `redesign/src/app.js` and `redesign/build.py`.
- Each week page has four views: Start here, Plan (Brief A), Reddit (Brief B), Talks (Brief C).
  Start here opens with the Practical block when the week has one (see "Practical section" below).
  Old anchors still work from `index.html`: `#wk-NN`, `#learning-NN`, `#reddit-NN`, `#aie-NN`, `#aie-<videoid>`.
- If `redesign/build.py` fails, the script exits with an error after `classic/index.html` is already updated.
  Do not publish in that state: fix or report the error, then rerun `python3 redesign/build.py`.
  The build prints one line per week (plan items, threads kept, talks); a week showing `plan 0 items` or
  `reddit None` that should have content means the parser did not recognise the block.
- `redesign/build.py` depends on the HTML structure `add_week.py` and `aie_brief.py` write (class names such as
  `wk`, `src`, `grp`, `grph`, `tcard`, `badge`, `subsrc`, `bbsynth`, `tc-item`). If that markup changes, update the
  parser in `redesign/build.py` in the same commit.
- Fonts (Recia, Supreme) load from the Fontshare CDN; no font files are in the repo.
- Known limit: weeks are keyed by ISO week number only (`week-46.html`), so a second year needs a naming change.

### Practical section

Each week page opens with **Practical this week** at the top of Start here, above the plan, Reddit and talks.
It lists up to 5 practical workflows and skills shared on X and Reddit that week, ranked by engagement,
without anything already in that week's Brief A (plan) or Brief B (Reddit). Weeks without a data file
render exactly as before (no block).

```bash
# weekly, after add_week.py build (the week must already be in classic/index.html) and before git add
python3 practical.py check  $START   # validate + print which entries are kept or skipped; writes nothing
python3 practical.py render $START   # write/replace the block in classic/index.html, then run redesign/build.py
```

- The build line gains `practical N` (number shown). `practical None` means no data file for that week; that is
  normal for weeks before Nov 9, 2026.
- `add_week.py build` keeps the block on rebuild when the file exists (`--no-practical` leaves it out), and
  `aie_brief.py render` leaves it alone. Rerunning `render` gives the same output (no diff).
- Classic markup: `<!-- Practical:start wk-NN -->` … `<!-- Practical:end wk-NN -->` with
  `<section class="src" id="practical-NN">` and `article.tcard.pr-card` cards, right after the week header.
  `redesign/build.py` (`parse_practical`) reads it. Public anchors: `week-NN.html#practical-NN` (or `#practical`),
  one card `#pr-NN-<n>`; `index.html#practical-NN` and `index.html#pr-NN-<n>` redirect to the week page. Search lists the cards as "Practical".

**File:** `weeks-data/<monday>-practical.json`

```json
{
  "week": 46, "start": "2026-11-09",
  "window": "Mon Nov 9, 2026 00:00 to Sun Nov 15, 2026 23:59, Europe/Bucharest",
  "method": "How posts were filtered and ranked (shown under 'How these were picked').",
  "pools": {"reddit": 13, "x": 5},
  "items": [ /* up to 5, each with a rank */ ],
  "runners_up": [ /* next entries, best first; rank may be null */ ]
}
```

Each entry in `items` and `runners_up`:

| field | type | notes |
| --- | --- | --- |
| `rank` | int, or null in `runners_up` | `items` are read in rank order |
| `title` | string, required | editorial title; `` `code` `` is shown as code |
| `platform` | `"x"` or `"reddit"`, required | |
| `author` | string or null | `@handle` or `u/name` |
| `community` | string or null | for example `r/ClaudeAI` (optional, added to the proposed schema) |
| `url` | `https://` string, required | the post itself; used by the skip rule |
| `posted_at` | ISO 8601 with offset, or null | for example `2026-11-11T16:07:00+02:00` |
| `engagement` | object or null | X: `likes`, `reposts`, `replies`, `bookmarks`; Reddit: `score`, `comments` |
| `native_score` | int or null | with `engagement` given, every count the formula uses must be there and add up; with `engagement` null the total alone is accepted |
| `percentile` | 0–1 or null | within the post's own platform; never rises down the list, null only at the end |
| `summary`, `try_it`, `caveats` | string or null | plain text for a public reader (no private notes); bare `https://` links become links |

Missing data stays `null` and is simply not shown. Never fill a number or a link that the source did not give.
Unknown keys, a wrong `native_score`, `true`/`false` where a number belongs, two entries for the same post, more
than 5 `items`, or an order that does not follow `percentile` stop `render` before anything is written.

`pools` is the size of the whole filtered pool per platform (the N of the percentile). The file may list fewer
entries than that, never more. `window` is a string or null.

**Ranking (done by the collector, not by the script):** X native = likes + reposts × 2 + replies;
Reddit native = score + comments × 2. Percentile inside each platform = (N − rank + 1) / N; then both
platforms are merged by percentile. The script keeps the order it is given: `items` by rank, then
`runners_up` in list order, and checks it: walking that order, `percentile` may stay equal or fall, never rise.
An entry whose percentile cannot be worked out stays `null` and goes last (null is allowed only at the tail).
When a pool is larger than the list, the listed posts are taken as the top of that pool.

**Skip rule (done by the script):** walking that order, an entry is skipped when its post is already linked
anywhere in the same week's Brief A or Brief B (same Reddit thread id, same X status id, same YouTube video id,
or same host + path + query without tracking parameters), when its normalised title equals a Brief A or Brief B
card title, or when a link written in its `summary` or `try_it` is already linked in Brief A or Brief B. The first 5 that are left are shown,
renumbered 1–5. Skipped titles are listed under "How these were picked".

**Prototype only.** A third, separate site to iterate on Zander's unified
2-brief-per-week idea in the Drift design. It does **not** replace or modify
the live sites:

- Live Drift: https://flaviusapop.github.io/ai-digest/drift.html (repo `flaviusapop/ai-digest`)
- Live learning plan: https://flaviusapop.github.io/weekly-ai-learning-plan/ (repo `flaviusapop/weekly-ai-learning-plan`)

Live prototype: https://flaviusapop.github.io/caught-up/

## Idea

One Drift-design site, 2 briefs per week, synced in timing/format:

1. **Brief A — AI Learning** (working title, TODO: rename — naming exploration
   runs separately): exactly 3 Must Watch + agents/workflows,
   investing/trading, product/building; ~10h; no short-form, no vendor content.
2. **Brief B — Reddit Deep-Dive** (working title, TODO: rename): priority
   threads, comments worth quoting, what changes for a real setup.
   Planned sources: r/hermesagent, r/Hermes, r/OpenClaw, r/AI_Agents,
   r/ClaudeAI, r/ClaudeCode, r/cursor, r/LocalLLaMA, r/ChatGPT, r/OpenAI.

Names are placeholders (`Brief A / Brief B`) until Zander picks final names.
Implementation of the collector/scheduler is intentionally **not** started —
this repo only proves the unified layout. The unified spec (how the two
digests combine) is still to be decided by Zander.

## Layout

- `index.html` — THE single landing page: weeks stacked newest-first on one page (Week 42 full Brief A + Brief B, Weeks 41/40 as not-collected blocks), with a minimal in-page anchor jump list at the top
- `weeks/2026-10-12.html` — redirect stub to `index.html#wk-42` (the week now lives on the landing page)
  Drift style: `Brief/Week header · date range · strip · Fold all`,
  foldable sections (Brief A and Brief B sticky tabs sit directly together), and inside Brief B ten full-size subreddit section headers (big hue display heading, Core/Secondary pill, rule, scanned/kept/shown stat) starting under Brief B's own header; r/hermesagent carries the Brief 35 sample, the other 9 subreddits are 'not yet collected' placeholders, priority-thread cards, top-comments folds
- `style.css` — Drift design DNA copied read-only from `flaviusapop/ai-digest`
  (`src/drift.html`: cream/dark editorial, Chivo + Sometype Mono, 660px
  measure, mobile-first) + small prototype additions (banner, cards)
- `app.js` — fold/unfold, Fold all, Compact (key-points) toggle; no backend

Visual system: `style.css` is the original Drift stylesheet verbatim plus a small additions block that reuses only original Drift tokens/patterns (type scale, `--h-*` hues, `.brk-band` divider, `.srch/.srtoggle` subreddit headers, original fold motion). No invented sizes, colours or transitions.

Sample content is clearly labelled PROTOTYPE: Brief A reuses the Oct 18
learning-plan structure; Brief B reuses Drift Brief 35 (Aug 21–26, 2026)
structure/headline. Neither is a new collected edition.

## How to iterate

1. Edit HTML/CSS/JS directly (plain static, no build step).
2. Add a week: copy `weeks/2026-10-12.html`, change the Week header/date,
   replace sample cards, and add a matching week section + anchor row in `index.html`.
3. Rename briefs: search for `Brief A` / `Brief B` once final names land.
4. Publish: `git add -A && git commit -m "..." && git push` — GitHub Pages
   serves `main` / root, redeploys in ~1 min.
5. Verify: `curl -s -o /dev/null -w '%{http_code}\n' https://flaviusapop.github.io/caught-up/`

## Add a week (repeatable)

One script, `add_week.py`, adds or replaces one Mon–Sun week on `classic/index.html`
(newest first), then regenerates the public pages with `redesign/build.py`. It never touches other weeks. Inputs: the week's learning-plan
markdown (Brief A) and the Monday start date. Brief B (Reddit) has an agent
curation step in the middle.

Key: `/home/box/.config/redditapis.env` (`REDDITAPIS_API_KEY=...`). The script
reads it from that file only (the shell env var is not used). Read-only GETs;
never post, vote or DM. Raw responses go to `data-cache/<start>/` (gitignored),
and the call count plus the last `X-Credits-Remaining` value go to
`data-cache/<start>/calls.json`.

```bash
cd /workspace/drift-unified-prototype && git pull --rebase origin main
START=2026-10-26                      # Monday of the week
PLAN=/workspace/plan-2026-11-01.md    # that week's learning plan (Sunday edition)

# 1. Collect: 1 call per subreddit (10 calls). Top 100 of the past week if run
#    within 7 days of START, otherwise paginates sort=new (--mode new).
python3 add_week.py collect $START
#    -> data-cache/$START/candidates.md  (in-window posts, ranked, with snippets)
#    -> weeks-data/$START.json            (skeleton, created once)

# 2. Curate (agent): in weeks-data/$START.json pick threads with real signal per
#    subreddit (workflows, setups, measured results, cost/memory/security lessons;
#    not score alone; usually 0-3 per sub), set "id", "summary", "kp".
#    Set "note" for subs with nothing kept, plus "headline", "executive_read"
#    (HTML paragraphs), "for_our_setup", optional "method".
python3 add_week.py comments $START   # 1 call per kept thread, cached
#    -> data-cache/$START/comments.md ; put 1-2 comment ids in each thread's "quotes"

# 3. Build: insert/replace the week block in classic/index.html, jump-list row, weeks/$START.html redirect,
#    then regenerate index.html, week-NN.html, ideas.html and the search index (redesign/build.py)
python3 add_week.py build $PLAN $START

# 4. Publish + verify (Pages redeploys in ~1 min)
git add -A && git commit -m "Add Week NN" && git push
sleep 75 && curl -s https://flaviusapop.github.io/caught-up/ | grep -c 'id="wk-NN"'
```

Re-running `build` for the same week replaces that week in place. Week ids are
ISO week numbers (`wk-43` = Oct 19–25, 2026). The committed `weeks-data/<start>.json`
holds the curation, so a week can be rebuilt from cache without new API calls.
Cost: about (10 + kept threads) calls × $0.002.

## Brief C — AI Engineer (optional)

Talk summaries from the AI Engineer YouTube channel (https://www.youtube.com/@aidotengineer),
placed in the Mon–Sun week of each talk's publish date. Data: `weeks-data/aie-<monday>.json`
(derived summaries and concepts only — never transcripts, private URLs or local paths).
Working files: `classic/index.html#aie-<videoid>` (talk cards) and `classic/concepts.html` (anchors `#c-<week>-<n>`).
Public pages: `week-NN.html#t-<videoid>` (talks) and `week-NN.html#idea-<week>-<n>` (concepts, in the Talks view).

```bash
# weekly, before or after add_week.py build (save the Hermes preview to a local file first,
# outside the repo; never commit it or its URL)
python3 aie_brief.py import-preview /path/outside/repo/preview.html  # places talks by publish date, skips ids already on any week
python3 aie_brief.py check                    # duplicates, link/id pairing, leak scan
python3 aie_brief.py render                   # (re)writes Brief C in classic/ for every week with data, then regenerates the public pages
```

`add_week.py build` keeps Brief C automatically when `weeks-data/aie-<monday>.json` exists
(`--no-brief-c` leaves it out). Without that file, build behaves exactly as before.
