// Caught Up (formerly Drift): progressive enhancement. Every page reads without this file.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement;
  const ls = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fmt = (m) => {
    const h = Math.floor(m / 60), mm = Math.round(m % 60);
    if (h && mm) return `${h} h ${mm} min`;
    return h ? `${h} h` : `${mm} min`;
  };
  const press = (b, on) => b.setAttribute('aria-pressed', on ? 'true' : 'false');
  const pressed = (b) => b.getAttribute('aria-pressed') === 'true';

  // ---- theme: the button names the theme you would switch to
  const themeBtn = $('[data-theme-toggle]');
  const theme = () => root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const paintTheme = () => { if (themeBtn) themeBtn.textContent = theme() === 'dark' ? 'Paper' : 'Night'; };
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const next = theme() === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next; ls.set('drift.theme', next); paintTheme();
    });
    paintTheme();
  }

  // ---- titles only: one setting, a toggle in each view that has items
  const titleBtns = $$('[data-titles]');
  const paintTitles = () => titleBtns.forEach((b) => press(b, root.dataset.density === 'compact'));
  paintTitles();
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-titles]')) return;
    const on = root.dataset.density !== 'compact';
    if (on) root.dataset.density = 'compact'; else delete root.dataset.density;
    ls.set('drift.titles', on ? '1' : '0');
    paintTitles();
  });

  // ---- done state + time budget
  let done;
  try { done = new Set(JSON.parse(ls.get('drift.done') || '[]')); } catch (e) { done = new Set(); }
  const budget = $('.budget');
  const planItems = $$('#plan .it[data-min]');
  let shownLeft = null, raf = 0;
  const paintBudget = (animate) => {
    if (!budget) return;
    const total = planItems.reduce((a, it) => a + +it.dataset.min, 0);
    const open = planItems.filter((it) => !done.has(it.id));
    const left = open.reduce((a, it) => a + +it.dataset.min, 0);
    const nDone = planItems.length - open.length;
    const out = $('[data-left]', budget);
    $('[data-left-l]', budget).textContent = nDone ? `left of ${fmt(total)}` : 'listed';
    $('[data-done-l]', budget).textContent = nDone ? `${nDone} of ${planItems.length} done` : `${planItems.length} items`;
    cancelAnimationFrame(raf);
    if (!animate || calm || shownLeft === null) { out.textContent = left ? fmt(left) : 'All done'; shownLeft = left; return; }
    const from = shownLeft, t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 420), e = 1 - Math.pow(1 - k, 4);
      shownLeft = from + (left - from) * e;
      out.textContent = k === 1 && !left ? 'All done' : fmt(Math.round(shownLeft));
      if (k < 1) raf = requestAnimationFrame(step); else shownLeft = left;
    };
    raf = requestAnimationFrame(step);
  };
  const paintDone = (id) => {
    const on = done.has(id);
    const it = document.getElementById(id);
    if (it) it.classList.toggle('is-done', on);
    $$(`.tick[data-id="${CSS.escape(id)}"]`).forEach((b) => press(b, on));
    $$(`.rs[data-id="${CSS.escape(id)}"]`).forEach((s) => s.classList.toggle('is-done', on));
  };
  $$('.tick').forEach((b) => paintDone(b.dataset.id));
  paintBudget(false);
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.tick');
    if (!b) return;
    const id = b.dataset.id;
    if (done.has(id)) done.delete(id); else done.add(id);
    ls.set('drift.done', JSON.stringify([...done]));
    paintDone(id);
    paintBudget(true);
  });

  // ---- ruler readout: hovering or focusing a block names it
  const readout = $('[data-readout]');
  if (readout) {
    const say = (t) => { readout.textContent = t || readout.dataset.default; readout.classList.toggle('is-live', !!t); };
    $$('.rs').forEach((s) => {
      s.addEventListener('pointerenter', () => say(s.dataset.label));
      s.addEventListener('focus', () => say(s.dataset.label));
      s.addEventListener('pointerleave', () => say(''));
      s.addEventListener('blur', () => say(''));
    });
  }

  // ---- "time I have"
  const timeBox = $('[data-time]');
  if (timeBox) {
    const status = $('[data-time-status]', timeBox);
    const apply = (max) => {
      let fit = 0;
      planItems.forEach((it) => {
        const ok = !max || +it.dataset.min <= max;
        it.hidden = !ok; if (ok) fit++;
        $$(`.rs[data-id="${it.id}"]`).forEach((s) => s.classList.toggle('is-out', !ok));
      });
      $$('#plan [data-grp]').forEach((g) => { g.hidden = !$$('.it', g).some((it) => !it.hidden); });
      status.textContent = max ? (fit ? `${fit} of ${planItems.length} fit` : 'Nothing that short this week') : '';
    };
    timeBox.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-max]');
      if (!b) return;
      $$('button[data-max]', timeBox).forEach((x) => press(x, x === b));
      apply(+b.dataset.max);
    });
  }

  // ---- highlight today in the day-by-day plan
  const sched = $('.sched[data-from]');
  if (sched) {
    const from = new Date(sched.dataset.from + 'T00:00:00');
    const now = new Date();
    const days = Math.floor((now - from) / 864e5);
    if (days >= 0 && days < 7) {
      const name = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][now.getDay()];
      const li = $(`li[data-day="${name}"]`, sched);
      if (li) li.classList.add('is-today');
    }
  }

  // ---- reddit: one subreddit at a time
  const subs = $('[data-subs]');
  if (subs) {
    subs.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-sub]');
      if (!b) return;
      const want = b.dataset.sub;
      $$('button[data-sub]', subs).forEach((x) => press(x, x === b));
      $$('#reddit section[data-sub]').forEach((s) => { s.hidden = !!want && s.dataset.sub !== want; });
      const empty = $('#reddit [data-sub-empty]');
      if (empty) empty.hidden = !!want;
    });
  }

  // ---- talks: topics and text
  const talks = $('[data-talks]');
  if (talks) {
    const q = $('[data-talk-q]', talks), status = $('[data-talk-status]', talks), none = $('[data-talk-none]', talks);
    const rows = $$('.it', talks), togs = $$('button[data-topic]', talks);
    const apply = () => {
      const want = togs.filter(pressed).map((b) => b.dataset.topic);
      const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
      let n = 0;
      rows.forEach((r) => {
        const tp = r.dataset.topics.split('|');
        const ok = (!want.length || want.some((w) => tp.includes(w))) && terms.every((t) => r.dataset.text.includes(t));
        r.hidden = !ok; if (ok) n++;
      });
      const active = want.length || terms.length;
      status.textContent = active ? `${n} of ${rows.length} talks` : '';
      none.hidden = n > 0;
    };
    talks.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-topic]');
      if (b) { press(b, !pressed(b)); apply(); return; }
      if (e.target.closest('[data-talk-clear]')) { togs.forEach((x) => press(x, false)); q.value = ''; apply(); q.focus(); }
    });
    q.addEventListener('input', apply);
  }

  // ---- search page
  const sq = $('[data-search-q]');
  if (sq) {
    const out = $('[data-search-out]'), status = $('[data-search-status]');
    const escH = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const hi = (s, terms) => {
      let h = escH(s);
      terms.forEach((t) => {
        const re = new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        h = h.replace(/(<[^>]*>)|([^<]+)/g, (m, tag, txt) => tag || txt.replace(re, '<mark>$1</mark>'));
      });
      return h;
    };
    const snip = (s, terms) => {
      const low = s.toLowerCase();
      let at = -1;
      terms.forEach((t) => { const i = low.indexOf(t); if (i > -1 && (at < 0 || i < at)) at = i; });
      const a = Math.max(0, at - 70), cut = s.slice(a, a + 240);
      return (a ? '… ' : '') + cut + (a + 240 < s.length ? ' …' : '');
    };
    const run = () => {
      const data = window.DRIFT_SEARCH || [];
      const terms = sq.value.toLowerCase().split(/\s+/).filter((t) => t.length > 1);
      if (!terms.length) { out.innerHTML = ''; status.textContent = 'Type at least two letters.'; return; }
      const hits = [];
      data.forEach((d) => {
        const t = d.t.toLowerCase(), all = t + ' ' + d.m.toLowerCase() + ' ' + d.s.toLowerCase();
        if (!terms.every((x) => all.includes(x))) return;
        hits.push([terms.reduce((a, x) => a + (t.includes(x) ? 3 : 1), 0) * 100 + d.w, d]);
      });
      hits.sort((a, b) => b[0] - a[0]);
      status.textContent = hits.length ? `${hits.length} result${hits.length === 1 ? '' : 's'}${hits.length > 80 ? ', showing the first 80' : ''}` : 'Nothing found. Try a shorter word.';
      out.innerHTML = hits.slice(0, 80).map(([, d]) =>
        `<article class="res"><p class="res-k"><b>${d.k}</b>Week ${d.w}</p><div><h4><a href="${escH(d.u)}">${hi(d.t, terms)}</a></h4>` +
        `<p class="by">${hi(d.m, terms)}</p><p class="sum">${hi(snip(d.s, terms), terms)}</p></div></article>`).join('');
    };
    const init = new URLSearchParams(location.search).get('q') || '';
    sq.value = init;
    const top = $('#q'); if (top) top.closest('.find').hidden = true;
    let timer = 0;
    sq.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 90); });
    sq.form.addEventListener('submit', (e) => { e.preventDefault(); history.replaceState(null, '', '?q=' + encodeURIComponent(sq.value)); run(); });
    window.addEventListener('load', run);
    if (!init) sq.focus();
  }

  // ---- "/" focuses search
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    const box = $('[data-search-q]') || $('#q');
    if (box) { e.preventDefault(); box.focus(); }
  });
})();
