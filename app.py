import mysql.connector
import os
import json
import time
import requests
import calendar
import sys
import threading
import pytz
from timezonefinder import TimezoneFinder
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, redirect
from dateutil import parser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import venue

def log(msg):
    sys.stderr.write(f"LOG: {msg}\n")
    sys.stderr.flush()

app = Flask(__name__)

# MariaDB Configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "mariadb"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE", "swarm"),
    "port": int(os.getenv("DB_PORT", 3306))
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

tf = TimezoneFinder()
venue.init(get_db_connection)

def setup_db_and_workers():
    # Wait for DB to be ready
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Ensure CITY column exists
            try:
                cursor.execute("ALTER TABLE FSQ_Swarm ADD COLUMN CITY VARCHAR(255) DEFAULT NULL")
                conn.commit()
                log("Added CITY column to FSQ_Swarm.")
            except mysql.connector.Error as err:
                if err.errno == 1060: # Duplicate column name
                    pass
                else:
                    log(f"DB init error: {err}")
            cursor.close()
            conn.close()
            break
        except Exception as e:
            log(f"Waiting for DB... {e}")
            time.sleep(3)

    # Start background geocoder
    def geocode_worker():
        # Prevent running twice in Flask debug mode
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and app.debug:
            return

        skipped_ids = set()
        backoff_until = 0
        
        while True:
            try:
                if time.time() < backoff_until:
                    time.sleep(60)
                    continue

                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                
                # Fetch a random record that hasn't been skipped in this session
                query = "SELECT FSQ_ID, LAT, LNG FROM FSQ_Swarm WHERE CITY IS NULL AND LAT != '' AND LNG != '' "
                params = []
                if skipped_ids:
                    placeholders = ', '.join(['%s'] * len(skipped_ids))
                    query += f"AND FSQ_ID NOT IN ({placeholders}) "
                    params = list(skipped_ids)
                query += "ORDER BY RAND() LIMIT 1"
                
                cursor.execute(query, params)
                row = cursor.fetchone()
                
                if not row:
                    cursor.close()
                    conn.close()
                    if skipped_ids:
                        log("All pending records skipped in this session. Resetting skip list in 10 minutes.")
                        skipped_ids.clear()
                        time.sleep(600)
                    else:
                        time.sleep(300)
                    continue
                
                fsq_id = row['FSQ_ID']
                lat, lng = row['LAT'], row['LNG']
                
                # OPTIMIZATION: Check if we already have a CITY for this exact LAT/LNG in our DB
                cursor.execute("SELECT CITY FROM FSQ_Swarm WHERE LAT=%s AND LNG=%s AND CITY IS NOT NULL LIMIT 1", (lat, lng))
                existing_row = cursor.fetchone()
                
                if existing_row and existing_row['CITY']:
                    city_name = existing_row['CITY']
                    cursor.execute("UPDATE FSQ_Swarm SET CITY=%s WHERE FSQ_ID=%s", (city_name, fsq_id))
                    conn.commit()
                    log(f"Optimized: Copied CITY from existing record for {fsq_id} ({lat}, {lng}) -> {city_name}")
                    cursor.close()
                    conn.close()
                    continue # Skip API call and move to next record immediately

                url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json&accept-language=ko"
                headers = {
                    'User-Agent': 'FoursquareSwarmMapInsights/1.1 (contact: shin2012; personal project for checkin visualization)'
                }
                
                res = requests.get(url, headers=headers, timeout=15)
                
                if res.status_code == 200:
                    data = res.json()
                    addr = data.get('address', {})
                    city_name = addr.get('city') or addr.get('town') or addr.get('province') or addr.get('county') or addr.get('village')
                    
                    if city_name and city_name.endswith('도') and (addr.get('city') or addr.get('county')):
                        city_name = addr.get('city') or addr.get('county')
                    
                    if city_name:
                        cursor.execute("UPDATE FSQ_Swarm SET CITY=%s WHERE FSQ_ID=%s", (city_name, fsq_id))
                        conn.commit()
                        log(f"Successfully geocoded {fsq_id} -> {city_name}")
                    else:
                        log(f"No city info found for {fsq_id} ({lat}, {lng}). Skipping.")
                        skipped_ids.add(fsq_id)
                
                elif res.status_code in [403, 429]:
                    log(f"Nominatim API Error {res.status_code}. Backing off for 1 hour.")
                    backoff_until = time.time() + 3600
                else:
                    log(f"Nominatim API Error {res.status_code} for {fsq_id}. Skipping.")
                    skipped_ids.add(fsq_id)

                cursor.close()
                conn.close()
                # Conservative delay + jitter
                time.sleep(3.0 + (time.time() % 2))
                
            except Exception as e:
                log(f"Geocode worker exception: {e}")
                time.sleep(30)

    t = threading.Thread(target=geocode_worker, daemon=True)
    t.start()

