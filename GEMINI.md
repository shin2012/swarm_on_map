# GEMINI.md - FSQ Swarm Map Project Context

이 파일은 Foursquare Swarm 체크인 데이터를 지도에 시각화하는 `fsq_map` 프로젝트의 핵심 정보와 아키텍처를 정리하여, Gemini가 프로젝트의 컨텍스트를 유지하고 향후 개선 작업을 돕기 위해 작성되었습니다.

## 1. 프로젝트 개요
- **목적**: MariaDB의 `FSQ_Swarm` 테이블에 저장된 체크인 데이터를 가져와 웹 브라우저의 지도 위에 마커로 표시.
- **주요 기능**:
  - MariaDB 도커 컨테이너 연동 및 데이터 조회.
  - Leaflet.js를 이용한 인터랙티브 지도 구현.
  - MarkerCluster를 통한 대량의 데이터(9,000+건) 효율적 시각화.
  - **모바일 대응**: 모바일 환경을 위한 슬라이딩 방문 리스트 토글 및 UI 최적화.
  - 마커 클릭 시 장소명, 카테고리, 시간, 사진, 코멘트(Shout) 팝업 표시.
  - 방문 통계 분석 대시보드 (Chart.js 기반).
  - **체크인 관리**: 수동 체크인 추가, 기존 데이터 수정 및 삭제 기능.
  - **동기화**: 추가/수정/삭제 시 Swarm 서비스 및 구글 캘린더와 연동.

## 2. 기술 스택
- **Backend**: Python 3.10, Flask
- **Frontend**: HTML5, Vanilla JS, Leaflet.js, Leaflet.markercluster (CDN 사용)
- **Database**: MariaDB (외부 컨테이너 `mariadb`와 `oci_bridge` 네트워크로 연결)
- **Deployment**: Docker, Docker Compose

## 3. 핵심 아키텍처 및 로직
- **데이터 흐름**: 
  1. 사용자가 접속하면 `index.html` 로드.
  2. 프론트엔드에서 `/api/data` 호출.
  3. 백엔드에서 MariaDB에 접속하여 `LAT`, `LNG`가 있는 유효한 체크인 데이터를 가져와 JSON으로 반환.
  4. Leaflet이 데이터를 받아 클러스터링 후 지도에 렌더링.
- **체크인 관리 로직**:
  - 장소명 및 카테고리 자동완성 지원 (기존 방문 데이터 기반).
  - 드래그 가능한 지도 팝업을 통한 위치(좌표/주소) 선택 기능.
  - 주소 자동 포맷팅 (`[우편번호] [국가] [도시] [나머지주소]`).
  - 방문 시간 초기값 설정 및 세련된 UI 적용.
- **네트워크 설정**: `docker-compose.yml`에서 `external: true`인 `oci_bridge` 네트워크를 사용하여 기존 MariaDB 컨테이너와 통신합니다.

## 4. 주요 파일 구조
- `app.py`: Flask 메인 애플리케이션 및 API 엔드포인트.
- `templates/index.html`: Leaflet 지도 로직 및 UI.
- `templates/manage.html`: 체크인 관리 인터페이스 (CRUD).
- `Dockerfile`: 컨테이너 빌드 설정.
- `docker-compose.yml`: 컨테이너 실행 및 환경 변수(DB 접속 정보) 설정.
- `requirements.txt`: Python 라이브러리 의존성.

## 5. 데이터베이스 스키마 (참고)
```sql
CREATE TABLE `FSQ_Swarm` (
  `FSQ_UNIXTIME` int(10) NOT NULL,
  `FSQ_ID` varchar(24) NOT NULL,
  `FSQ_TIMEZONEOFFSET` int(4) NOT NULL,
  `FSQ_VENUEID` varchar(24) NOT NULL,
  `FSQ_ISMAYER` varchar(1) NOT NULL,
  `FSQ_ISPRIVATE` varchar(1) NOT NULL,
  `VENUE` varchar(255) NOT NULL,
  `VENUE_SUB` varchar(255) DEFAULT NULL,
  `CATEGORY` varchar(255) DEFAULT NULL,
  `LAT` varchar(12) NOT NULL,
  `LNG` varchar(12) NOT NULL,
  `ADDRESS` varchar(255) DEFAULT NULL,
  `COUNTRY` varchar(255) DEFAULT NULL,
  `COUNTRYCODE` varchar(255) DEFAULT NULL,
  `TIME_UTC` varchar(32) NOT NULL,
  `TIME_KST` varchar(32) NOT NULL,
  `TIME_LOCAL` varchar(32) NOT NULL,
  `PHOTO` varchar(255) DEFAULT NULL,
  `SHOUT` varchar(1024) DEFAULT NULL,
  `CALENDAR_SENT` varchar(1) NOT NULL,
  `GCal_EventID` varchar(26) DEFAULT NULL,
  `MODIFIED` timestamp NULL DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`FSQ_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 6. 개발 및 운영 지침
- **환경 설정**: `.env` 파일에 데이터베이스 접속 정보를 저장합니다.
- **실행**: `docker-compose up -d --build`
- **로그 확인**: `docker logs -f fsq_map`
- **주의사항**:
  - `.env` 파일은 절대 Git에 커밋하지 마세요 (보안).
  - `DB_HOST` 환경 변수는 도커 네트워크 내의 MariaDB 컨테이너 이름(`mariadb`)과 일치해야 합니다.

## 7. 주요 API 엔드포인트
- `/api/data`: 지도 표시용 전체 데이터 조회.
- `/api/manage/list`: 관리 페이지용 페이징 리스트 조회.
- `/api/manage/venues`: 장소명 자동완성 검색.
- `/api/manage/categories`: 카테고리 자동완성 검색.
- `/api/manage/add`: 새 체크인 추가.
- `/api/manage/update/<fsq_id>`: 기존 체크인 수정.
- `/api/manage/delete/<fsq_id>`: 체크인 삭제.
