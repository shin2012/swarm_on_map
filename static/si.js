/* Swarm Insights 공통 데이터·그리기 (PC·모바일 공용) */
(function () {
  const WD = ['일', '월', '화', '수', '목', '금', '토'];
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const pad = n => String(n).padStart(2, '0');
  const M = t => moment.unix(t);

  const SI = { WD, esc, pad, all: [], byVenue: {} };

  SI.load = async function () {
    const raw = await (await fetch('/api/data?t=' + Date.now())).json();
    const all = raw.map(d => ({ ...d, FSQ_UNIXTIME: parseInt(d.FSQ_UNIXTIME), latNum: parseFloat(d.LAT), lngNum: parseFloat(d.LNG) }))
      .filter(d => d.FSQ_UNIXTIME > 0 && !isNaN(d.latNum)).sort((a, b) => a.FSQ_UNIXTIME - b.FSQ_UNIXTIME);
    const byVenue = {};
    all.forEach((d, i) => { d.no = i + 1; (byVenue[d.VENUE] = byVenue[d.VENUE] || []).push(d); });
    SI.all = all; SI.byVenue = byVenue;
    return all;
  };

  // 주소에서 구·시·군 하나
  SI.gu = d => {
    const w = (d.ADDRESS || '').split(/\s+/).find(x => /(구|시|군)$/.test(x) && !/(특별시|광역시|특별자치시)$/.test(x));
    return w || (d.CITY && d.CITY !== 'Unknown' ? d.CITY : '');
  };
  SI.match = (d, q) => !q || d.VENUE.toLowerCase().includes(q) || (d.CATEGORY && d.CATEGORY.toLowerCase().includes(q));

  // 날짜별로 묶은 목록 HTML (최근 것이 위)
  SI.listHTML = function (items, selT) {
    if (!items.length) return '<div class="vempty">이 기간·검색어에 맞는 방문이 없어요</div>';
    let html = '', cur = '';
    items.forEach(d => {
      const m = M(d.FSQ_UNIXTIME), key = m.format('YYYYMMDD');
      if (key !== cur) {
        cur = key;
        html += `<div class="vday"><b>${m.format('M월 D일')}</b><small>${WD[m.day()]}요일 · ${m.year()}</small></div>`;
      }
      const g = SI.gu(d);
      html += `<div class="vrow${d.SHOUT ? ' has-s' : ''}${d.FSQ_UNIXTIME === selT ? ' sel' : ''}" data-t="${d.FSQ_UNIXTIME}">
        <span class="vt">${m.format('HH:mm')}</span>
        <span class="vb"><span class="vn"><span>${esc(d.VENUE)}</span></span><span class="vm">${esc(d.CATEGORY || '분류 없음')}${g ? ` <i>· ${esc(g)}</i>` : ''}</span>${d.SHOUT ? `<span class="vs">“${esc(d.SHOUT)}”</span>` : ''}</span>
        <span class="vno">${d.no.toLocaleString()}</span></div>`;
    });
    return html;
  };

  SI.visitInfo = d => {
    const list = SI.byVenue[d.VENUE] || [d], k = list.indexOf(d), prev = k > 0 ? list[k - 1] : null;
    return { nth: k + 1, total: list.length, prev };
  };

  SI.popupHTML = function (d) {
    const m = M(d.FSQ_UNIXTIME), v = SI.visitInfo(d);
    return `<div class="pop-t">${m.format('YYYY.MM.DD')} (${WD[m.day()]}) ${m.format('HH:mm')}</div>
      <div class="pop-n">${esc(d.VENUE)}</div>
      <div class="pop-m">${esc(d.CATEGORY || '분류 없음')}${SI.gu(d) ? ' · ' + esc(SI.gu(d)) : ''}</div>
      ${d.SHOUT ? `<div class="pop-s">“${esc(d.SHOUT)}”</div>` : ''}
      ${d.PHOTO ? `<img src="${esc(d.PHOTO)}" class="pop-img" loading="lazy" alt="">` : ''}
      <div class="pop-a"><span>이 장소 <b>${v.nth}</b>/${v.total}번째</span><span>·</span><span>전체 <b>${d.no.toLocaleString()}</b>번째 방문</span></div>`;
  };

  // 재생 카드 채우기
  SI.fillNP = function (d, i, n) {
    const m = M(d.FSQ_UNIXTIME), v = SI.visitInfo(d), $ = id => document.getElementById(id);
    const set = (id, t) => { const e = $(id); if (e) e.textContent = t; };
    set('np-date', m.format('M.DD') + ' ' + WD[m.day()]);
    set('np-time', m.format('HH:mm'));
    set('np-venue', d.VENUE);
    set('np-sub', (d.ADDRESS || '').replace(/^\d{5}\s*/, '').replace(/^대한민국\s*/, '') || d.CATEGORY || '');
    set('np-cat', d.CATEGORY || '분류 없음');
    set('np-prev', v.prev ? '이전 ' + M(v.prev.FSQ_UNIXTIME).format('YYYY.MM.DD') : '첫 방문');
    set('np-cnt', `이 장소 ${v.nth}/${v.total}`);
    set('np-no', d.no.toLocaleString());
    set('np-prog', `${i + 1} / ${n}`);
    // 순번으로 만든 막대 무늬
    const code = $('np-code');
    if (code) {
      let h = 2166136261; for (const c of String(d.FSQ_ID || d.no)) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0;
      let s = ''; for (let k = 0; k < 30; k++) { h = Math.imul(h, 1103515245) + 12345 >>> 0; s += `<i style="width:${1 + (h >>> 29) % 3}px;margin-right:${1 + (h >>> 26) % 2}px"></i>`; }
      code.innerHTML = s;
    }
  };

  /* ── 통계 ── */
  const charts = {};
  function chart(canvas, cfg) {
    if (!canvas) return;
    if (charts[canvas.id]) charts[canvas.id].destroy();
    charts[canvas.id] = new Chart(canvas.getContext('2d'), cfg);
  }
  SI.periodLabel = p => ({ '7': '최근 1주', '30': '최근 1개월', '90': '최근 3개월', '365': '최근 1년', all: '전체 기간' })[p] || '';
  SI.inPeriod = function (p) {
    const all = SI.all; if (!all.length) return [];
    if (p === 'all') return all;
    const last = all[all.length - 1].FSQ_UNIXTIME, cut = last - parseInt(p) * 86400;
    return all.filter(d => d.FSQ_UNIXTIME >= cut);
  };

  SI.renderStats = function (root, period, opt) {
    opt = opt || {};
    const data = SI.inPeriod(period), P = UI.pal(), q = s => root.querySelector(s);
    const range = q('[data-st=range]');
    if (range && data.length) range.textContent = `${M(data[0].FSQ_UNIXTIME).format('YYYY.MM.DD')} — ${M(data[data.length - 1].FSQ_UNIXTIME).format('YYYY.MM.DD')}`;
    // 요약 문장
    const venues = new Set(data.map(d => d.VENUE)).size;
    const cMap = {}, rMap = {}, vMap = {}; const wArr = Array(7).fill(0), hArr = Array(24).fill(0);
    const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
    const days = new Set();
    data.forEach(d => {
      const m = M(d.FSQ_UNIXTIME), wd = m.day(), h = m.hour();
      if (d.CATEGORY) cMap[d.CATEGORY] = (cMap[d.CATEGORY] || 0) + 1;
      if (d.CITY && d.CITY !== 'Unknown') rMap[d.CITY] = (rMap[d.CITY] || 0) + 1;
      vMap[d.VENUE] = (vMap[d.VENUE] || 0) + 1;
      wArr[wd]++; hArr[h]++; grid[wd][h]++; days.add(m.format('YYYY-MM-DD'));
    });
    const sortedDays = [...days].sort(); let best = 0, run = 0;
    sortedDays.forEach((d, i) => { run = i && moment(d).diff(moment(sortedDays[i - 1]), 'days') === 1 ? run + 1 : 1; best = Math.max(best, run); });
    const topCat = Object.entries(cMap).sort((a, b) => b[1] - a[1])[0];
    const topDay = WD[wArr.indexOf(Math.max(...wArr))];
    const topHour = hArr.indexOf(Math.max(...hArr));
    const sum = q('[data-st=sum]');
    if (sum) sum.innerHTML = data.length ? `${SI.periodLabel(period)} 동안 <b>${data.length.toLocaleString()}번</b> 방문했고, 다녀간 곳은 <b>${venues.toLocaleString()}곳</b>이에요.
      가장 많이 간 분류는 <b>${esc(topCat ? topCat[0] : '–')}</b>, 가장 자주 움직인 때는 <b>${topDay}요일 ${topHour}시</b> 무렵.
      최장 <b>${best}일</b> 연속으로 기록했고, 기록한 날엔 하루 평균 <b>${(data.length / Math.max(sortedDays.length, 1)).toFixed(1)}번</b> 남겼어요.` : '이 기간엔 기록이 없어요.';

    const font = { family: P.font, size: opt.small ? 10 : 11 };
    const base = {
      responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: { backgroundColor: P.ink, titleColor: P.bg, bodyColor: P.bg, padding: 10, cornerRadius: 4, displayColors: false } },
      scales: { x: { grid: { display: false }, border: { color: P.sub }, ticks: { color: P.sub, font, maxRotation: 0, autoSkipPadding: 10 } },
        y: { beginAtZero: true, grid: { color: P.grid }, border: { display: false }, ticks: { color: P.sub, font, precision: 0 } } },
    };
    // 월별 추이
    const tMap = {}; data.forEach(d => { const k = M(d.FSQ_UNIXTIME).format('YY.MM'); tMap[k] = (tMap[k] || 0) + 1; });
    const tL = Object.keys(tMap).sort();
    chart(q('[data-st=timeline] canvas'), { type: 'line', data: { labels: tL, datasets: [{ data: tL.map(k => tMap[k]), borderColor: P.accent, backgroundColor: P.heat(.12), fill: true, borderWidth: 2, tension: .3, pointRadius: tL.length > 30 ? 0 : 3, pointBackgroundColor: P.accent }] }, options: base });
    // 시간대
    chart(q('[data-st=hourly] canvas'), { type: 'bar', data: { labels: hArr.map((_, i) => i + '시'), datasets: [{ data: hArr, backgroundColor: hArr.map((_, i) => i === topHour ? P.accent : P.accent2), borderRadius: 2, barPercentage: .8 }] }, options: base });
    // 요일
    chart(q('[data-st=weekday] canvas'), { type: 'bar', data: { labels: WD.map(w => w + '요일'), datasets: [{ data: wArr, backgroundColor: wArr.map(v => v === Math.max(...wArr) ? P.accent : P.accent2), borderRadius: 2, barPercentage: .7 }] }, options: base });
    // 신규 방문지
    const first = {}; data.forEach(d => { if (!first[d.VENUE]) first[d.VENUE] = M(d.FSQ_UNIXTIME).format('YY.MM'); });
    const nMap = {}; Object.values(first).forEach(k => nMap[k] = (nMap[k] || 0) + 1);
    const nL = Object.keys(nMap).sort().slice(-18);
    chart(q('[data-st=newv] canvas'), { type: 'bar', data: { labels: nL, datasets: [{ data: nL.map(k => nMap[k]), backgroundColor: P.accent, borderRadius: 2, barPercentage: .7 }] }, options: base });
    // 순위 표
    const ranks = (sel, map, n) => {
      const el = q(sel); if (!el) return;
      const rows = Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, n || 8), mx = rows.length ? rows[0][1] : 1;
      el.innerHTML = rows.length ? `<table class="ranks">${rows.map(([k, v], i) => `<tr><td class="r">${i + 1}</td><td class="n">${esc(k)}</td><td class="c"><div class="bar" style="width:${Math.max(4, v / mx * 100)}%"></div></td><td class="v">${v.toLocaleString()}</td></tr>`).join('')}</table>` : '<div class="vempty">없음</div>';
    };
    ranks('[data-st=cats] .rk', cMap); ranks('[data-st=regions] .rk', rMap); ranks('[data-st=venues] .rk', vMap);
    // 요일×시간
    const act = q('[data-st=activity] .act-wrap');
    if (act) {
      const mx = Math.max(...grid.flat(), 1);
      let t = '<table class="act"><tr><td class="d"></td>';
      for (let h = 0; h < 24; h++) t += `<td>${h % 3 === 0 ? h : ''}</td>`;
      t += '</tr>';
      grid.forEach((row, d) => {
        t += `<tr><td class="d">${WD[d]}</td>`;
        row.forEach((v, h) => { const a = v ? .12 + v / mx * .88 : .05; t += `<td title="${WD[d]}요일 ${h}시 ${v}번" style="background:${P.heat(a.toFixed(2))}"></td>`; });
        t += '</tr>';
      });
      act.innerHTML = t + '</table>';
    }
  };

  window.SI = SI;
})();
