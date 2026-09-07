import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from app.security import get_password_hash
from sqlalchemy import select

async def reset_agent():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == "victor.odia14@gmail.com"))
        agent = res.scalars().first()
        if agent:
            print(f"Resetting password for agent: {agent.email}")
            agent.hashed_password = get_password_hash("admin123")
            agent.requires_password_reset = False
            await db.commit()
            print("Password reset to 'admin123'")
        else:
            print("Agent not found.")

if __name__ == "__main__":
    asyncio.run(reset_agent())
