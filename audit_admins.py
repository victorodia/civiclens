import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from sqlalchemy import select

async def audit_admins():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.role == "admin"))
        admins = res.scalars().all()
        print(f"--- Audit: {len(admins)} Admin(s) Found ---")
        for admin in admins:
            print(f"ID: {admin.id} | Email: {admin.email} | Active: {admin.is_active}")
            # Note: We don't print the hash, but we know it's there.

if __name__ == "__main__":
    asyncio.run(audit_admins())
