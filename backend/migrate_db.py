
import sqlite3
import os

db_path = r'C:\Users\Ontop\Desktop\Python_Projects\CivicLens\backend\civiclens.db'

def migrate():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'hashed_duress_password' not in columns:
            print("Adding hashed_duress_password column...")
            cursor.execute("ALTER TABLE users ADD COLUMN hashed_duress_password TEXT")
            conn.commit()

        if 'check_in_lat' not in columns:
            print("Adding check_in_lat column...")
            cursor.execute("ALTER TABLE users ADD COLUMN check_in_lat FLOAT")
            conn.commit()

        if 'check_in_lng' not in columns:
            print("Adding check_in_lng column...")
            cursor.execute("ALTER TABLE users ADD COLUMN check_in_lng FLOAT")
            conn.commit()
            print("Geospatial columns added successfully.")
        else:
            print("Geospatial columns already exist.")

        # Results table migration
        cursor.execute("PRAGMA table_info(results)")
        columns_results = [row[1] for row in cursor.fetchall()]
        if 'video_url' not in columns_results:
            print("Adding video_url column to results...")
            cursor.execute("ALTER TABLE results ADD COLUMN video_url TEXT")
            conn.commit()

        if 'is_flagged' not in columns_results:
            print("Adding AI verification columns to results...")
            cursor.execute("ALTER TABLE results ADD COLUMN ai_party_a_votes INTEGER")
            cursor.execute("ALTER TABLE results ADD COLUMN ai_party_b_votes INTEGER")
            cursor.execute("ALTER TABLE results ADD COLUMN ai_party_c_votes INTEGER")
            cursor.execute("ALTER TABLE results ADD COLUMN ai_confidence FLOAT")
            cursor.execute("ALTER TABLE results ADD COLUMN is_flagged BOOLEAN DEFAULT 0")
            conn.commit()
            print("AI verification columns added successfully.")
        else:
            print("AI verification columns already exist.")
            
        if 'latitude' not in columns_results:
            print("Adding latitude and longitude columns to results...")
            cursor.execute("ALTER TABLE results ADD COLUMN latitude FLOAT")
            cursor.execute("ALTER TABLE results ADD COLUMN longitude FLOAT")
            conn.commit()
            print("Geolocation columns added to results successfully.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
