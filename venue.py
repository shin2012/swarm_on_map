"""체크인 장소 정하기 — daily-yoseop(app/checkins.py)과 같은 규칙.

후보: 내 체크인 · 포스퀘어(Swarm 과 같은 venue_id) · 카카오(한국만) · 주소.
  같은 가게면 포스퀘어(또는 포스퀘어 ID 가 있는 내 체크인) 줄에 카카오를 합침.
저장 값 (resolve):
  한국  — 포스퀘어 장소면 이름·지점·분류·좌표·도시는 포스퀘어 그대로, 주소만 규칙에 맞춤.
          포스퀘어에 없고 카카오에 있으면 FSQ_VENUEID=Kakao_<카카오 장소번호>, 카카오 값.
          둘 다 없으면 직접 입력 (저장할 때 Manual_Venue__<유닉스초>).
  해외  — 카카오 안 씀. 포스퀘어 값·주소 그대로, 부실하거나 직접 입력이면 OpenStreetMap.
주소 형식 (한국): '{우편번호} 대한민국 {시·도} {시·군·구 …} {도로명 번호} {건물명} {상세}'.
  원래 주소에 도로명이 있으면 카카오 주소 검색으로 우편번호·건물명 보완(1km 안만), 없으면 좌표 역지오코딩.
  도시: 서울·광역시는 '서울특별시', 도 지역은 시·군('여주시').

환경변수: KAKAO_REST_KEY (카카오 로컬 REST 키), SWARM_API_KEY (포스퀘어 v2 OAuth 토큰).
"""
import math
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache

import requests

MANUAL_VENUE = "Manual_Venue__"
KAKAO_VENUE = "Kakao_"
_get_conn = None


def init(get_conn):
    """app.py 의 DB 연결 함수 (mysql.connector)."""
    global _get_conn
    _get_conn = get_conn


def _q(sql, args=()):
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, args)
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


# ─────────────────────────── 외부 API ───────────────────────────

def _kakao(path, params):
    key = os.getenv("KAKAO_REST_KEY", "")
    if not key:
        raise RuntimeError("KAKAO_REST_KEY 없음")
    r = requests.get(f"https://dapi.kakao.com{path}", params=params, headers={"Authorization": f"KakaoAK {key}"}, timeout=6)
    r.raise_for_status()
    return r.json()


def _fsq(params):
    tok = os.getenv("SWARM_API_KEY") or os.getenv("FSQ_OAUTH_TOKEN")
    if not tok:
        return []
    try:
        r = requests.get("https://api.foursquare.com/v2/venues/search",
                         params={**params, "oauth_token": tok, "v": "20240101", "locale": "ko"}, timeout=6)
        return r.json().get("response", {}).get("venues", [])
    except Exception:
        return []


@lru_cache(maxsize=256)
def _osm_r(lat, lng):
    r = requests.get("https://nominatim.openstreetmap.org/reverse",
                     params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1, "accept-language": "ko"},
                     headers={"User-Agent": "FoursquareSwarmMapInsights/1.1 (contact: shin2012)"}, timeout=8)
    r.raise_for_status()
    return r.json()


# ─────────────────────────── 이름 비교 ───────────────────────────

def _norm(name):
    n = re.sub(r"\(.*?\)|\[.*?\]", "", name or "").strip()
    parts = n.split()
    if len(parts) > 1 and re.search(r"(점|지점|호점)$", parts[-1]):
        parts = parts[:-1]
    n = "".join(parts)
    n = re.sub(r"[·\-_/.,&']", "", n)
    n = re.sub(r"(본점|직영점)$", "", n)
    return n.lower()


