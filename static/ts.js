/**
 * ts.js — Tailscale 연결 상태 감지 + UI 반영
 * 모든 서비스에서 공통 사용
 *
 * 사용법:
 *   로그아웃 요소: data-ts-logout 속성 추가
 *   스크립트 로드: <script src="/static/ts.js" defer></script>
 *
 * 동작:
 *   Tailscale 연결 시  → 로그아웃 버튼 자리에 Tailscale 로고(정방형 아이콘) 표시
 *   Tailscale 미연결 시 → 로그아웃 버튼 그대로 유지, 아이콘만 SVG로 교체
 */
(async function() {
  const LOGOUT_SELECTOR = '[data-ts-logout]';

  // Tailscale 로고 SVG (정방형 28×28, 둥근 테두리)
  function tsBadgeHTML(logoutEl) {
    const sz = logoutEl.dataset.tsSize || '28';
    return `<span data-ts-badge="1" title="Tailscale 연결됨" style="
      display:inline-flex;align-items:center;justify-content:center;
      width:${sz}px;height:${sz}px;border-radius:6px;
      background:rgba(0,0,0,0.06);cursor:default;user-select:none;
      vertical-align:middle;flex-shrink:0;">
      <svg width="18" height="18" viewBox="0 0 128 128" fill="none">
        <circle cx="64" cy="32" r="14" fill="#242424"/>
        <circle cx="64" cy="96" r="14" fill="#242424"/>
        <circle cx="32" cy="64" r="14" fill="#242424"/>
        <circle cx="96" cy="64" r="14" fill="#242424"/>
        <circle cx="40" cy="40" r="9" fill="#242424" opacity="0.45"/>
        <circle cx="88" cy="40" r="9" fill="#242424" opacity="0.45"/>
        <circle cx="40" cy="88" r="9" fill="#242424" opacity="0.45"/>
        <circle cx="88" cy="88" r="9" fill="#242424" opacity="0.45"/>
      </svg>
    </span>`;
  }

  // 로그아웃 아이콘 SVG (정방형, 배경색과 대비)
  function logoutIconHTML(logoutEl) {
    const sz = logoutEl.dataset.tsSize || '28';
    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      style="pointer-events:none;flex-shrink:0;">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" y1="12" x2="9" y2="12"/>
    </svg>`;
  }

  // 로그아웃 버튼을 정방형 아이콘 스타일로 정규화
  function normalizeLogoutEl(el) {
    const sz = el.dataset.tsSize || '28';
    el.style.cssText += `;display:inline-flex;align-items:center;justify-content:center;
      width:${sz}px;height:${sz}px;border-radius:6px;flex-shrink:0;`;
    // 텍스트만 있고 아이콘이 없으면 SVG 아이콘으로 교체
    if (!el.querySelector('svg') && !el.querySelector('i')) {
      el.innerHTML = logoutIconHTML(el);
    }
  }

  try {
    const res = await fetch('https://ts.b-612.kr', {
      signal: AbortSignal.timeout(2000),
      cache: 'no-store'
    });
    const { tailscale } = await res.json();

    document.querySelectorAll(LOGOUT_SELECTOR).forEach(el => {
      if (tailscale) {
        // Tailscale 연결 → 로그아웃 버튼 자리에 뱃지 삽입 후 버튼 숨기기
        if (!el.nextElementSibling || !el.nextElementSibling.dataset.tsBadge) {
          el.insertAdjacentHTML('afterend', tsBadgeHTML(el));
        }
        el.style.display = 'none';
      } else {
        // Tailscale 미연결 → 로그아웃 버튼 유지하되 정방형 아이콘 스타일
        normalizeLogoutEl(el);
        el.style.display = '';
        const badge = el.nextElementSibling;
        if (badge && badge.dataset && badge.dataset.tsBadge) badge.remove();
      }
    });
  } catch {
    // 연결 실패 → 로그아웃 버튼 그대로 유지 (정방형 아이콘 적용)
    document.querySelectorAll(LOGOUT_SELECTOR).forEach(el => normalizeLogoutEl(el));
  }
})();
