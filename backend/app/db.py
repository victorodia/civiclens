import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "civiclens.db")
)

print(f"DATABASE CONNECTING TO: {DATABASE_URL}")

# Create an async database engine
# Note: For SQLite we need check_same_thread=False, for Postgres we don't.
if "sqlite" in DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
