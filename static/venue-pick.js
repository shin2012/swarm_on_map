/* 근처 장소 후보 (manage.html · m/index.html 공용)
 * 서버 /api/manage/candidates · /api/manage/resolve · /api/manage/geocode (venue.py — daily-yoseop 과 같은 규칙)
 *   한국: 포스퀘어 장소면 포스퀘어 값 그대로 + 주소만 '{우편번호} 대한민국 {행정구역} {도로명} {건물}'
 *         포스퀘어에 없으면 카카오 장소(Kakao_<번호>), 둘 다 없으면 직접 입력(Manual_Venue__<초>)
 *   해외: 카카오 안 씀, 포스퀘어 값 그대로, 주소가 부실하면 OpenStreetMap
 */
(function () {
    const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const SRC = { swarm: '내 체크인', fsq: '포스퀘어', kakao: '카카오', addr: '주소' };
    const GROUPS = [['mine', '내 체크인'], ['fsq', '포스퀘어 근처'], ['kakao', '카카오 근처'], ['addr', '이 위치 주소로']];

    function tag(c) {
        if (c.both) return (c.from === 'swarm' ? '내 체크인' : '포스퀘어') + '+카카오';
        return SRC[c.from] || '';
    }

    function injectStyle() {
        if (document.getElementById('vp-style')) return;
        const st = document.createElement('style');
        st.id = 'vp-style';
        st.textContent = `
        .vp-box { margin-top: 10px; max-height: 42vh; overflow-y: auto; -webkit-overflow-scrolling: touch; }
        .vp-h { font-size: .75em; font-weight: 700; color: var(--text-mute, var(--mute)); margin: 10px 2px 4px; }
        .vp-item { padding: 9px 4px; border-top: 1px solid var(--border); cursor: pointer; }
        .vp-item:active, .vp-item:hover { background: var(--bg2, var(--bg)); }
        .vp-top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
        .vp-name { font-weight: 700; font-size: .92em; }
        .vp-name small { font-weight: 500; color: var(--text-mute, var(--mute)); margin-left: 4px; }
        .vp-m { font-size: .75em; color: var(--text-mute, var(--mute)); white-space: nowrap; }
        .vp-sub { font-size: .75em; color: var(--text-mute, var(--mute)); margin-top: 2px; line-height: 1.35; }
        .vp-tag { font-size: .7em; font-weight: 700; color: var(--primary, var(--secondary)); margin-right: 4px; }
        .vp-msg { font-size: .8em; color: var(--text-mute, var(--mute)); padding: 8px 2px; }
        .vp-note { font-size: .75em; color: var(--text-mute, var(--mute)); margin-top: 6px; }`;
        document.head.appendChild(st);
    }

    /** 좌표 근처 후보를 box 에 그림. 고르면 onPick(저장 값) 호출. */
    async function show(box, lat, lng, q, onPick) {
        injectStyle();
        box.classList.add('vp-box');
        box.innerHTML = '<div class="vp-msg">근처 장소 찾는 중…</div>';
        let data;
        try {
            const r = await fetch(`/api/manage/candidates?lat=${lat}&lng=${lng}&q=${encodeURIComponent(q || '')}`);
            data = await r.json();
            if (data.error) throw new Error(data.error);
        } catch (e) {
            box.innerHTML = `<div class="vp-msg">후보를 못 불러왔어요 (${esc(e.message)})</div>`;
            return null;
        }
        const all = [];
        let html = '';
        for (const [k, title] of GROUPS) {
            const list = data[k] || [];
            if (!list.length) continue;
            html += `<div class="vp-h">${title}</div>`;
            for (const c of list) {
                const i = all.push(c) - 1;
                const name = c.from === 'addr' ? '이 위치 (직접 입력)' : c.name;
                html += `<div class="vp-item" data-i="${i}">
                    <div class="vp-top"><span class="vp-name">${esc(name)}${c.sub ? `<small>${esc(c.sub)}</small>` : ''}</span>
                    <span class="vp-m">${c.from === 'addr' ? '' : (c.m || 0) + 'm'}</span></div>
                    <div class="vp-sub"><span class="vp-tag">${esc(tag(c))}</span>${esc([c.category, c.why && c.why !== c.category ? c.why : '', c.from === 'addr' ? c.address : ''].filter(Boolean).join(' · '))}</div>
                </div>`;
            }
        }
        box.innerHTML = html || '<div class="vp-msg">근처에 후보가 없어요</div>';
        box.querySelectorAll('.vp-item').forEach(el => el.onclick = async () => {
            const c = all[+el.dataset.i];
            el.style.opacity = .5;
            const v = await resolve(c);
            el.style.opacity = '';
            if (v) onPick(v, c);
        });
        return all;
    }

    async function resolve(cand) {
        try {
            const r = await fetch('/api/manage/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cand }) });
            const v = await r.json();
            if (v.error) throw new Error(v.error);
            return v;
        } catch (e) {
            alert('장소 값을 못 정했어요: ' + e.message);
            return null;
        }
    }

    /** 좌표 → {address, city, country, cc} (한국 카카오, 해외 OpenStreetMap) */
    async function geocode(lat, lng) {
        try {
            const r = await fetch(`/api/manage/geocode?lat=${lat}&lng=${lng}`);
            const j = await r.json();
            return j.error ? null : j;
        } catch (_) { return null; }
    }

    window.VenuePick = { show, resolve, geocode };
})();
