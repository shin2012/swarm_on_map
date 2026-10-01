# Swarm on Map 🗺️

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-2.3+-green?style=flat-square&logo=flask)
![MariaDB](https://img.shields.io/badge/MariaDB-10.5+-orange?style=flat-square&logo=mariadb)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=flat-square&logo=docker)
![License](https://img.shields.io/badge/License-Personal%20Project-lightgrey?style=flat-square)

Foursquare Swarm 체크인 데이터를 **인터랙티브 웹 지도**에 시각화하는 프로젝트입니다.  
누적된 방문 기록을 지도에 마커로 표시하고, 통계 분석 및 관리 기능을 제공합니다.

---

## 🎯 핵심 기능

### 📍 지도 시각화
- **Leaflet.js** 기반 인터랙티브 지도
- **MarkerCluster**를 활용한 대량 데이터 효율화 (9,000+건)
- 마커 클릭 시 장소명, 카테고리, 시간, 사진, 코멘트 팝업 표시
- 타임캡슐 스크러버로 시간축 탐색

### 📊 통계 분석 대시보드
- **Chart.js** 기반 방문 통계
- 기간별 분석 (전체, 1개월, 3개월, 6개월)
- 도시, 카테고리, 시간대별 차트
- 히트맵 시각화

### 🔄 자동화 기능
- **Nominatim 역지오코딩**: 위/경도 기반 도시명 자동 추출
- **Timezone 자동화**: 좌표 기반 타임존 오프셋 자동 계산
- **Google Calendar 연동**: 체크인 추가/수정/삭제 시 자동 동기화
- **Swarm API 연동**: 데이터 변경 사항 실시간 동기화

### ✏️ 체크인 관리 (CRUD)
- **새 체크인 추가**: 지도에서 위치 선택 + 자동 완성
- **기존 데이터 수정**: 장소, 시간, 내용 편집
- **체크인 삭제**: 관련 Google Calendar 이벤트 함께 삭제
- **페이징 리스트**: 장소명/주소 검색 및 필터링

### 📱 반응형 디자인
- **데스크톱**: 사이드바 + 지도 레이아웃
- **모바일**: 하단 슬라이딩 패널 + FAB 메뉴
- Dark/Light 모드 자동 감지

---

## 🛠️ 기술 스택

| 계층 | 기술 |
|------|------|
| **Backend** | Python 3.10, Flask 2.3+ |
| **Frontend** | HTML5, Vanilla JS, Leaflet.js 1.9.4 |
| **Database** | MariaDB 10.5+ (외부 컨테이너) |
| **APIs** | Google Calendar v3, Foursquare Swarm, Nominatim |
| **Deploy** | Docker, Docker Compose |

### 주요 Python 라이브러리
```
flask                           # 웹 프레임워크
mysql-connector-python          # MariaDB 연결
python-dateutil                 # 날짜/시간 파싱
google-auth-oauthlib            # Google Calendar OAuth
timezonefinder                  # 좌표 기반 타임존 조회
pytz                            # 타임존 처리
requests                        # HTTP 요청
python-dotenv                   # 환경변수 관리
```

### Frontend 라이브러리 (CDN)
- **Leaflet.js** (1.9.4): 인터랙티브 지도
- **Leaflet MarkerCluster** (1.5.3): 마커 클러스터링
- **Chart.js** (4.4.1): 통계 차트
- **Leaflet.Heat**: 히트맵 시각화
- **noUiSlider** (15.7.1): 시간축 스크러버
- **Flatpickr**: 날짜/시간 선택기
- **Moment.js** (2.29.4): 시간대 포맷팅
- **Font Awesome 6.5.1**: 아이콘
- **Pretendard Variable**: 한글 폰트

---

## 📂 프로젝트 구조

<details open>
<summary><b>디렉토리 레이아웃</b></summary>

```
swarm_on_map/
├── app.py                          # Flask 메인 애플리케이션
├── requirements.txt                # Python 의존성
├── Dockerfile                      # 컨테이너 빌드 설정
├── docker-compose.yml              # 컨테이너 오케스트레이션
├── GEMINI.md                       # 프로젝트 컨텍스트 문서
├── README.md                       # 이 문서
├── .gitignore                      # Git 무시 파일
├── .git/                           # Git 저장소
└── templates/
    ├── index.html                  # 지도 메인 페이지 (637줄)
    └── manage.html                 # 체크인 관리 페이지 (613줄)
```

</details>

---

## 🚀 설치 및 실행

### 전제 조건
- **Docker & Docker Compose** 설치
- **MariaDB** 컨테이너 (외부, `oci_bridge` 네트워크)
- **환경변수** (.env 파일)

### 1️⃣ 저장소 클론

```bash
git clone https://github.com/shin2012/swarm_on_map.git
cd swarm_on_map
```

### 2️⃣ 환경변수 설정

`.env` 파일 생성:

```env
# MariaDB 연결 정보
DB_HOST=mariadb
DB_USER=your_username
DB_PASSWORD=your_password
DB_DATABASE=swarm
DB_PORT=3306

# Foursquare Swarm API
SWARM_API_KEY=your_swarm_api_key

# Google Calendar
# (DB의 FSQ_GCalAuth 테이블에 token.json 저장)
```

### 3️⃣ 도커 컨테이너 실행

```bash
# 빌드 및 실행
docker-compose up -d --build

# 로그 확인
docker-compose logs -f fsq_map

# 종료
docker-compose down
```

### 4️⃣ 웹 접속

```
http://localhost:5005
```

---

## 📖 사용 가이드

### 🗺️ 지도 페이지 (`/`)

<details>
<summary><b>주요 상호작용</b></summary>

| 동작 | 설명 |
|------|------|
| **마커 클릭** | 장소 정보 팝업 표시 (사진, 코멘트 포함) |
| **클러스터 클릭** | 해당 지역 확대 |
| **시간축 스크러버** | 특정 시점의 체크인 필터링 |
| **사이드바 장소 클릭** | 해당 마커로 지도 이동 |
| **리포트 버튼** | 통계 대시보드 열기 |
| **관리 버튼** | 체크인 관리 페이지 이동 |

</details>

### ✏️ 체크인 관리 페이지 (`/manage`)

<details>
<summary><b>체크인 추가</b></summary>

1. **"새 체크인 추가"** 폼 작성:
   - 🏠 **장소명**: 기존 방문 데이터에서 자동완성
   - 📍 **지점**: 지점 입력 (예: `1번점`)
   - 🏷️ **카테고리**: 자동완성으로 선택
   - 📍 **주소**: 지도 버튼 클릭 → 위치 선택
   - ⏰ **방문시간**: Flatpickr 날짜선택기 이용
   - 💬 **내용**: 방문 코멘트 입력

2. **"등록"** 버튼 클릭
   - ✅ 자동 타임존 계산
   - ✅ Google Calendar 이벤트 생성
   - ✅ 데이터베이스 저장

</details>

<details>
<summary><b>체크인 수정 및 삭제</b></summary>

| 동작 | 절차 |
|------|------|
| **수정** | 리스트에서 **수정** 버튼 → 필드 편집 → **저장** |
| **삭제** | **삭제** 버튼 클릭 → Google Calendar 이벤트 동시 삭제 |

</details>

---

## 🔌 API 엔드포인트

<details open>
<summary><b>REST API 목록</b></summary>

### 데이터 조회
| 메서드 | 엔드포인트 | 설명 | 쿼리 파라미터 |
|--------|----------|------|--|
| `GET` | `/api/data` | 지도 표시용 전체 체크인 데이터 | - |
| `GET` | `/api/manage/list` | 관리 페이지용 페이징 리스트 | `page`, `limit`, `q` |
| `GET` | `/api/manage/venues` | 장소명 자동완성 검색 | `q` |
| `GET` | `/api/manage/categories` | 카테고리 자동완성 검색 | `q` |

### 데이터 조작
| 메서드 | 엔드포인트 | 설명 | 요청 본문 |
|--------|----------|------|--|
| `POST` | `/api/manage/add` | 새 체크인 추가 | JSON (venue, lat, lng, ...) |
| `PUT` | `/api/manage/update/<fsq_id>` | 기존 체크인 수정 | JSON (venue, lat, lng, ...) |
| `DELETE` | `/api/manage/delete/<fsq_id>` | 체크인 삭제 | `gcal_id` 쿼리 파라미터 |

### 요청 예시

```bash
# 페이징 리스트 조회 (20개씩, 1페이지)
GET /api/manage/list?page=1&limit=20&q=카페

# 장소명 자동완성
GET /api/manage/venues?q=스타벅스

# 카테고리 자동완성
GET /api/manage/categories?q=카페

# 새 체크인 추가
POST /api/manage/add
Content-Type: application/json
{
  "venue_only": "스타벅스",
  "venue_sub": "강남점",
  "category": "카페",
  "lat": "37.497",
  "lng": "127.027",
  "address": "서울 강남구 테헤란로",
  "time_local": "2024-01-15 14:30:00",
  "shout": "아메리카노 한잔"
}
```

</details>

---

## 🗄️ 데이터베이스 스키마

<details>
<summary><b>FSQ_Swarm 테이블 구조</b></summary>

```sql
CREATE TABLE `FSQ_Swarm` (
  `FSQ_ID` varchar(24) PRIMARY KEY,           -- Swarm 체크인 ID (또는 ManuallySaved_unixtime)
  `FSQ_UNIXTIME` int(10) NOT NULL,            -- Unix 타임스탬프
  `FSQ_TIMEZONEOFFSET` int(4) NOT NULL,       -- 타임존 오프셋 (분)
  `FSQ_VENUEID` varchar(24),                  -- Swarm 장소 ID
  `FSQ_ISMAYER` varchar(1),                   -- Mayor 여부
  `FSQ_ISPRIVATE` varchar(1),                 -- 비공개 여부
  
  `VENUE` varchar(255) NOT NULL,              -- 장소명
  `VENUE_SUB` varchar(255),                   -- 지점 (예: "1번점")
  `CATEGORY` varchar(255),                    -- 카테고리
  
  `LAT` varchar(12) NOT NULL,                 -- 위도
  `LNG` varchar(12) NOT NULL,                 -- 경도
  `ADDRESS` varchar(255),                     -- 주소
  `COUNTRY` varchar(255),                     -- 국가
  `COUNTRYCODE` varchar(255),                 -- 국가 코드
  `CITY` varchar(255),                        -- 도시 (자동 계산)
  
  `TIME_UTC` varchar(32) NOT NULL,            -- UTC 시간
  `TIME_KST` varchar(32) NOT NULL,            -- KST(한국) 시간
  `TIME_LOCAL` varchar(32) NOT NULL,          -- 지역 시간
  
  `PHOTO` varchar(255),                       -- 사진 URL
  `SHOUT` varchar(1024),                      -- 체크인 코멘트
  
  `CALENDAR_SENT` varchar(1),                 -- Calendar 동기화 여부
  `GCal_EventID` varchar(26),                 -- Google Calendar 이벤트 ID
  `MODIFIED` timestamp,                       -- 마지막 수정 시간
  
  KEY `idx_unixtime` (`FSQ_UNIXTIME`),
  KEY `idx_city` (`CITY`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### FSQ_GCalAuth 테이블 (Google Calendar 토큰)

```sql
CREATE TABLE `FSQ_GCalAuth` (
  `id` int(11) PRIMARY KEY AUTO_INCREMENT,
  `type` varchar(50),                         -- "token.json"
  `data` longtext,                            -- OAuth2 토큰 JSON
  `created_at` timestamp DEFAULT CURRENT_TIMESTAMP
);
```

</details>

---

## 🔄 백그라운드 워커

<details>
<summary><b>지오코딩 워커 (Geocode Worker)</b></summary>

서버 시작 시 자동 실행되는 데몬 스레드:

### 동작 방식
1. **CITY 컬럼이 NULL인 데이터** 대상으로 순회
2. **Nominatim API** 호출: `reverse?lat={LAT}&lon={LNG}&format=json`
3. 응답에서 도시명 추출:
   - 우선순위: `city` > `town` > `province` > `county` > `village`
   - 한국의 경우: `시` 또는 `군` 선호
4. **데이터베이스 업데이트**: `UPDATE FSQ_Swarm SET CITY = ? WHERE FSQ_ID = ?`

### 최적화 기능
- **중복 방지**: 같은 좌표의 기존 CITY 데이터 재사용
- **API Rate Limiting**: 3초 + 랜덤 지터 (Nominatim 정책 준수)
- **백오프 전략**: 429/403 에러 시 1시간 대기
- **스킵 세션**: 처리 불가 레코드는 세션 중 스킵, 10분 후 재시도

### 로그 확인
```bash
docker-compose logs -f fsq_map | grep "LOG:"
```

</details>

---

## 🔐 보안 고려사항

<details>
<summary><b>중요 보안 지침</b></summary>

### ⚠️ 필수 주의사항

1. **`.env` 파일 보안**
   ```bash
   # .gitignore에 .env 추가 (이미 포함됨)
   # .env 파일은 절대 Git에 커밋하지 마세요
   ```

2. **API 키 관리**
   - `SWARM_API_KEY` 환경변수로 관리
   - 리포지토리에 절대 노출 금지
   - 정기적 로테이션 권장

3. **Google Calendar OAuth2**
   - 토큰 데이터는 데이터베이스의 `FSQ_GCalAuth` 테이블에 저장
   - 만료된 토큰은 자동으로 리프레시

4. **데이터베이스**
   - MariaDB는 별도 컨테이너에서 운영
   - `oci_bridge` 네트워크로 격리
   - DB 접속 정보는 환경변수로 전달

5. **CORS 및 인증**
   - 현재 공개 API (내부 네트워크 운영 가정)
   - 필요시 OAuth2 또는 JWT 추가

</details>

---

## 🐛 문제 해결

<details>
<summary><b>일반적인 문제 및 해결책</b></summary>

### 컨테이너 시작 실패
```bash
# 문제: "네트워크 oci_bridge가 없음"
# 해결: 기존 MariaDB 네트워크 확인
docker network ls | grep oci_bridge

# 없으면 생성
docker network create oci_bridge
```

### 데이터베이스 연결 오류
```bash
# 문제: "Waiting for DB..."
# 해결: MariaDB 컨테이너 상태 확인
docker ps | grep mariadb

# MariaDB 로그 확인
docker logs mariadb
```

### Nominatim API 호출 실패
```bash
# 문제: "429 Too Many Requests" (Rate Limiting)
# 해결: 워커가 자동으로 1시간 백오프 실행
# 로그에서 확인:
docker-compose logs fsq_map | grep "Backing off"
```

### Google Calendar 동기화 실패
```bash
# 문제: "GCal Auth Error"
# 해결: 데이터베이스의 FSQ_GCalAuth 테이블 확인
# 토큰 만료 시 자동 리프레시됨
```

### 마커가 지도에 표시되지 않음
```bash
# 문제: "LAT/LNG가 비어있음"
# 해결: 다음 SQL로 확인
SELECT COUNT(*) FROM FSQ_Swarm WHERE LAT = '' OR LNG = '';
```

</details>

---

## 📊 성능 최적화

<details>
<summary><b>데이터 처리 팁</b></summary>

### 대량 데이터 처리 (9,000+)
- **MarkerCluster**: 1000개 이상 마커는 자동 클러스터링
- **쿼리 최적화**: 인덱스 활용 (`FSQ_UNIXTIME`, `CITY`)
  ```sql
  CREATE INDEX idx_unixtime ON FSQ_Swarm(FSQ_UNIXTIME);
  CREATE INDEX idx_city ON FSQ_Swarm(CITY);
  ```

### 지오코딩 속도 개선
- **중복 조회 방지**: 같은 좌표 재사용 (이미 구현됨)
- **배치 처리**: 야간 시간대 집중 처리 권장

### 프론트엔드 최적화
- **CDN 사용**: 모든 라이브러리는 안정 버전 CDN 제공
- **Lazy Loading**: 팝업 콘텐츠는 필요 시에만 로드

</details>

---

## 🔗 관련 API 및 서비스

| 서비스 | 용도 | 문서 |
|--------|------|------|
| **Foursquare Swarm** | 체크인 데이터 출처 및 동기화 | [API Docs](https://developer.foursquare.com/docs/places-api/checkins/) |
| **Google Calendar** | 방문 일정 동기화 | [Calendar API](https://developers.google.com/calendar) |
| **OpenStreetMap Nominatim** | 좌표 역지오코딩 (도시명 추출) | [Nominatim](https://nominatim.org/) |
| **TimezoneFinder** | 좌표 기반 타임존 조회 | [PyPI](https://pypi.org/project/timezonefinder/) |

---

## 📝 라이선스

개인 프로젝트 (Personal Project)

---

## 👤 저자

**shin2012** (Yoseop Shin)

- GitHub: [@shin2012](https://github.com/shin2012)
- 프로젝트: Swarm Insights (Foursquare 체크인 시각화)

---

## 📞 문의 및 피드백

- **버그 리포트**: GitHub Issues
- **기능 제안**: GitHub Discussions
- **문제 해결**: 로그 (`docker-compose logs -f fsq_map`) 확인 후 이슈 작성

---

## 🙏 감사의 말

- **Leaflet.js** 커뮤니티
- **Google** (Google Calendar API)
- **OpenStreetMap** (Nominatim)
- **Chart.js** 개발팀

---

## 📌 버전 정보

| 항목 | 버전 |
|------|------|
| **Python** | 3.10+ |
| **Flask** | 2.3+ |
| **MariaDB** | 10.5+ |
| **Node.js** | - (Frontend CDN only) |

**마지막 업데이트**: 2026년 현재
