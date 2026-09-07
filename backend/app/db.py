import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# USE ABSOLUTE PATH TO PREVENT "TABLE NOT FOUND" ERRORS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATABASE_PATH = os.path.join(PROJECT_ROOT, "civiclens.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

print(f"DATABASE CONNECTING TO: {DATABASE_URL}")

# Create an async database engine
engine = create_async_engine(
    DATABASE_URL, 
    echo=True, 
    connect_args={"check_same_thread": False}
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
