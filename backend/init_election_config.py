import sqlite3

conn = sqlite3.connect('civiclens.db')
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS election_config (
    id TEXT PRIMARY KEY,
    party_a_name TEXT DEFAULT 'Party A',
    party_b_name TEXT DEFAULT 'Party B',
    party_c_name TEXT DEFAULT 'Party C',
    election_name TEXT DEFAULT 'General Election',
    updated_at DATETIME
)""")

cursor.execute("""INSERT OR IGNORE INTO election_config
    (id, party_a_name, party_b_name, party_c_name, election_name)
    VALUES ('global', 'Party A', 'Party B', 'Party C', 'General Election')""")

conn.commit()
rows = cursor.execute("SELECT * FROM election_config").fetchall()
print("election_config table ready:", rows)
conn.close()
