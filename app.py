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
from flask import Flask, render_template, jsonify, request
from dateutil import parser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

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
        while True:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT FSQ_ID, LAT, LNG FROM FSQ_Swarm WHERE CITY IS NULL AND LAT != '' AND LNG != '' LIMIT 1")
                row = cursor.fetchone()
                
                if not row:
                    cursor.close()
                    conn.close()
                    time.sleep(60) # Sleep longer if no work
                    continue
                
                fsq_id = row['FSQ_ID']
                lat = row['LAT']
                lng = row['LNG']
                
                # Fetch from Nominatim
                url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json&accept-language=ko"
                headers = {'User-Agent': 'fsq_map_insights/1.0'}
                res = requests.get(url, headers=headers, timeout=10)
                
                city_name = "Unknown"
                if res.status_code == 200:
                    data = res.json()
                    addr = data.get('address', {})
                    # Try to find the most relevant city/province name
                    city_name = addr.get('city') or addr.get('town') or addr.get('province') or addr.get('county') or addr.get('village') or "Unknown"
                    if city_name.endswith('도') and (addr.get('city') or addr.get('county')):
                         # Prefer city/county over province if both exist but city wasn't first choice (edge cases)
                         city_name = addr.get('city') or addr.get('county') or city_name
                
                # Update DB
                cursor.execute("UPDATE FSQ_Swarm SET CITY=%s WHERE FSQ_ID=%s", (city_name, fsq_id))
                conn.commit()
                cursor.close()
                conn.close()
                log(f"Geocoded {fsq_id}: {city_name}")
                
                time.sleep(1.5) # Respect Nominatim rate limits
            except Exception as e:
                log(f"Geocode worker error: {e}")
                time.sleep(10)

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage')
def manage():
    return render_template('manage.html')

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
                VENUE as VENUE_ONLY, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, TIME_LOCAL, TIME_KST, TIME_UTC, SHOUT, GCal_EventID
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
            SELECT DISTINCT VENUE, VENUE_SUB, ADDRESS, LAT, LNG, CATEGORY, FSQ_TIMEZONEOFFSET, FSQ_VENUEID, COUNTRY, COUNTRYCODE,
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

@app.route('/api/manage/add', methods=['POST'])
def add_checkin():
    data = request.json
    try:
        offset = get_timezone_offset(data['lat'], data['lng'], data['time_local'])
        unixtime, time_utc, time_kst, time_local = calculate_times(data['time_local'], offset)
        
        # Use the same unixtime for FSQ_ID to keep them consistent
        fsq_id = f"ManuallySaved_{unixtime}"
        
        gcal_data = {**data, 'fsq_unixtime': unixtime, 'venue': data['venue_only']}
        gcal_eventid = sync_to_gcal('add', gcal_data)
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO FSQ_Swarm (FSQ_ID, FSQ_UNIXTIME, FSQ_TIMEZONEOFFSET, VENUE, VENUE_SUB, CATEGORY, LAT, LNG, ADDRESS, 
             COUNTRY, COUNTRYCODE, TIME_LOCAL, TIME_KST, TIME_UTC, SHOUT, GCal_EventID, MODIFIED, FSQ_VENUEID, FSQ_ISMAYER, FSQ_ISPRIVATE, CALENDAR_SENT)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, 'N', 'N', 'Y')
        """
        cursor.execute(query, (fsq_id, unixtime, offset, data['venue_only'], data.get('venue_sub', ''), data['category'], data['lat'], data['lng'], data['address'], 
            data.get('country', ''), data.get('countrycode', ''), time_local, time_kst, time_utc, data['shout'], gcal_eventid, data.get('fsq_venueid', '')))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "fsq_id": fsq_id})
    except Exception as e:
        log(f"Error adding checkin: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/manage/update/<fsq_id>', methods=['PUT'])
def update_checkin(fsq_id):
    data = request.json
    try:
        offset = get_timezone_offset(data['lat'], data['lng'], data['time_local'])
        unixtime, time_utc, time_kst, time_local = calculate_times(data['time_local'], offset)
        sync_data = {**data, 'fsq_id': fsq_id, 'fsq_unixtime': unixtime, 'venue': data['venue_only']}
        sync_to_swarm('update', sync_data)
        sync_to_gcal('update', sync_data)
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            UPDATE FSQ_Swarm SET VENUE=%s, VENUE_SUB=%s, CATEGORY=%s, LAT=%s, LNG=%s, ADDRESS=%s, 
                TIME_LOCAL=%s, TIME_KST=%s, TIME_UTC=%s, FSQ_TIMEZONEOFFSET=%s, SHOUT=%s, FSQ_UNIXTIME=%s, MODIFIED=NOW(), CITY=NULL
            WHERE FSQ_ID=%s
        """
        cursor.execute(query, (data['venue_only'], data.get('venue_sub', ''), data['category'], data['lat'], data['lng'], data['address'], 
            time_local, time_kst, time_utc, offset, data['shout'], unixtime, fsq_id))
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
        gcal_ok = True
        if gcal_id:
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
