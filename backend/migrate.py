import asyncio
from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def migrate_data():
    sqlite_url = "sqlite:////app/civiclens.db"
    pg_url = os.environ["DATABASE_URL"]  # required: set in .env
    
    print(f"Migrating from {sqlite_url} to {pg_url}")
    
    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_async_engine(pg_url)
    
    meta = MetaData()
    
    meta.reflect(bind=sqlite_engine)
    
    with sqlite_engine.connect() as sqlite_conn:
        async with pg_engine.begin() as pg_conn:
            for table in meta.sorted_tables:
                print(f"Migrating table: {table.name}")
                result = sqlite_conn.execute(table.select())
                rows = result.fetchall()
                if rows:
                    data = [dict(row._mapping) for row in rows]
                    await pg_conn.execute(table.insert(), data)
    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_data())
