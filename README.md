# FSQ Swarm Map

Foursquare Swarm 체크인 데이터를 지도에 시각화하는 웹 애플리케이션입니다.

## 주요 기능
- MariaDB 데이터베이스에서 체크인 데이터 조회
- Leaflet.js 및 MarkerCluster를 이용한 인터랙티브 지도 시각화
- **모바일 최적화**: 모바일 기기를 위한 슬라이딩 방문 리스트 토글 기능
- 장소명, 카테고리, 시간, 사진 및 코멘트가 포함된 팝업 표시
- 데이터 분석 리포트 대시보드 (방문 추이, 시간대, 카테고리 등)

## 기술 스택
- **Backend**: Python 3.10, Flask
- **Frontend**: Vanilla JS, Leaflet.js, Leaflet.markercluster
- **Database**: MariaDB
- **Infrastructure**: Docker, Docker Compose

## 설치 및 실행 방법

### 1. 환경 설정
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력합니다.

```env
DB_HOST=your_db_host
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_DATABASE=your_db_name
DB_PORT=3306
```

### 2. 컨테이너 실행
```bash
docker-compose up -d --build
```

### 3. 접속
브라우저에서 `http://localhost:5005`에 접속합니다.

## 프로젝트 구조
- `app.py`: Flask 백엔드 API
- `templates/index.html`: 프론트엔드 지도 인터페이스
- `Dockerfile` / `docker-compose.yml`: 도커 배포 설정
- `.env`: 데이터베이스 연결 설정 (비공개)
