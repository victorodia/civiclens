import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User, PollingUnit
from app.security import get_password_hash
from sqlalchemy import select

async def seed_user():
    async with AsyncSessionLocal() as db:
        pu_res = await db.execute(select(PollingUnit))
        pu = pu_res.scalars().first()
        if not pu:
            print("No polling unit found!")
            return
            
        print(f"Assigning user to PU: {pu.id}")
        
        email = "victor.odia14@gmail.com"
        pwd = "password123"
        hashed = get_password_hash(pwd)
        
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalars().first():
            print("User already exists!")
            return
            
        new_agent = User(
            email=email,
            full_name="Victor Odia",
            hashed_password=hashed,
            hashed_duress_password=get_password_hash("duress123"),
            role="agent",
            is_active=True,
            requires_password_reset=False,
            device_fingerprint="MOCKED_PHONE_ID",
            assigned_pu_id=pu.id
        )
        db.add(new_agent)
        await db.commit()
        print("Agent added!")

if __name__ == "__main__":
    asyncio.run(seed_user())
