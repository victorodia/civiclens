import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from sqlalchemy import select

async def list_users():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        print(f"--- Complete Registry: {len(users)} User(s) Found ---")
        for u in users:
            print(f"Email: {u.email} | Role: {u.role} | Active: {u.is_active}")

if __name__ == "__main__":
    asyncio.run(list_users())