def _similar(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb or (len(min(na, nb, key=len)) >= 3 and (na in nb or nb in na)):
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _branch(s):
    """'씨유 여주번도리점' → '여주번도리'. 띄어 쓴 마지막 낱말이 '…점'일 때만."""
    parts = (s or "").split()
    if len(parts) < 2:
        return ""
    m = re.fullmatch(r"([가-힣A-Za-z0-9]{2,})점", parts[-1])
    return m.group(1) if m else ""


def _same_shop(cand, q):
    """이름이 비슷하고, q 에 지점명이 있으면 후보 지점명도 같아야 함 (체인점 다른 지점 배제)."""
    if _similar(cand, q) < 0.7:
        return False
    bq = _branch(q)
    return not bq or bq.replace("역", "") in (cand or "").replace(" ", "").replace("역", "")


def _split_branch(name, sub):
    """'파리바게뜨 광흥창역점' → ('파리바게뜨', '광흥창역점')."""
    if sub:
        return name, sub
    m = re.match(r"^(.+?)\s+(\S{2,}점)$", name or "")
    return (m.group(1), m.group(2)) if m else (name, sub)


def _kakao_cat(category_name, place):
    """'음식점 > 간식 > 제과,베이커리 > 파리바게뜨' → '제과,베이커리' (끝이 상표면 한 단계 위)."""
    cat = [x for x in (category_name or "").split(" > ") if x]
    if len(cat) > 1:
        last, prev = cat[-1], cat[-2]
        if _similar(last, place) >= 0.6 or prev.split(",")[0] in last or last in (place or ""):
            cat = cat[:-1]
    return cat[-1] if cat else ""


# ─────────────────────────── 한국 / 해외 ───────────────────────────

@lru_cache(maxsize=512)
def _in_korea_r(lat, lng):
    if not (33.0 <= lat <= 38.7 and 124.5 <= lng <= 131.0):
        return False
    try:   # 대마도·바다처럼 상자 안이지만 한국 땅이 아닌 곳은 시·도가 비어 있음
        j = _kakao("/v2/local/geo/coord2regioncode.json", {"x": lng, "y": lat})
        return any(d.get("region_1depth_name") for d in j.get("documents") or [])
    except Exception:
        return True


def in_korea(lat, lng):
    try:
        return _in_korea_r(round(float(lat), 3), round(float(lng), 3))
    except (TypeError, ValueError):
        return True


def osm_addr(lat, lng):
    """해외 좌표 → '{우편번호} {국가} {주} {시} {구역} {번호 도로} {이름}' + 도시·국가·국가코드."""
    try:
        d = _osm_r(round(float(lat), 6), round(float(lng), 6))
    except Exception:
        return {"address": "", "city": "", "country": "", "cc": ""}
    a = d.get("address") or {}
    city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county") or ""
    area = a.get("city_district") or a.get("suburb") or a.get("quarter") or ""
    road = " ".join(x for x in (a.get("house_number"), a.get("road")) if x) if a.get("road") else ""
    name = d.get("name") or ""
    out, seen = [], set()
    for p in [a.get("postcode") or "", a.get("country") or "", a.get("state") or "", city, area, road,
              name if name and name not in (road, area, city) else ""]:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return {"address": " ".join(out), "city": city, "country": a.get("country") or "", "cc": (a.get("country_code") or "").upper()}


# ─────────────────────────── 한국 주소 (카카오) ───────────────────────────

_CITY = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시",
         "대전": "대전광역시", "울산": "울산광역시", "세종특별자치시": "세종특별자치시", "세종": "세종특별자치시",
         "경기": "경기도", "강원": "강원특별자치도", "강원특별자치도": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
         "전북": "전북특별자치도", "전북특별자치도": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
         "제주특별자치도": "제주특별자치도", "제주": "제주특별자치도"}
_ROAD = r"(\S+(?:로|길)(?:\d+(?:번?길))?)\s*(\d+(?:-\d+)?)"


def _kakao_doc_addr(ra, aa, detail=""):
    r1 = ra.get("region_1depth_name") or aa.get("region_1depth_name") or ""
    sido = _CITY.get(r1, r1)
    body = ra.get("address_name") or aa.get("address_name") or ""
    for pre in (sido, r1):
        if pre and body.startswith(pre + " "):
            body = body[len(pre) + 1:]
            break
    bld = (ra.get("building_name") or "").strip()
    extra = " ".join(w for w in (detail or "").split() if w not in bld)
    tail = " ".join(x for x in (bld, extra) if x)
    city = sido
    if sido.endswith("도"):
        r2 = (ra.get("region_2depth_name") or aa.get("region_2depth_name") or "").split()
        city = r2[0] if r2 else sido
    return {"address": " ".join(x for x in [ra.get("zone_no") or "", "대한민국", sido, body, tail] if x), "city": city}


