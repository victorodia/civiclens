import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User, PollingUnit
from sqlalchemy import select

async def check_agent_pu():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == "victor.odia14@gmail.com"))
        u = res.scalars().first()
        if u:
            print(f"Agent: {u.email} | PU ID: {u.assigned_pu_id}")
            if u.assigned_pu_id:
                pu_res = await db.execute(select(PollingUnit).where(PollingUnit.id == u.assigned_pu_id))
                pu = pu_res.scalars().first()
                if pu:
                    print(f"PU Name: {pu.name} | PU Code: {pu.pu_code}")
                else:
                    print("PU not found in database.")
            else:
                print("No PU assigned to this agent.")
        else:
            print("Agent not found.")

if __name__ == "__main__":
    asyncio.run(check_agent_pu())
