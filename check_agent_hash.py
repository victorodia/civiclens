import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from sqlalchemy import select

async def check_agent_hash():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == "victor.odia14@gmail.com"))
        u = res.scalars().first()
        if u:
            print(f"Agent: {u.email}")
            print(f"Hashed Password: {u.hashed_password}")
        else:
            print("Agent not found.")

if __name__ == "__main__":
    asyncio.run(check_agent_hash())
