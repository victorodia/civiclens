import sqlite3
import os

db_path = r'C:\Users\Ontop\Desktop\Python_Projects\CivicLens\backend\civiclens.db'

def check_db():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(results)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Columns in results: {columns}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
