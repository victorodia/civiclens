import sqlite3
for p in ['/home/ubuntu/civiclens/backend/civiclens.db', '/home/ubuntu/civiclens/backend/app/civiclens.db', '/home/ubuntu/civiclens/civiclens.db']:
    print("Testing", p)
    try:
        conn = sqlite3.connect(p)
        print(conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
        conn.close()
    except Exception as e:
        print(e)