# Initialize DB and worker on startup
threading.Thread(target=setup_db_and_workers, daemon=True).start()

# --- Sync Helpers ---

def save_gcal_token(creds):
    """Save updated OAuth2 credentials back to DB."""
    try:
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            'expiry': creds.expiry.isoformat() if creds.expiry else None
        }
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE FSQ_GCalAuth SET data=%s WHERE type='token.json' ORDER BY id DESC LIMIT 1", (json.dumps(token_data),))
        conn.commit()
        cursor.close()
        conn.close()
        log("GCal Token updated in DB.")
    except Exception as e:
        log(f"Error saving GCal token: {e}")

def get_gcal_service():
    """Fetch OAuth2 credentials from DB and return GCal service."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT data FROM FSQ_GCalAuth WHERE type='token.json' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            token_data = json.loads(row['data'])
            creds = Credentials.from_authorized_user_info(token_data)
            
            if creds and creds.expired and creds.refresh_token:
                log("Token expired, refreshing...")
                creds.refresh(Request())
                save_gcal_token(creds)
            
            return build('calendar', 'v3', credentials=creds)
        else:
            log("No 'token.json' found in FSQ_GCalAuth table.")
    except Exception as e:
        log(f"GCal Auth Error: {e}")
    return None

GCAL_ID = "2nni9aea85ne72iofr53f51pts@group.calendar.google.com"

# CarPlay API Token
CARPLAY_API_TOKEN = os.getenv("CARPLAY_API_TOKEN", "")

def sync_to_swarm(action, data):
    """Implement Swarm API sync logic."""
    fsq_id = data.get('fsq_id')
    if not fsq_id or fsq_id.startswith('ManuallySaved'):
        return True 
    
    api_key = os.getenv("SWARM_API_KEY")
    if not api_key:
        log("SWARM_API_KEY not found in .env")
        return False

    v_date = "20231010" 
    try:
        if action == 'delete':
            log(f"Deleting checkin from Swarm: {fsq_id}")
            delete_url = f"https://api.foursquare.com/v2/checkins/{fsq_id}/delete"
            res = requests.post(delete_url, params={'oauth_token': api_key, 'v': v_date})
            log(f"Swarm Delete Result: {res.status_code}")
            return res.status_code == 200
        elif action == 'update':
            unixtime = data.get('fsq_unixtime')
            if unixtime and (time.time() - unixtime) < 86400:
                log(f"Updating shout in Swarm: {fsq_id}")
                update_url = f"https://api.foursquare.com/v2/checkins/{fsq_id}/update"
                params = {
                    'oauth_token': api_key,
                    'v': v_date,
                    'shout': data.get('shout', '')
                }
                res = requests.post(update_url, params=params)
                log(f"Swarm Update Result: {res.status_code} - {res.text[:100]}")
                return res.status_code == 200
            else:
                log(f"Skipping Swarm update for {fsq_id}: older than 24h")
                return True
    except Exception as e:
        log(f"Swarm Sync Error: {e}")
    return True

def sync_to_gcal(action, data):
    """Sync changes to Google Calendar."""
    gcal_id = data.get('gcal_eventid')
    fsq_id = data.get('fsq_id')
    
    log(f"Starting GCal sync: {action} for {fsq_id}")

    if not gcal_id and fsq_id and action in ['update', 'delete']:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT GCal_EventID FROM FSQ_Swarm WHERE FSQ_ID=%s", (fsq_id,))
            row = cursor.fetchone()
            if row: gcal_id = row['GCal_EventID']
            cursor.close()
            conn.close()
        except Exception as e:
            log(f"DB Fetch GCal ID Error: {e}")

    if not gcal_id and action != 'add':
        log(f"Skipping GCal {action}: No GCal_EventID found")
        return True
    
    service = get_gcal_service()
    if not service:
        log("GCal Sync Error: Could not get GCal service")
        return False

    try:
        event_body = {}
        if action != 'delete':
            start_dt = datetime.fromtimestamp(data['fsq_unixtime'], tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            end_dt = datetime.fromtimestamp(data['fsq_unixtime'] + 1800, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            venue_name = data.get('venue_only', data.get('venue', 'Unknown'))
            sub = data.get('venue_sub')
            if sub and sub.endswith('점'):
                venue_name = f"{venue_name} ({sub})"

            event_body = {
                'summary': venue_name,
                'location': data.get('address'),
                'description': data.get('shout'),
                'start': {'dateTime': start_dt},
                'end': {'dateTime': end_dt},
            }
        
        if action == 'add':
            log(f"Adding to GCal: {event_body['summary']}")
            event = service.events().insert(calendarId=GCAL_ID, body=event_body).execute()
            return event.get('id')
        
        # Search all calendars if not in GCAL_ID
        actual_cid = GCAL_ID
        try:
            service.events().get(calendarId=GCAL_ID, eventId=gcal_id).execute()
        except Exception:
            calendar_list = service.calendarList().list().execute()
            found_cid = None
            for entry in calendar_list.get('items', []):
                try:
                    cid = entry['id']
                    service.events().get(calendarId=cid, eventId=gcal_id).execute()
                    found_cid = cid
                    break
                except Exception: continue
            if not found_cid:
                log(f"GCal Error: Event {gcal_id} not found anywhere.")
                return False
            actual_cid = found_cid

        if action == 'update':
            log(f"Updating GCal Event: {gcal_id} in {actual_cid}")
            service.events().patch(calendarId=actual_cid, eventId=gcal_id, body=event_body).execute()
        elif action == 'delete':
            log(f"Deleting GCal Event: {gcal_id} from {actual_cid}")
            service.events().delete(calendarId=actual_cid, eventId=gcal_id).execute()
        return True
    except Exception as e:
        log(f"GCal Sync Exception during {action}: {e}")
        return False

def get_timezone_offset(lat, lng, time_local_str):
    """Calculate minute offset for given coordinates and local time."""
    try:
        tz_str = tf.timezone_at(lat=float(lat), lng=float(lng))
        if not tz_str:
            return 540
        tz = pytz.timezone(tz_str)
        dt_naive = parser.parse(time_local_str)
        dt_aware = tz.localize(dt_naive, is_dst=None)
        return int(dt_aware.utcoffset().total_seconds() / 60)
    except Exception as e:
        log(f"Timezone calc error: {e}")
        return 540

def calculate_times(time_local_str, offset_minutes):
    """Calculate all time formats based on local time string and offset."""
    dt_naive = parser.parse(time_local_str)
    unixtime = calendar.timegm(dt_naive.utctimetuple()) - (offset_minutes * 60)
    time_utc = datetime.fromtimestamp(unixtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    time_kst = datetime.fromtimestamp(unixtime + 32400, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    time_local = datetime.fromtimestamp(unixtime + (offset_minutes * 60), tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return unixtime, time_utc, time_kst, time_local

# --- API Routes ---

_MOBILE_UA = ('iphone', 'ipad', 'android', 'mobile', 'blackberry', 'windows phone')

def is_mobile():
    ua = request.headers.get('User-Agent', '').lower()
    return any(k in ua for k in _MOBILE_UA)

@app.route('/')
def index():
    if is_mobile():
        return redirect('/m/')
    return render_template('index.html')

@app.route('/manage')
def manage():
    if is_mobile():
        return redirect('/m/')
    return render_template('manage.html')

@app.route('/m')
@app.route('/m/')
def mobile():
    return render_template('m/index.html')

@app.route('/api/manage/list')
def get_manage_list():
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    offset = (page - 1) * limit
    q = request.args.get('q', '')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        count_query = "SELECT COUNT(*) as total FROM FSQ_Swarm WHERE VENUE LIKE %s OR ADDRESS LIKE %s"
        cursor.execute(count_query, (f"%{q}%", f"%{q}%"))
        total = cursor.fetchone()['total']
        query = """
            SELECT FSQ_ID, FSQ_UNIXTIME, FSQ_TIMEZONEOFFSET, CITY,
                CASE WHEN VENUE_SUB LIKE '%%점' THEN CONCAT(VENUE, ' (', VENUE_SUB, ')') ELSE VENUE END AS VENUE,
                VENUE as VENUE_ONLY, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, TIME_LOCAL, TIME_KST, TIME_UTC, SHOUT, GCal_EventID,
                COUNTRY, COUNTRYCODE, FSQ_VENUEID
            FROM FSQ_Swarm WHERE VENUE LIKE %s OR ADDRESS LIKE %s ORDER BY FSQ_UNIXTIME DESC LIMIT %s OFFSET %s
        """
        cursor.execute(query, (f"%{q}%", f"%{q}%", limit, offset))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"data": rows, "total": total, "page": page, "limit": limit})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/venues')
def search_venues():
    q = request.args.get('q', '')
    if len(q) < 2: return jsonify([])
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT DISTINCT VENUE, VENUE_SUB, ADDRESS, LAT, LNG, CATEGORY, FSQ_TIMEZONEOFFSET, FSQ_VENUEID, COUNTRY, COUNTRYCODE, CITY,
                CASE WHEN VENUE_SUB LIKE '%%점' THEN CONCAT(VENUE, ' (', VENUE_SUB, ')') ELSE VENUE END AS DISPLAY_NAME
            FROM FSQ_Swarm WHERE VENUE LIKE %s LIMIT 10
        """
        cursor.execute(query, (f"%{q}%",))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/categories')
