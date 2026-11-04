/* Swarm Insights 공통 화면 도구
   - 화면 테마 2가지: diary(공책 다이어리) · board(탑승권·출발 안내판). html[data-theme]로 바꿈
   - 지도 바탕: auto · light · dark · satellite
   - 설정 창(UI.openSettings), 아이콘(UI.ic), 차트·선 색(UI.pal)
   설정은 localStorage에 저장되고 모든 화면(PC·관리·모바일)이 같이 씀 */
(function () {
  const KEY = { theme: 'si.theme', tiles: 'si.tiles' };
  const THEMES = {
    diary: { name: '공책 다이어리', desc: '흰 종이 줄노트, 형광펜 선택, 종이 자로 기간 고르기' },
    board: { name: '탑승권·안내판', desc: '검은 출발 안내판 목록, 재생 중엔 탑승권' },
  };
  const TILES = { auto: '테마에 맞춤', light: '밝게', dark: '어둡게', satellite: '위성' };

  const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const set = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };

  const UI = {
    THEMES, TILES,
    theme: () => { const t = get(KEY.theme, 'diary'); return THEMES[t] ? t : 'diary'; },
    tiles: () => { const t = get(KEY.tiles, 'auto'); return TILES[t] ? t : 'auto'; },
    // 실제로 깔 바탕: auto면 테마에 맞춰 밝은 지도
    tileKind() { const t = UI.tiles(); return t === 'auto' ? 'light' : t; },

    setTheme(t) {
      if (!THEMES[t]) return;
      set(KEY.theme, t);
      document.documentElement.dataset.theme = t;
      UI.emit();
    },
    setTiles(t) { if (!TILES[t]) return; set(KEY.tiles, t); UI.emit(); },
    emit() { window.dispatchEvent(new CustomEvent('ui:change', { detail: { theme: UI.theme(), tiles: UI.tiles() } })); },

    // 캔버스(차트·지도 선)에서 쓸 색 — CSS 변수는 캔버스가 못 읽어서 여기 따로 둠
    pal() {
      return UI.theme() === 'board' ? {
        ink: '#F1F1EC', sub: '#8C929C', grid: 'rgba(255,255,255,.08)', bg: '#111317',
        accent: '#FFC23D', accent2: '#F1F1EC', line: '#111317', lineNow: '#FFC23D', trail: '#111317',
        series: ['#FFC23D', '#F1F1EC', '#8C929C', '#E8833A', '#5FB3A1', '#C9A0DC', '#6E8BBF', '#B58A2C'],
        heat: (a) => `rgba(255,194,61,${a})`, font: "'JetBrains Mono', ui-monospace, monospace",
      } : {
        ink: '#1D2742', sub: '#6C7385', grid: 'rgba(29,39,66,.08)', bg: '#FBFBF7',
        accent: '#E0574F', accent2: '#1D2742', line: '#E0574F', lineNow: '#1D2742', trail: '#E0574F',
        series: ['#1D2742', '#E0574F', '#6C9BD2', '#E8B23A', '#7DB38E', '#B48CC8', '#E89A7E', '#9AA3B5'],
        heat: (a) => `rgba(224,87,79,${a})`, font: "'Pretendard Variable', Pretendard, sans-serif",
      };
    },

    // lucide 아이콘을 SVG 문자열로 (동적 HTML 안에서 쓰기)
    ic(name, cls) {
      if (!window.lucide) return '';
      const key = name.replace(/(^|-)(\w)/g, (_, __, c) => c.toUpperCase());
      const node = lucide.icons && lucide.icons[key];
      if (!node) return '';
      const el = lucide.createElement(node);
      el.setAttribute('class', 'lucide' + (cls ? ' ' + cls : ''));
      return el.outerHTML;
    },
    icons() { if (window.lucide) lucide.createIcons(); },

    // 설정 창
    openSettings() {
      let el = document.getElementById('settings');
      if (!el) {
        el = document.createElement('div');
        el.id = 'settings';
        el.innerHTML = `<div class="set-dim"></div><div class="set-panel" role="dialog" aria-label="설정">
          <div class="set-head"><b>설정</b><button class="ib set-x" aria-label="닫기">${UI.ic('x')}</button></div>
          <div class="set-sec"><div class="set-lab">화면 테마</div><div class="set-themes">
            ${Object.entries(THEMES).map(([k, v]) => `<button class="set-th" data-t="${k}">
              <span class="th-prev th-${k}"><i></i><i></i><i></i><i></i></span>
              <span class="th-txt"><b>${v.name}</b><small>${v.desc}</small></span></button>`).join('')}
          </div></div>
          <div class="set-sec"><div class="set-lab">지도 바탕</div><div class="seg set-tiles">
            ${Object.entries(TILES).map(([k, v]) => `<button data-k="${k}">${v}</button>`).join('')}
          </div><p class="set-note">국내는 네이버 지도, 해외는 오픈스트리트맵으로 그려요.</p></div>
        </div>`;
        document.body.appendChild(el);
        const close = () => el.classList.remove('open');
        el.querySelector('.set-dim').onclick = close;
        el.querySelector('.set-x').onclick = close;
        document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
        el.querySelectorAll('.set-th').forEach(b => b.onclick = () => { UI.setTheme(b.dataset.t); sync(); });
        el.querySelectorAll('.set-tiles button').forEach(b => b.onclick = () => { UI.setTiles(b.dataset.k); sync(); });
      }
      const sync = () => {
        el.querySelectorAll('.set-th').forEach(b => b.classList.toggle('on', b.dataset.t === UI.theme()));
        el.querySelectorAll('.set-tiles button').forEach(b => b.classList.toggle('on', b.dataset.k === UI.tiles()));
      };
      sync();
      requestAnimationFrame(() => el.classList.add('open'));
    },
  };

  // 지도 타일
  const CARTO = 'cb1_2mra_1_20f52391c4787f3b6ed18089';
  const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
  const URLS = {
    light: `https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${CARTO}`,
    dark: `https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=${CARTO}`,
    satellite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  };
  // Leaflet 지도에 바탕(타일 + 네이버)을 깔고, 설정이 바뀌면 따라 바꿈
  UI.baseMap = function (map) {
    let tiles = null;
    const make = () => L.tileLayer(URLS[UI.tileKind()], { attribution: UI.tileKind() === 'satellite' ? 'Esri' : ATTR, maxZoom: 19 });
    tiles = make().addTo(map);
    const nv = window.NaverBase ? NaverBase.attach(map, { tiles: () => tiles, theme: UI.tileKind() }) : null;
    window.addEventListener('ui:change', () => {
      map.removeLayer(tiles);
      tiles = make().addTo(map);
      if (nv) nv.setTheme(UI.tileKind());
    });
    return { get tiles() { return tiles; } };
  };

  document.documentElement.dataset.theme = UI.theme();
  window.UI = UI;
})();
