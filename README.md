# FSQ Swarm Map

Foursquare Swarm 체크인 데이터를 지도에 시각화하고 관리하는 웹 애플리케이션입니다.

## 주요 기능
- **인터랙티브 지도**: Leaflet.js 및 MarkerCluster를 이용한 데이터 시각화.
- **데이터 분석 리포트**: 방문 추이, 시간대 분포, 지역별/카테고리별 통계 대시보드.
- **체크인 관리 페이지 (`/manage`)**:
    - **수동 추가**: 지도 클릭 또는 검색을 통한 새로운 체크인 등록.
    - **실시간 검색**: DB 내 장소명 자동완성 및 전체 기록 검색.
    - **수정 및 삭제**: 기존 체크인 정보(장소, 시간, 좌표 등)의 인라인 수정 및 삭제.
- **외부 서비스 동기화**:
    - **Foursquare Swarm**: 체크인 삭제 및 Shout(코멘트) 수정 반영 (24시간 이내).
    - **Google Calendar**: OAuth2 기반의 일정 자동 추가, 수정, 삭제 동기화.
- **모바일 최적화**: 모바일 기기를 위한 전용 UI 및 슬라이딩 리스트, FAB 버튼 지원.

## 기술 스택
- **Backend**: Python 3.10, Flask
- **Frontend**: Vanilla JS, Leaflet.js, Moment.js, Chart.js
- **Database**: MariaDB
- **Infrastructure**: Docker, Docker Compose

## 설치 및 실행 방법

### 1. 환경 설정
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력합니다.

```env
# Database
DB_HOST=mariadb
DB_USER=your_user
DB_PASSWORD=your_password
DB_DATABASE=swarm
DB_PORT=3306

# API Keys
SWARM_API_KEY=your_swarm_token
```
*구글 캘린더 인증 정보는 DB의 `FSQ_GCalAuth` 테이블을 참조합니다.*

### 2. 컨테이너 실행
```bash
docker-compose up -d --build
```

### 3. 접속
- 메인 지도: `http://localhost:5005`
- 관리 페이지: `http://localhost:5005/manage`

## 프로젝트 구조
- `app.py`: Flask 백엔드 API 및 외부 서비스(Swarm, GCal) 동기화 로직.
- `templates/index.html`: 메인 지도 및 리포트 인터페이스.
- `templates/manage.html`: 체크인 관리 전용 페이지.
- `Dockerfile` / `docker-compose.yml`: 도커 배포 설정.
- `requirements.txt`: 필요한 Python 라이브러리 목록.
