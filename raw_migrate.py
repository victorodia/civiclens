import sqlite3
import psycopg2

conn_sq = sqlite3.connect("/app/civiclens.db")
conn_sq.row_factory = sqlite3.Row
import os
pg = psycopg2.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))  # required: set in .env

bool_cols = {"is_active", "is_2fa_enabled", "requires_password_reset", "is_on_site", "is_verified", "is_compromised", "is_flagged"}

for table in ["users", "election_config", "states", "lgas", "wards", "polling_units", "results", "audit_logs"]:
    print(f"Migrating {table}...")
    try:
        rows = conn_sq.execute(f"SELECT * FROM {table}").fetchall()
        if not rows: 
            print("No rows")
            continue
        keys = list(rows[0].keys())
        
        cols = ",".join(keys)
        vals = ",".join(["%s"] * len(keys))
        query = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT DO NOTHING"
        
        cur = pg.cursor()
        for r in rows:
            new_r = []
            for k, val in zip(keys, r):
                if k in bool_cols:
                    new_r.append(bool(val))
                else:
                    new_r.append(val)
            cur.execute(query, tuple(new_r))
        pg.commit()
        print(f"Inserted {len(rows)} rows")
    except Exception as e:
        print("Error migrating", table, e)
        pg.rollback()

print("Done")
