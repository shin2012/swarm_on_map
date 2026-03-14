from flask import Flask, render_template, jsonify
import mysql.connector
import os

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Original data from FSQ_Swarm only
        query = """
            SELECT 
                FSQ_UNIXTIME, 
                CASE 
                    WHEN VENUE_SUB LIKE '%점' THEN CONCAT(VENUE, ' (', VENUE_SUB, ')')
                    ELSE VENUE 
                END AS VENUE,
                CATEGORY, 
                LAT, 
                LNG, 
                ADDRESS, 
                TIME_KST, 
                PHOTO, 
                SHOUT
            FROM FSQ_Swarm 
            WHERE LAT != '' AND LNG != ''
            ORDER BY FSQ_UNIXTIME ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print(f"Error in get_data: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
