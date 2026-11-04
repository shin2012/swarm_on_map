# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
한 사람(요섭)의 개인 도구. 2010년부터 쌓인 Foursquare Swarm 체크인 약 1만 건을 본인이 본다. iPhone(홈 화면 PWA), iPad Safari, PC 브라우저를 골고루 쓴다. 주된 일은 **지도로 예전 방문을 돌아보는 것**이고, 기록 고치기·추가, 통계, 이동 경로 재생은 가끔 쓴다.

## Product Purpose
누적 체크인을 지도 위에 펼쳐 "언제 어디에 있었는지"를 다시 찾아보게 한다. 기간을 좁히고, 장소를 검색하고, 시간 순서대로 이동을 재생해 본다. 고친 기록은 DB → 구글 캘린더로 동기화된다(Lambda).

## Positioning
남의 지도 서비스에는 없는 본인만의 15년치 방문 기록이 데이터 그 자체. 장소 이름·카테고리·방문 시각·메모(SHOUT)·사진이 실제 콘텐츠다.

## Operating Context
- 화면: PC 메인(`/`: 지도 + 왼쪽 목록 + 기간 슬라이더·재생 + 통계 모달), 관리(`/manage`: 추가 폼 + 기록 표 + 위치 선택 지도), 모바일(`/m/`: 지도·기록·추가·통계 4탭 하단 내비, 위치 선택 오버레이). 모바일 기기로 `/`·`/manage` 접속 시 `/m/`로 보냄.
- 지도: Leaflet + markercluster + heat. 국내는 네이버 지도를 바탕으로 깔고(static/naver-base.js), 해외·실패 시 CARTO 타일.
- tinyauth SSO 뒤에 있음(로그아웃 버튼 존재).

## Capabilities and Constraints
- 기능은 유지: 기간 필터(슬라이더/1주·1개월·3개월·1년·전체), 검색, 히트맵 토글, 내 위치, 경로 재생(속도 선택·정지), 통계(방문 추이·시간대·카테고리 등), 체크인 추가·수정·삭제, 장소 후보 선택(venue-pick.js), CarPlay API 등.
- 설정 페이지는 만들지 않는다(사용자 결정).
- iOS Safari 터치 호환 필수, iPhone PWA standalone.
- UI에 한자 금지, 한국어만.

## Brand Commitments
- 이름: Swarm Insights (현재 표기).
- 사용자 취향: 카드 박스 + 색 배지 + 이모지 + KPI 박스 나열 같은 "AI 디자인 느낌" 거부. 밀도 높은 정보는 카드 그리드보다 리스트/표. 둥근 모서리 작게.

## Evidence on Hand
실제 DB 데이터(/api/data, 약 10,237건). 사진 URL 일부 존재. 가짜 데이터 만들 필요 없음.

## Product Principles
1. 지도가 주인공 — 돌아보기가 첫 화면의 일이다.
2. 기록은 시간 순서의 이야기 — 날짜·시각이 장소만큼 중요하다.
3. 세 기기 모두 1급 — 터치·좁은 화면에서도 같은 일이 된다.
4. 꾸밈보다 정보 밀도와 읽기 쉬움.
