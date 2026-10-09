import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "civiclens.db")
)

# Never log the full URL: it carries credentials.
def _safe_db_label(url: str) -> str:
    return "sqlite (local dev)" if url.startswith("sqlite") else "postgresql (configured)"

print(f"[DB] engine target: {_safe_db_label(DATABASE_URL)}")

# Create an async database engine
# Note: For SQLite we need check_same_thread=False, for Postgres we don't.
# echo=False: SQL statement logging belongs in debug sessions only — it
# leaks table contents and query structure into stdout.
if "sqlite" in DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
