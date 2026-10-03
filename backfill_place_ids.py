#!/usr/bin/env python3
"""기존 체크인에 KAKAO_PLACE_ID, TMAP_POI_ID 백필.

distinct FSQ_VENUEID 기준으로 한 번만 API 호출하고 같은 venue_id 행 일괄 업데이트.
- Kakao_ venue: venue_id에서 kakao_id 직접 추출
- 한국 venue: 카카오 키워드 검색 + TMAP POI 검색
- 해외 venue: 스킵 (카카오/TMAP 모두 한국만)

사용법:
  python3 backfill_place_ids.py [--dry-run] [--limit N]
"""
import os, sys, time, math, re, json
import requests
import pymysql

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", 3306)),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="swarm", charset="utf8mb4", autocommit=True)

KAKAO_KEY = os.getenv("KAKAO_REST_KEY", "")
TMAP_KEY = os.getenv("TMAP_APP_KEY", "")

def haversine_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(h))

def norm(name):
    n = re.sub(r"\(.*?\)|\[.*?\]", "", name or "").strip()
    parts = n.split()
    if len(parts) > 1 and re.search(r"(점|지점|호점)$", parts[-1]):
        parts = parts[:-1]
    n = "".join(parts)
    n = re.sub(r"[·\-_/.,&']", "", n)
    return n.lower()

def similar(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb or (len(min(na, nb, key=len)) >= 3 and (na in nb or nb in na)):
        return 1.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, na, nb).ratio()

def kakao_search(name, lat, lng):
    """카카오 키워드 검색 → 300m 이내 + 이름 유사 50% → kakao place id."""
    if not KAKAO_KEY:
        return ""
    try:
        r = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json",
                         params={"query": name, "x": lng, "y": lat, "radius": 300, "sort": "distance", "size": 5},
                         headers={"Authorization": f"KakaoAK {KAKAO_KEY}"}, timeout=6)
        if r.status_code != 200:
            return ""
        for doc in r.json().get("documents", []):
            dl, dg = float(doc["y"]), float(doc["x"])
            m = haversine_m((lat, lng), (dl, dg))
            if m <= 300 and similar(doc["place_name"], name) >= 0.5:
                return doc.get("id", "")
    except Exception:
        pass
    return ""

def tmap_search(name, lat, lng):
    """TMAP POI 검색 → 300m 이내 + 이름 유사 50% → tmap poi id."""
    if not TMAP_KEY:
        return ""
    try:
        r = requests.get("https://apis.openapi.sk.com/tmap/pois",
                         params={"version": "1", "appKey": TMAP_KEY, "searchKeyword": name,
                                 "searchtypCd": "R", "radius": "1", "centerLon": str(lng), "centerLat": str(lat),
                                 "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO", "count": "5"},
                         timeout=6)
        if r.status_code != 200:
            return ""
        pois = r.json().get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
        for p in pois:
            try:
                pl, pg = float(p.get("noorLat", 0)), float(p.get("noorLon", 0))
            except (TypeError, ValueError):
                continue
            m = haversine_m((lat, lng), (pl, pg))
            if m <= 300 and similar(p.get("name", ""), name) >= 0.5:
                return p.get("id", "")
    except Exception:
        pass
    return ""

def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    conn = pymysql.connect(**DB)
    cur = conn.cursor(pymysql.cursors.DictCursor)

    # 1) Kakao_ venue → kakao_id 직접 추출
    cur.execute("SELECT DISTINCT FSQ_VENUEID FROM FSQ_Swarm WHERE FSQ_VENUEID LIKE 'Kakao_%' AND KAKAO_PLACE_ID IS NULL")
    kakao_venues = cur.fetchall()
    for row in kakao_venues:
        vid = row["FSQ_VENUEID"]
        kid = vid[len("Kakao_"):]
        if dry_run:
            print(f"[DRY] Kakao_ → kakao_id={kid} for {vid}")
        else:
            cur.execute("UPDATE FSQ_Swarm SET KAKAO_PLACE_ID=%s WHERE FSQ_VENUEID=%s AND KAKAO_PLACE_ID IS NULL", (kid, vid))
    print(f"Kakao_ venue: {len(kakao_venues)}건 처리")

    # 2) 한국 venue: distinct (venue_id, name, lat, lng) → 카카오 + TMAP
    cur.execute("""
        SELECT FSQ_VENUEID, VENUE, VENUE_SUB, LAT, LNG, COUNTRYCODE
        FROM FSQ_Swarm
        WHERE KAKAO_PLACE_ID IS NULL AND TMAP_POI_ID IS NULL
          AND COUNTRYCODE = 'KR'
          AND LAT != '' AND LNG != ''
        GROUP BY FSQ_VENUEID
        ORDER BY COUNT(*) DESC
    """)
    venues = cur.fetchall()
    if limit:
        venues = venues[:limit]

    total = len(venues)
    matched_kakao = 0
    matched_tmap = 0
    print(f"한국 venue {total}건 매칭 시작 {'(dry-run)' if dry_run else ''}")

    for i, v in enumerate(venues):
        vid = v["FSQ_VENUEID"]
        name = v["VENUE"] + (" " + v["VENUE_SUB"] if v["VENUE_SUB"] else "")
        try:
            lat, lng = float(v["LAT"]), float(v["LNG"])
        except (TypeError, ValueError):
            continue

        # 카카오
        kid = kakao_search(name, lat, lng)
        # TMAP
        tid = tmap_search(name, lat, lng)

        if kid or tid:
            if not dry_run:
                sets, vals = [], []
                if kid:
                    sets.append("KAKAO_PLACE_ID=%s")
                    vals.append(kid[:20])
                if tid:
                    sets.append("TMAP_POI_ID=%s")
                    vals.append(tid[:20])
                vals.append(vid)
                cur.execute(f"UPDATE FSQ_Swarm SET {', '.join(sets)} WHERE FSQ_VENUEID=%s AND KAKAO_PLACE_ID IS NULL AND TMAP_POI_ID IS NULL", vals)

            if kid:
                matched_kakao += 1
            if tid:
                matched_tmap += 1

        if (i + 1) % 100 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] 카카오={matched_kakao} 티맵={matched_tmap} (현재: {name[:20]})")

        # Rate limit: 카카오는 넉넉, TMAP POI 20,000/일
        time.sleep(0.15)

    print(f"\n완료: 카카오 {matched_kakao}/{total} 매칭, 티맵 {matched_tmap}/{total} 매칭")

    # 최종 통계
    cur.execute("SELECT COUNT(*) c FROM FSQ_Swarm WHERE KAKAO_PLACE_ID IS NOT NULL")
    print(f"KAKAO_PLACE_ID 있는 행: {cur.fetchone()['c']}")
    cur.execute("SELECT COUNT(*) c FROM FSQ_Swarm WHERE TMAP_POI_ID IS NOT NULL")
    print(f"TMAP_POI_ID 있는 행: {cur.fetchone()['c']}")

    conn.close()

if __name__ == "__main__":
    main()
