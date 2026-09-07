import asyncio
from app.db import AsyncSessionLocal
from app.models import PollingUnit, User, Ward, LGA, State
from sqlalchemy import select, func

async def test_audit():
    async with AsyncSessionLocal() as db:
        # Test 1: Total PUs
        tot_pu = await db.execute(select(func.count(PollingUnit.id)))
        print(f"Total PUs in DB: {tot_pu.scalar()}")

        # Test 2: Unassigned PUs with LEFT JOIN
        stmt = select(func.count(PollingUnit.id)).select_from(PollingUnit).join(
            Ward, PollingUnit.ward_id == Ward.id
        ).join(
            LGA, Ward.lga_id == LGA.id
        ).join(
            State, LGA.state_id == State.id
        ).outerjoin(
            User, PollingUnit.id == User.assigned_pu_id
        ).where(User.id.is_(None))
        
        res = await db.execute(stmt)
        print(f"Unassigned PUs (Alchemy): {res.scalar()}")

        # Test 3: Check for ABUJA
        abuja_stmt = stmt.where(State.name == "ABUJA")
        res_abuja = await db.execute(abuja_stmt)
        print(f"Unassigned PUs in ABUJA (Alchemy): {res_abuja.scalar()}")

if __name__ == "__main__":
    asyncio.run(test_audit())
