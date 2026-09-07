import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User, PollingUnit, Ward, LGA, State, Result
from sqlalchemy import select

async def test_query():
    async with AsyncSessionLocal() as db:
        stmt = select(User, PollingUnit, Ward, LGA, State, Result).join(
            PollingUnit, User.assigned_pu_id == PollingUnit.id, isouter=True
        ).join(
            Ward, PollingUnit.ward_id == Ward.id, isouter=True
        ).join(
            LGA, Ward.lga_id == LGA.id, isouter=True
        ).join(
            State, LGA.state_id == State.id, isouter=True
        ).join(
            Result, PollingUnit.id == Result.pu_id, isouter=True
        ).where(User.role == "agent")
        
        try:
            res = await db.execute(stmt)
            rows = res.all()
            print(f"Success, found {len(rows)} rows")
            for row in rows:
                print(row)
        except Exception as e:
            print("Error executing query:")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_query())