def kakao_addr(lat, lng):
    """좌표 → 한국 주소 형식 + 도시 (카카오 역지오코딩, 도로명 없으면 지번)."""
    try:
        d = (_kakao("/v2/local/geo/coord2address.json", {"x": lng, "y": lat}).get("documents") or [{}])[0]
    except Exception:
        return {"address": "", "city": ""}
    return _kakao_doc_addr(d.get("road_address") or {}, d.get("address") or {})


def norm_addr(raw, lat, lng):
    """한국 주소를 한 형식으로: 도로명이 있으면 그 주소를 카카오에서 찾아 보완, 없거나 못 찾으면 좌표로."""
    q = re.sub(r"\([^)]*\)", " ", raw or "")
    q = re.sub(r"\b\d{5}\b|\b\d{3}-\d{3}\b|대한민국", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    m = re.search(_ROAD, q)
    if m:
        try:
            j = _kakao("/v2/local/search/address.json", {"query": q[:m.end()], "size": 3})
            for d in j.get("documents") or []:
                ra = d.get("road_address") or {}
                if ra and haversine_km((float(lat), float(lng)), (float(d["y"]), float(d["x"]))) <= 1.0:
                    return _kakao_doc_addr(ra, d.get("address") or {}, q[m.end():].strip())
        except Exception:
            pass
    return kakao_addr(lat, lng)


def _road_key(addr):
    m = re.search(_ROAD, re.sub(r"\([^)]*\)", " ", addr or ""))
    return (m.group(1) + m.group(2)).replace(" ", "") if m else ""


def place_address(lat, lng):
    """지도에서 고른 좌표 → 주소·도시·국가·국가코드 (한국 카카오, 해외 OpenStreetMap)."""
    if in_korea(lat, lng):
        a = kakao_addr(lat, lng)
        return {**a, "country": "대한민국", "cc": "KR"}
    return osm_addr(lat, lng)


# ─────────────────────────── 후보 ───────────────────────────

def _fsq_venue(v, lat, lng):
    loc = v.get("location") or {}
    cats = v.get("categories") or []
    fa = loc.get("formattedAddress") or []
    addr = " ".join(x for x in [loc.get("postalCode", ""), loc.get("country", ""), loc.get("city", ""), fa[0] if fa else ""] if x).strip()
    vl, vg = float(loc.get("lat") or lat), float(loc.get("lng") or lng)
    return {"name": v.get("name") or "", "sub": loc.get("crossStreet", "") or "", "category": cats[0]["name"] if cats else "",
            "lat": vl, "lng": vg, "address": addr, "city": loc.get("city") or loc.get("state") or "",
            "country": loc.get("country") or "", "cc": loc.get("cc") or "", "venue_id": v.get("id") or "",
            "m": round(haversine_km((lat, lng), (vl, vg)) * 1000), "from": "fsq"}


def _kakao_place(p, lat, lng, why="카카오"):
    pl, pg = float(p["y"]), float(p["x"])
    return {"name": p["place_name"], "sub": "", "category": _kakao_cat(p.get("category_name"), p["place_name"]),
            "kakao_id": p.get("id") or "", "lat": pl, "lng": pg,
            "address": p.get("road_address_name") or p.get("address_name") or "", "city": "", "venue_id": "",
            "m": round(haversine_km((lat, lng), (pl, pg)) * 1000), "from": "kakao", "why": why}


def _merge_kakao(kakao, pools):
    """카카오 후보 중 포스퀘어 줄(포스퀘어 ID 가 있는 내 체크인 포함)과 같은 가게는 그 줄에 합치고 목록에서 뺌.
    같은 가게: 60m 안 같은 이름 / 40m 안 같은 지점명 / 100m 안 같은 도로명+번호·비슷한 이름 / 60m 안 같은 업종·비슷한 이름.
    지점명이나 건물번호가 서로 다르면 안 합침. 한 줄에 가장 가까운 카카오 하나만."""
    pairs = []
    for ki, k in enumerate(kakao):
        kb = _branch(k["name"]).replace("역", "")
        kr = _road_key(k.get("address"))
        for c in pools:
            if not c.get("venue_id") or c["venue_id"].startswith((KAKAO_VENUE, MANUAL_VENUE)):
                continue
            m = haversine_km((k["lat"], k["lng"]), (c["lat"], c["lng"])) * 1000
            if m > 100:
                continue
            full = c["name"] + (" " + c["sub"] if c.get("sub") else "")
            cb = _branch(full).replace("역", "")
            cr = _road_key(c.get("address"))
            if (kb and cb and kb != cb) or (kr and cr and kr != cr):
                continue
            ka, ca = (k.get("category") or "").replace(",", ""), (c.get("category") or "").replace(",", "")
            same_cat = bool(ka and ca) and (ka in ca or ca in ka or _similar(ka, ca) >= 0.7)
            if (m <= 60 and _same_shop(full, k["name"])) or (kb and kb == cb and m <= 40) or \
               (kr and kr == cr and _similar(c["name"], k["name"]) >= 0.5) or \
               (m <= 60 and same_cat and _similar(c["name"], k["name"]) >= 0.6):
                pairs.append((m, ki, c))
    used_k, used_c = set(), set()
    for m, ki, c in sorted(pairs, key=lambda p: p[0]):
        if ki in used_k or id(c) in used_c:
            continue
        used_k.add(ki)
        used_c.add(id(c))
        k = kakao[ki]
        c.update(kakao_id=k.get("kakao_id") or "", kakao_name=k["name"], kakao_addr=k.get("address") or "", both=True)
        c["m"] = min(c["m"], k["m"])
        if (k.get("why") or "").startswith("이름 일치") and not (c.get("why") or "").startswith("이름 일치"):
            c["why"] = "이름 일치 · " + (c.get("why") or "")
            c["score"] = max(c.get("score") or 0, k.get("score") or 0)
        if k["name"] != c["name"] + (" " + c["sub"] if c.get("sub") else ""):
            c["why"] = (c.get("why") or "") + f" · 카카오 '{k['name']}'"
    return [k for i, k in enumerate(kakao) if i not in used_k]


def candidates(lat, lng, query=""):
    """체크인 추가 후보. 결과 {mine, fsq, kakao, addr} — 각 줄 {name, sub, category, lat, lng, address, venue_id, m, from, why, both?}."""
    lat, lng = float(lat), float(lng)
    query = (query or "").strip()
    korea = in_korea(lat, lng)
    # 내 체크인: 500m 안 + (검색어가 있으면) 5km 안 같은 이름
    d = 0.5 / 111.0
    rows = _q("""SELECT FSQ_VENUEID, VENUE, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, CITY, COUNTRY, COUNTRYCODE,
                        COUNT(*) n, MAX(TIME_KST) last
                 FROM FSQ_Swarm
                 WHERE (CAST(LAT AS DECIMAL(10,7)) BETWEEN %s AND %s AND CAST(LNG AS DECIMAL(10,7)) BETWEEN %s AND %s)
                    OR (%s <> '' AND VENUE LIKE %s)
                 GROUP BY FSQ_VENUEID, VENUE, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, CITY, COUNTRY, COUNTRYCODE
                 ORDER BY n DESC LIMIT 300""",
              (lat - d, lat + d, lng - d / math.cos(math.radians(lat)), lng + d / math.cos(math.radians(lat)),
               query, f"%{query[:30]}%"))
    mine, seen = {}, set()
    for r in rows:
        try:
            vl, vg = float(r["LAT"]), float(r["LNG"])
        except (TypeError, ValueError):
            continue
        m = round(haversine_km((lat, lng), (vl, vg)) * 1000)
        hit = bool(query) and (_same_shop(r["VENUE"] + " " + (r["VENUE_SUB"] or ""), query) or query.replace(" ", "") in (r["VENUE"] or "").replace(" ", ""))
        if m > (5000 if hit else 500):
            continue
        key = r["FSQ_VENUEID"] or r["VENUE"]
        c = mine.get(key)
        if c:
            c["n"] += r["n"]
            c["last"] = max(c["last"], r["last"] or "")
            continue
        mine[key] = {"name": r["VENUE"], "sub": r["VENUE_SUB"] or "", "category": r["CATEGORY"] or "", "lat": vl, "lng": vg,
                     "address": r["ADDRESS"] or "", "city": r["CITY"] or "", "country": r["COUNTRY"] or "", "cc": r["COUNTRYCODE"] or "",
                     "venue_id": r["FSQ_VENUEID"] or "", "m": m, "from": "swarm", "hit": hit, "n": r["n"], "last": r["last"] or ""}
    mine = list(mine.values())
    for c in mine:
        c["score"] = (6 if c["hit"] else 0) + 3.5 * math.exp(-c["m"] / 100) + 0.7 * math.log1p(c["n"])
        c["why"] = ("이름 일치 · " if c["hit"] else "") + f"전에 {c['n']}번 · 마지막 {c['last'][:10].replace('-', '.')}"
        seen.add(c["venue_id"])
    # 포스퀘어: 250m 안 + 이름 검색 3km
    fsq = []
    params = [{"ll": f"{lat},{lng}", "radius": 250, "limit": 20, "intent": "browse"}]
    if query:
        params.insert(0, {"ll": f"{lat},{lng}", "query": query, "radius": 3000, "limit": 10, "intent": "browse"})
    for p in params:
        for v in _fsq(p):
            fv = _fsq_venue(v, lat, lng)
            if not fv["venue_id"] or fv["venue_id"] in seen or (fv["category"] or "").startswith(("주거", "집")):
                continue
            has = bool(query) and query.replace(" ", "") in fv["name"].replace(" ", "")
            hit = bool(query) and (_same_shop(fv["name"] + " " + fv["sub"], query) or has)
            if p.get("query") and not hit and _similar(fv["name"], query) < 0.7:
                continue
            seen.add(fv["venue_id"])
            fv["why"] = ("이름 일치 · " if hit else "") + (fv["category"] or "포스퀘어")
            fv["score"] = (6 if hit else 0) + 2.0 * math.exp(-fv["m"] / 80)
            fsq.append(fv)
    # 카카오 (한국만): 주변 업종 + 이름 검색
    kakao = []
    if korea:
        have = set()
        try:
            if query:
                j = _kakao("/v2/local/search/keyword.json", {"query": query, "x": lng, "y": lat, "radius": 3000, "sort": "distance", "size": 5})
                for p in j.get("documents", []):
                    if _same_shop(p["place_name"], query) or query.replace(" ", "") in p["place_name"].replace(" ", ""):
                        k = _kakao_place(p, lat, lng, "이름 일치 · 카카오")
                        k["score"] = 6.0
                        kakao.append(k)
                        have.add(k["kakao_id"])
            for code in ("FD6", "CE7", "MT1", "CS2", "HP8", "PM9", "AT4", "CT1", "OL7", "PK6"):
                j = _kakao("/v2/local/search/category.json", {"category_group_code": code, "x": lng, "y": lat, "radius": 100, "sort": "distance", "size": 5})
                for p in j.get("documents", []):
                    if p.get("id") not in have:
                        have.add(p.get("id"))
                        k = _kakao_place(p, lat, lng)
                        k["score"] = 2.6 * math.exp(-k["m"] / 40)
                        kakao.append(k)
        except Exception:
            pass
        kakao = _merge_kakao(kakao, mine + fsq)
    for lst in (mine, fsq, kakao):
        lst.sort(key=lambda c: (not (c.get("why") or "").startswith("이름 일치"), -c["score"]))
    a = place_address(lat, lng)
    addr = [{"name": a["address"], "sub": "", "category": "", "lat": lat, "lng": lng, "address": a["address"],
             "city": a["city"], "venue_id": "", "m": 0, "from": "addr", "why": "주소"}] if a["address"] else []
    for c in mine + fsq + kakao:
        c["score"] = round(c["score"], 2)
    return {"mine": mine[:8], "fsq": fsq[:10], "kakao": kakao[:6], "addr": addr}


# ─────────────────────────── 저장 값 정하기 ───────────────────────────

def _fsq_match(name, lat, lng):
    """카카오 후보와 같은 가게가 포스퀘어에 있으면 그것 (60m 안 같은 이름 / 40m 안 같은 지점명)."""
    q = re.sub(r"\s+", " ", re.sub(r"\(([^)]*)\)?", r" \1", name or "")).strip()
    br = _branch(q).replace("역", "")
    seen, best = set(), None
    for p in ({"ll": f"{lat},{lng}", "query": q, "radius": 120, "limit": 10, "intent": "browse"},
              {"ll": f"{lat},{lng}", "radius": 60, "limit": 30, "intent": "browse"}):
        for v in _fsq(p):
            if v.get("id") in seen:
                continue
            seen.add(v.get("id"))
            fv = _fsq_venue(v, lat, lng)
            full = fv["name"] + (" " + fv["sub"] if fv["sub"] else "")
            ok = (fv["m"] <= 60 and _same_shop(full, q)) or \
                 (br and fv["m"] <= 40 and br in (fv["sub"] + fv["name"]).replace(" ", "").replace("역", ""))
            if ok and (best is None or fv["m"] < best["m"]):
                best = fv
        if best:
            return best
    return None


def _resolve(c):
    src = c.get("from")
    lat, lng = float(c["lat"]), float(c["lng"])
    if src == "swarm" and c.get("venue_id"):
        rows = _q("""SELECT FSQ_VENUEID, VENUE, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, COUNTRY, COUNTRYCODE, CITY
                     FROM FSQ_Swarm WHERE FSQ_VENUEID=%s
                     ORDER BY (TRIM(IFNULL(ADDRESS,''))<>'') + (TRIM(IFNULL(CATEGORY,''))<>'') + (TRIM(IFNULL(CITY,''))<>'') DESC,
                              FSQ_UNIXTIME DESC LIMIT 1""", (c["venue_id"],))
        if rows:
            r = rows[0]
            vid = r["FSQ_VENUEID"]
            kind = "kakao" if vid.startswith(KAKAO_VENUE) else "manual" if vid.startswith(MANUAL_VENUE) else "fsq"
            return {"source": kind, "venue_id": vid, "name": r["VENUE"], "sub": r["VENUE_SUB"] or "", "category": r["CATEGORY"] or "",
                    "lat": float(r["LAT"]), "lng": float(r["LNG"]), "address": r["ADDRESS"] or "", "city": r["CITY"] or "",
                    "country": r["COUNTRY"] or "", "cc": r["COUNTRYCODE"] or "", "note": "전에 체크인한 장소 그대로"}
    if src == "fsq" and c.get("venue_id"):
        return {"source": "fsq", "venue_id": c["venue_id"], "name": c["name"], "sub": c.get("sub") or "", "category": c.get("category") or "",
                "lat": lat, "lng": lng, "address": c.get("address") or "", "city": c.get("city") or "",
                "country": c.get("country") or "", "cc": c.get("cc") or "", "note": "포스퀘어 장소 값 그대로"}
    if not in_korea(lat, lng):
        o = osm_addr(lat, lng)
        name, sub = (c.get("name") or "", c.get("sub") or "") if src in ("own", "swarm") else ("", "")
        return {"source": "manual", "venue_id": "", "name": name, "sub": sub, "category": c.get("category") or "" if src != "addr" else "",
                "lat": lat, "lng": lng, "address": o["address"], "city": o["city"], "country": o["country"], "cc": o["cc"],
                "note": "포스퀘어에 없어 직접 적는 장소 (주소는 OpenStreetMap)"}
    if src in ("kakao", "swarm") and c.get("name"):
        fv = _fsq_match(c["name"], lat, lng)
        if fv:
            r = _resolve({**fv, "from": "fsq"})
            r["note"] = f"카카오 '{c['name']}' 와 같은 포스퀘어 장소를 찾아 그 값으로" if src == "kakao" else "같은 포스퀘어 장소를 찾아 그 값으로"
            return r
    ad = kakao_addr(lat, lng)
    if src == "kakao" and c.get("kakao_id"):
        name, sub = _split_branch(c["name"], c.get("sub") or "")
        return {"source": "kakao", "venue_id": f"{KAKAO_VENUE}{c['kakao_id']}"[:24], "name": name, "sub": sub,
                "category": c.get("category") or "", "lat": lat, "lng": lng,
                # 카카오 장소의 도로명주소가 있으면 그걸로 (좌표 역지오코딩은 산·지번으로 나올 때가 있음)
                "address": c.get("address") if _road_key(c.get("address")) else (ad["address"] or c.get("address") or ""),
                "city": ad["city"], "country": "대한민국", "cc": "KR", "note": "포스퀘어에 없어 카카오 장소 값으로"}
    name, sub = _split_branch(c.get("name") or "", c.get("sub") or "") if src in ("own", "kakao", "swarm") else ("", "")
    return {"source": "manual", "venue_id": "", "name": name, "sub": sub, "category": c.get("category") or "" if src != "addr" else "",
            "lat": lat, "lng": lng, "address": ad["address"], "city": ad["city"], "country": "대한민국", "cc": "KR",
            "note": "포스퀘어·카카오에 없어 직접 적는 장소"}


def resolve(c):
    """고른 후보 → 저장할 값 {source, venue_id, name, sub, category, lat, lng, address, city, country, cc, note}."""
    r = _resolve(c)
    before = r["address"]
    if (r["cc"] and r["cc"] != "KR") or not in_korea(r["lat"], r["lng"]):
        if r["source"] != "manual" and len(re.sub(r"\b[\d-]{4,}\b", "", before.replace(r["country"] or "@", "")).strip()) < 4:
            o = osm_addr(r["lat"], r["lng"])
            if o["address"]:
                r["address"], r["city"] = o["address"], r["city"] or o["city"]
                r["note"] += " · 주소는 OpenStreetMap 으로 찾음"
        if not r["country"]:
            o = osm_addr(r["lat"], r["lng"])
            r["country"], r["cc"] = o["country"], o["cc"]
        return r
    r["country"], r["cc"] = r["country"] or "대한민국", r["cc"] or "KR"
    src_addr = before
    if c.get("both") and c.get("kakao_name"):
        r["note"] += f" · 카카오 '{c['kakao_name']}' 와 같은 곳"
    if c.get("kakao_addr") and not _road_key(before):
        src_addr = c["kakao_addr"]
    n = norm_addr(src_addr, r["lat"], r["lng"])
    if n["address"]:
        r["address"] = n["address"]
        if r["source"] == "manual" or not r["city"] or r["city"] == "대한민국":
            r["city"] = n["city"] or r["city"]
        if src_addr is not before:
            r["note"] += " · 주소는 카카오 장소 기준"
        elif r["source"] != "manual" and not re.search(_ROAD, re.sub(r"\([^)]*\)", "", before or "")):
            r["note"] += " · 주소는 좌표로 찾음"
    return r


def fill_place(data, keep_address=False):
    """저장 직전: 주소·도시·국가·국가코드를 규칙대로 채움. data 키: lat, lng, address, city, country, countrycode.
    keep_address=True 면 주소에 도로명이 있을 때 사람이 쓴 그대로 둠(도시·국가만 채움)."""
    lat, lng = float(data["lat"]), float(data["lng"])
    addr = (data.get("address") or "").strip()
    if in_korea(lat, lng):
        if keep_address and _road_key(addr):
            n = norm_addr(addr, lat, lng)
            city = n["city"] or data.get("city") or ""
        else:
            n = norm_addr(addr, lat, lng)
            addr, city = n["address"] or addr, n["city"] or data.get("city") or ""
        return {"address": addr, "city": city, "country": "대한민국", "countrycode": "KR"}
    o = osm_addr(lat, lng)
    weak = len(re.sub(r"\b[\d-]{4,}\b", "", addr.replace(data.get("country") or o["country"] or "@", "")).strip()) < 4
    return {"address": o["address"] if weak and o["address"] else addr, "city": data.get("city") or o["city"],
            "country": data.get("country") or o["country"], "countrycode": data.get("countrycode") or o["cc"]}
