/* 네이버 지도 바탕: Leaflet 지도 밑에 네이버 지도를 깔고 위치·확대를 그대로 맞춘다.
   마커·클러스터·히트맵·재생 같은 위의 것들은 전부 Leaflet이 그대로 그린다.
   - 지도 가운데가 한국이고 확대 7 이상 → 네이버 지도 (CARTO 타일은 뺌)
   - 해외, 너무 축소, 네이버 로드 실패·인증 실패 → 기존 Leaflet 타일
   사용: NaverBase.attach(map, { tiles: () => 타일레이어, theme: 'light'|'dark'|'voyager'|'satellite' })
         테마를 바꾼 뒤엔 map._nv.setTheme(t) */
(function () {
  const KEY = window.NAVER_MAP_KEY_ID || '';
  const MIN_ZOOM = 7;
  let state = KEY ? 'idle' : 'failed';   // idle → loading → ready | failed
  let loading = null;
  const insts = new Set();

  // 대략적인 한국 범위. 쓰시마·규슈(경도 129.15 넘고 위도 34.9 아래)는 일본
  const inKR = (lat, lng) => lat >= 33 && lat <= 38.7 && lng >= 124.5 && lng <= 132 && !(lng > 129.15 && lat < 34.9);

  function fail(why) {
    if (state === 'failed') return;
    state = 'failed';
    console.warn('[NaverBase] 네이버 지도 사용 안 함:', why);
    insts.forEach(i => i.disable());
  }

  const prevFail = window.navermap_authFailure;
  window.navermap_authFailure = function () {
    if (prevFail) try { prevFail(); } catch (e) {}
    fail('인증 실패(키 또는 등록 도메인)');
  };

  function load() {
    if (state === 'failed') return Promise.reject();
    if (loading) return loading;
    state = 'loading';
    loading = new Promise((ok, no) => {
      const done = () => window.naver && naver.maps && naver.maps.Map;
      if (done()) return ok();
      const s = document.createElement('script');
      s.src = 'https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=' + encodeURIComponent(KEY);
      s.async = true;
      const t = setTimeout(() => no('시간 초과'), 6000);
      s.onerror = () => { clearTimeout(t); no('스크립트 로드 실패'); };
      s.onload = () => {   // maps.js가 본체를 한 번 더 불러오는 경우가 있어 잠깐 기다림
        const t0 = Date.now();
        (function wait() {
          if (done()) { clearTimeout(t); return ok(); }
          if (Date.now() - t0 > 4000) { clearTimeout(t); return no('naver.maps 없음'); }
          setTimeout(wait, 50);
        })();
      };
      document.head.appendChild(s);
    }).then(() => { if (state !== 'failed') state = 'ready'; }, e => { fail(e); throw e; });
    return loading;
  }

  class Inst {
    constructor(lmap, o) {
      this.l = lmap;
      this.getTiles = o.tiles || (() => null);
      this.theme = o.theme || 'light';
      this.n = null;
      this.on = false;
      this.dead = false;
      // 타일 레이어를 빼면 지도의 최대 확대가 무한대가 되어 markercluster가 멈춤 → 지금 값을 지도에 박아 둠
      const t0 = this.getTiles();
      if (lmap.options.maxZoom === undefined) lmap.options.maxZoom = (t0 && t0.options.maxZoom) || 18;
      if (lmap.options.minZoom === undefined) lmap.options.minZoom = (t0 && t0.options.minZoom) || 0;
      const c = lmap.getContainer();
      const el = this.el = document.createElement('div');
      el.className = 'nv-base';
      el.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;z-index:0;pointer-events:none;visibility:hidden;transform-origin:0 0;';
      c.insertBefore(el, c.firstChild);

      lmap.on('move zoom viewreset', () => this.sync());
      lmap.on('moveend zoomend', () => { this.sync(); this.decide(); });
      lmap.on('zoomanim', e => this.anim(e));
      lmap.on('resize', () => { if (this.n) { this.n.setSize(new naver.maps.Size(c.clientWidth, c.clientHeight)); this.sync(); } });
      lmap.on('unload', () => { this.dead = true; insts.delete(this); });
      insts.add(this);
      this.decide();
    }

    wanted() {
      if (state === 'failed' || this.dead) return false;
      const z = this.l.getZoom(), ctr = this.l.getCenter();
      return z >= MIN_ZOOM && inKR(ctr.lat, ctr.lng);
    }

    decide() {
      if (!this.wanted()) return this.off();
      if (this.n) return this.show();
      load().then(() => {
        if (this.dead || state === 'failed') return;
        this.create();
        if (this.wanted()) this.show();
      }, () => this.off());
    }

    create() {
      const N = naver.maps, ctr = this.l.getCenter(), c = this.l.getContainer();
      this.n = new N.Map(this.el, {
        center: new N.LatLng(ctr.lat, ctr.lng),
        zoom: Math.floor(this.l.getZoom() + 1e-6),
        size: new N.Size(c.clientWidth || 300, c.clientHeight || 300),
        draggable: false, pinchZoom: false, scrollWheel: false, keyboardShortcuts: false,
        disableDoubleClickZoom: true, disableDoubleTapZoom: true, disableTwoFingerTapZoom: true,
        disableKineticPan: true, tileTransition: false,
        zoomControl: false, mapTypeControl: false, mapDataControl: false, scaleControl: false,
        logoControl: true, logoControlOptions: { position: N.Position.BOTTOM_LEFT },
        minZoom: 1, maxZoom: 21,
      });
      this.applyTheme();
    }

    applyTheme() {
      if (!this.n) return;
      const N = naver.maps;
      this.n.setMapTypeId(this.theme === 'satellite' ? N.MapTypeId.HYBRID : N.MapTypeId.NORMAL);
      // 네이버는 어두운 지도가 없어 색을 뒤집어 비슷하게 만든다
      this.el.style.filter = this.theme === 'dark' ? 'invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.9)' : '';
    }

    setTheme(t) { this.theme = t; this.applyTheme(); this.refresh(); }

    // 테마를 바꾸며 타일을 새로 붙였을 때 등: 지금 상태에 맞게 다시 정리
    refresh() { if (this.on) this.hideTiles(); this.decide(); }

    hideTiles() {
      const t = this.getTiles();
      if (t && this.l.hasLayer(t)) this.l.removeLayer(t);
    }

    showTiles() {
      const t = this.getTiles();
      if (t && !this.l.hasLayer(t)) t.addTo(this.l);
      return t;
    }

    show() {
      if (this.on) return;
      this.on = true;
      this.el.style.visibility = 'visible';
      this.sync();
      this.hideTiles();
    }

    off() {
      if (!this.on) { this.showTiles(); return; }
      this.on = false;
      const t = this.showTiles();
      // CARTO 타일이 다 깔릴 때까지 네이버를 잠깐 남겨 빈 화면 깜빡임을 줄임
      let gone = false;
      const hide = () => { if (gone || this.on) return; gone = true; this.el.style.visibility = 'hidden'; };
      if (t) t.once('load', hide);
      setTimeout(hide, 1200);
    }

    disable() { this.off(); }

    // Leaflet의 현재 화면(소수 확대 포함)에 네이버를 맞춤
    sync() {
      if (!this.n || !this.on || this._animating) return;
      const N = naver.maps, ctr = this.l.getCenter(), z = this.l.getZoom();
      const zi = Math.floor(z + 1e-6);   // 내림 → 늘 1배 이상 확대라 가장자리 빈칸이 안 생김
      if (this.n.getZoom() !== zi) this.n.setZoom(zi, false);
      this.n.setCenter(new N.LatLng(ctr.lat, ctr.lng));
      const k = Math.pow(2, z - zi), sz = this.l.getSize();
      this.el.style.transition = '';
      // 가운데 기준 k배 = 원점(0,0) 기준 scale(k) 후 c(1-k)만큼 이동 (애니메이션과 같은 꼴로 맞춰 둠)
      this.el.style.transform = Math.abs(k - 1) < 1e-6 ? '' :
        `translate(${sz.x / 2 * (1 - k)}px, ${sz.y / 2 * (1 - k)}px) scale(${k})`;
    }

    // +/- 버튼·휠·더블탭 같은 애니메이션 확대: Leaflet과 같은 움직임을 CSS로 흉내
    anim(e) {
      if (!this.n || !this.on) return;
      const p = this.l.latLngToContainerPoint(e.center);
      const sz = this.l.getSize();
      const k = Math.pow(2, e.zoom - this.n.getZoom());
      const kNow = Math.pow(2, this.l.getZoom() - this.n.getZoom());
      // 지금 화면의 점 p는 네이버 원래 화면에선 o. 끝나면 o가 가운데에 k배로 와야 함 → x ↦ c + k(x - o)
      const ox = sz.x / 2 + (p.x - sz.x / 2) / kNow, oy = sz.y / 2 + (p.y - sz.y / 2) / kNow;
      this._animating = true;
      this.el.style.transition = 'transform 0.25s cubic-bezier(0,0,0.25,1)';
      this.el.style.transform = `translate(${sz.x / 2 - k * ox}px, ${sz.y / 2 - k * oy}px) scale(${k})`;
      clearTimeout(this._at);
      const end = () => { this._animating = false; this.sync(); };
      this.l.once('zoomend', () => { clearTimeout(this._at); end(); });
      this._at = setTimeout(end, 400);
    }
  }

  window.NaverBase = {
    inKR,
    attach(lmap, o) { const i = new Inst(lmap, o || {}); lmap._nv = i; return i; },
    get state() { return state; },
  };
})();