def search_categories():
    q = request.args.get('q', '')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT DISTINCT CATEGORY FROM FSQ_Swarm WHERE CATEGORY LIKE %s AND CATEGORY IS NOT NULL ORDER BY CATEGORY ASC LIMIT 15"
        cursor.execute(query, (f"%{q}%",))
        rows = [r['CATEGORY'] for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/candidates')
def venue_candidates():
    """좌표 근처 후보: 내 체크인 · 포스퀘어 · 카카오(한국) · 주소. 같은 가게는 포스퀘어+카카오 한 줄."""
    try:
        return jsonify(venue.candidates(request.args['lat'], request.args['lng'], request.args.get('q', '')))
    except Exception as e:
        log(f"candidates error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/manage/resolve', methods=['POST'])
def venue_resolve():
    """고른 후보 → 저장할 값 (포스퀘어 > 카카오 > 직접, 주소 규칙 적용)."""
    try:
        return jsonify(venue.resolve(request.json.get('cand') or {}))
    except Exception as e:
        log(f"resolve error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/manage/geocode')
def venue_geocode():
    """좌표 → 주소·도시·국가 (한국 카카오, 해외 OpenStreetMap)."""
    try:
        return jsonify(venue.place_address(request.args['lat'], request.args['lng']))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/manage/add', methods=['POST'])
def add_checkin():
    data = request.json
    try:
        offset = get_timezone_offset(data['lat'], data['lng'], data['time_local'])
        unixtime, time_utc, time_kst, time_local = calculate_times(data['time_local'], offset)
        
        # Use the same unixtime for FSQ_ID to keep them consistent
        fsq_id = f"ManuallySaved_{unixtime}"
        # 주소·도시·국가: 한국은 '{우편번호} 대한민국 {행정구역} {도로명} {건물}', 해외는 OpenStreetMap (venue.py)
        place = venue.fill_place(data, keep_address=bool(data.get('resolved')))
        venue_id = (data.get('fsq_venueid') or '').strip() or f"{venue.MANUAL_VENUE}{unixtime}"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM FSQ_Swarm WHERE FSQ_ID=%s", (fsq_id,))
        if cursor.fetchone():
            fsq_id = f"ManuallySaved_{unixtime + 1}"
        # CALENDAR_SENT='N' → 람다(getSwarmCheckins, cron_FSQ-GCal-Sync 1분마다)가 구글 캘린더에 올리고 'Y' + GCal_EventID 로 바꿈
        # 람다가 설명을 SHOUT + PHOTO 로 만들어서 PHOTO 가 NULL 이면 그 줄에서 멈춤 → '' 로 넣음
        query = """
            INSERT INTO FSQ_Swarm (FSQ_ID, FSQ_UNIXTIME, FSQ_TIMEZONEOFFSET, VENUE, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, 
             COUNTRY, COUNTRYCODE, CITY, TIME_LOCAL, TIME_KST, TIME_UTC, SHOUT, PHOTO, GCal_EventID, MODIFIED, FSQ_VENUEID, FSQ_ISMAYER, FSQ_ISPRIVATE, CALENDAR_SENT,
             KAKAO_PLACE_ID, TMAP_POI_ID)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '', NULL, NOW(), %s, 'N', 'N', 'N', %s, %s)
        """
        kakao_place_id = (data.get('kakao_place_id') or '')[:20] or None
        tmap_poi_id = (data.get('tmap_poi_id') or '')[:20] or None
        cursor.execute(query, (fsq_id, unixtime, offset, data['venue_only'], data.get('venue_sub', ''), data.get('category', ''),
            f"{float(data['lat']):.7f}", f"{float(data['lng']):.7f}", place['address'][:255],
            place['country'], place['countrycode'], place['city'], time_local, time_kst, time_utc, data.get('shout', ''), venue_id[:24],
            kakao_place_id, tmap_poi_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "fsq_id": fsq_id, "venue_id": venue_id[:24], "address": place['address']})
    except Exception as e:
        log(f"Error adding checkin: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/update/<fsq_id>', methods=['PUT'])
def update_checkin(fsq_id):
    data = request.json
    try:
        offset = get_timezone_offset(data['lat'], data['lng'], data['time_local'])
        unixtime, time_utc, time_kst, time_local = calculate_times(data['time_local'], offset)
        place = venue.fill_place(data, keep_address=True)
        data['address'] = place['address']
        sync_data = {**data, 'fsq_id': fsq_id, 'fsq_unixtime': unixtime, 'venue': data['venue_only']}
        sync_to_swarm('update', sync_data)
        sync_to_gcal('update', sync_data)
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            UPDATE FSQ_Swarm SET
                CITY=IF(ABS(CAST(LAT AS DECIMAL(12,7)) - %s) < 0.00001 AND ABS(CAST(LNG AS DECIMAL(12,7)) - %s) < 0.00001
                        AND IFNULL(CITY,'') <> '', CITY, %s),
                VENUE=%s, VENUE_SUB=%s, CATEGORY=%s, LAT=%s, LNG=%s, ADDRESS=%s, 
                TIME_LOCAL=%s, TIME_KST=%s, TIME_UTC=%s, FSQ_TIMEZONEOFFSET=%s, SHOUT=%s, FSQ_UNIXTIME=%s, MODIFIED=NOW(),
                COUNTRY=%s, COUNTRYCODE=%s, FSQ_VENUEID=COALESCE(NULLIF(%s, ''), FSQ_VENUEID),
                KAKAO_PLACE_ID=COALESCE(NULLIF(%s, ''), KAKAO_PLACE_ID),
                TMAP_POI_ID=COALESCE(NULLIF(%s, ''), TMAP_POI_ID)
            WHERE FSQ_ID=%s
        """
        kakao_place_id = (data.get('kakao_place_id') or '')[:20]
        tmap_poi_id = (data.get('tmap_poi_id') or '')[:20]
        # 도시: 위치가 그대로면 기존 값(포스퀘어 값) 유지, 옮겼으면 새 위치 기준
        cursor.execute(query, (float(data['lat']), float(data['lng']), place['city'] or None,
            data['venue_only'], data.get('venue_sub', ''), data.get('category', ''), data['lat'], data['lng'], place['address'][:255],
            time_local, time_kst, time_utc, offset, data.get('shout', ''), unixtime,
            place['country'], place['countrycode'], (data.get('fsq_venueid') or '')[:24],
            kakao_place_id, tmap_poi_id, fsq_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        log(f"Error updating checkin: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/delete/<fsq_id>', methods=['DELETE'])
def delete_checkin(fsq_id):
    gcal_id = request.args.get('gcal_id')
    try:
        log(f"Starting deletion sequence for {fsq_id}")
        swarm_ok = sync_to_swarm('delete', {'fsq_id': fsq_id})
        # 화면에 GCal_EventID 가 없어도(람다가 막 등록한 경우) DB 에서 찾아 지움
        gcal_ok = sync_to_gcal('delete', {'gcal_eventid': gcal_id, 'fsq_id': fsq_id})
        
        if not swarm_ok or not gcal_ok:
            return jsonify({"error": "Failed to sync deletion with external services. DB not updated."}), 500

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM FSQ_Swarm WHERE FSQ_ID=%s", (fsq_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        log(f"Deletion Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/data')
def get_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT FSQ_UNIXTIME, CASE WHEN VENUE_SUB LIKE '%점' THEN CONCAT(VENUE, ' (', VENUE_SUB, ')') ELSE VENUE END AS VENUE,
                CATEGORY, LAT, LNG, ADDRESS, CITY, TIME_KST, PHOTO, SHOUT, FSQ_ID, GCal_EventID
            FROM FSQ_Swarm WHERE LAT != '' AND LNG != '' ORDER BY FSQ_UNIXTIME ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- CarPlay API ---

@app.route('/api/carplay/health', methods=['GET'])
def carplay_health():
    return jsonify({'status': 'ok'})

def check_carplay_auth():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not CARPLAY_API_TOKEN or token != CARPLAY_API_TOKEN:
        return False
    return True

@app.route('/api/carplay/event', methods=['POST'])
def carplay_event():
    if not check_carplay_auth():
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({'error': 'invalid json'}), 400

    event_type = data.get('event')
    if event_type not in ('car_start', 'car_end'):
        return jsonify({'error': 'event must be car_start or car_end'}), 400

    from datetime import timedelta
    ts_str = data.get('timestamp')
    if ts_str:
        try:
            dt = datetime.fromisoformat(ts_str)
        except ValueError:
            return jsonify({'error': 'invalid timestamp format'}), 400
    else:
        dt = datetime.now(timezone(timedelta(hours=9)))

    if dt.tzinfo:
        dt_kst = dt.astimezone(timezone(timedelta(hours=9)))
    else:
        dt_kst = dt

    event_time = dt_kst.strftime('%Y-%m-%d %H:%M:%S')
    lat = data.get('lat', '')
    lng = data.get('lng', '')
    device = data.get('device', '')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO FSQ_CarPlay (event_type, event_time, lat, lng, device) VALUES (%s, %s, %s, %s, %s)',
            (event_type, event_time, str(lat) if lat else None, str(lng) if lng else None, device or None)
        )
        conn.commit()
        insert_id = cursor.lastrowid
        cursor.close()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'status': 'ok', 'id': insert_id, 'event': event_type, 'time': event_time}), 201

@app.route('/api/carplay/history', methods=['GET'])
def carplay_history():
    if not check_carplay_auth():
        return jsonify({'error': 'unauthorized'}), 401

    limit = request.args.get('limit', 20, type=int)
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, event_type, event_time, lat, lng, device, created_at FROM FSQ_CarPlay ORDER BY event_time DESC LIMIT %s', (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = []
        for r in rows:
            result.append({
                'id': r['id'], 'event': r['event_type'], 'time': str(r['event_time']),
                'lat': r['lat'], 'lng': r['lng'], 'device': r['device'],
                'created_at': str(r['created_at'])
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
