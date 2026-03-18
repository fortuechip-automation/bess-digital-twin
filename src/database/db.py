import psycopg2
import time

DB_CONFIG = {
    "dbname": "bess",
    "user": "bessuser",
    "password": "CHANGE ME",
    "host": "DB HOST",
    "port": 5432
}

def get_connection():
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            return conn
        except Exception as e:
            print(f"[DB] Connection failed: {e}. Retrying in 3s...")
            time.sleep(3)

def execute_query(sql, params=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
    except Exception as e:
        print(f"[DB] Error executing query: {e}")
    finally:
        cur.close()
        conn.close()

def fetch_query(sql, params=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as e:
        print(f"[DB] Error fetching query: {e}")
        return None
    finally:
        cur.close()
        conn.close()
