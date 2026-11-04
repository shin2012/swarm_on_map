/* 이동 경로 재생 (PC·모바일 공용)
   const pb = Playback.create(map, { onStart(list), onStep(d, i, n), onEnd() });
   pb.start(list, speedMs) · pb.stop() · pb.playing */
(function () {
  const toRad = d => d * Math.PI / 180, toDeg = r => r * 180 / Math.PI;
  function km(a, b) {
    const dLat = toRad(b[0] - a[0]), dLng = toRad(b[1] - a[1]);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }
  // 대권 위의 t(0~1) 지점
  function gc(a, b, t) {
    const la1 = toRad(a[0]), ln1 = toRad(a[1]), la2 = toRad(b[0]), ln2 = toRad(b[1]);
    const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((ln2 - ln1) / 2) ** 2));
    if (d < 1e-6) return a;
    const A = Math.sin((1 - t) * d) / Math.sin(d), B = Math.sin(t * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(ln1) + B * Math.cos(la2) * Math.cos(ln2);
    const y = A * Math.cos(la1) * Math.sin(ln1) + B * Math.cos(la2) * Math.sin(ln2);
    const z = A * Math.sin(la1) + B * Math.sin(la2);
    return [toDeg(Math.atan2(z, Math.sqrt(x * x + y * y))), toDeg(Math.atan2(y, x))];
  }
  // 멀수록 곡선을 촘촘히
  function seg(from, to) {
    const k = km(from, to);
    const n = k > 5000 ? 120 : k > 1000 ? 80 : k > 300 ? 50 : k > 100 ? 25 : k > 30 ? 8 : k > 5 ? 3 : 1;
    return n === 1 ? [to] : Array.from({ length: n }, (_, i) => gc(from, to, (i + 1) / n));
  }
  const ease = t => t < .5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

  function create(map, cb) {
    cb = cb || {};
    let list = [], idx = 0, speed = 400, timer = null, raf = null, line = null, cur = null, dots = [], bounds = null;
    const api = { playing: false };
    const pad = () => (cb.padding && cb.padding()) || [60, 60];

    function curMarker(ll) {
      if (cur) return cur.setLatLng(ll);
      cur = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="pb-now"><i></i><b></b></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), zIndexOffset: 1000 }).addTo(map);
    }
    function dot(ll) {
      const p = UI.pal();
      dots.push(L.circleMarker(ll, { radius: 4, color: p.trail, fillColor: p.bg, fillOpacity: 1, weight: 2, opacity: .9 }).addTo(map));
    }
    function fit(dur) {
      if (bounds) map.fitBounds(bounds, { paddingTopLeft: pad()[0], paddingBottomRight: pad()[1], maxZoom: 14, animate: true, duration: dur });
    }
    function animate(pts, dur, done) {
      const t0 = performance.now(); let drawn = -1;
      (function frame(now) {
        if (!api.playing) return;
        const pr = Math.min((now - t0) / dur, 1), target = Math.ceil(ease(pr) * pts.length) - 1;
        for (let i = drawn + 1; i <= target && i < pts.length; i++) line.addLatLng(pts[i]);
        if (target > drawn) drawn = Math.min(target, pts.length - 1);
        if (drawn >= 0) curMarker(pts[drawn]);
        if (pr < 1) raf = requestAnimationFrame(frame);
        else { line.addLatLng(pts[pts.length - 1]); curMarker(pts[pts.length - 1]); done(); }
      })(t0);
    }
    function step() {
      if (!api.playing) return;
      if (idx >= list.length) { api.playing = false; cb.onEnd && cb.onEnd(); return; }
      const d = list[idx], ll = [d.latNum, d.lngNum], prev = idx ? [list[idx - 1].latNum, list[idx - 1].lngNum] : null;
      bounds = bounds ? bounds.extend(ll) : L.latLngBounds([ll, ll]);
      cb.onStep && cb.onStep(d, idx, list.length);
      if (!prev) {
        line.addLatLng(ll); curMarker(ll); dot(ll); fit(Math.min(speed / 1000, .8));
        idx++; timer = setTimeout(step, speed * .5); return;
      }
      const k = km(prev, ll), dur = k > 300 ? speed * 1.8 : k > 100 ? speed * 1.3 : speed * .8;
      fit((dur / 1000) * .9);
      animate(seg(prev, ll), dur, () => {
        if (!api.playing) return;
        dot(ll); idx++;
        timer = setTimeout(step, k > 300 ? speed * .6 : speed * .15);
      });
    }

    api.start = function (data, ms) {
      api.stop(true);
      if (!data || !data.length) return false;
      list = data; idx = 0; speed = ms || 400; bounds = null; api.playing = true;
      const p = UI.pal();
      line = L.polyline([], { color: p.line, weight: 3, opacity: .9, lineCap: 'round', lineJoin: 'round' }).addTo(map);
      cb.onStart && cb.onStart(list);
      map.fitBounds(L.latLngBounds(list.map(d => [d.latNum, d.lngNum])), { paddingTopLeft: pad()[0], paddingBottomRight: pad()[1], maxZoom: 13, animate: true, duration: 1.2 });
      timer = setTimeout(step, 1400);
      return true;
    };
    api.setSpeed = ms => { speed = ms; };
    api.stop = function (silent) {
      const was = api.playing || line;
      api.playing = false;
      clearTimeout(timer); timer = null;
      if (raf) cancelAnimationFrame(raf); raf = null;
      if (line) map.removeLayer(line); line = null;
      if (cur) map.removeLayer(cur); cur = null;
      dots.forEach(m => map.removeLayer(m)); dots = [];
      bounds = null;
      if (was && !silent && cb.onStop) cb.onStop();
    };
    return api;
  }
  window.Playback = { create };
})();
