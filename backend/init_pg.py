import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from app.db import Base
from app import models  # Ensure models are loaded

async def init_db():
    pg_url = os.environ["DATABASE_URL"]  # required: set in .env
    print(f"Connecting to {pg_url}...")
    engine = create_async_engine(pg_url, echo=True)
    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized.")

if __name__ == "__main__":
    asyncio.run(init_db())
