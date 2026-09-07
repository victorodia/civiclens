import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db import AsyncSessionLocal
from app.models import State, PollingUnit
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        res_states = await db.execute(select(State))
        states = res_states.scalars().all()
        print(f"FOUND {len(states)} STATES")
        for s in states:
            print(f"- {s.name}")
            
        res_pus = await db.execute(select(PollingUnit))
        pus = res_pus.scalars().all()
        print(f"FOUND {len(pus)} POLLING UNITS")

if __name__ == "__main__":
    asyncio.run(check())
