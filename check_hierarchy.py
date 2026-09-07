import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import PollingUnit, Ward, LGA, State
from sqlalchemy import select

async def check_hierarchy():
    async with AsyncSessionLocal() as db:
        pu_id = '1eb6ab6bd35341fc88177310722f1a91'
        print(f"Checking hierarchy for PU: {pu_id}")
        
        stmt = select(PollingUnit, Ward, LGA, State).join(
            Ward, PollingUnit.ward_id == Ward.id, isouter=True
        ).join(
            LGA, Ward.lga_id == LGA.id, isouter=True
        ).join(
            State, LGA.state_id == State.id, isouter=True
        ).where(PollingUnit.id == pu_id)
        
        res = await db.execute(stmt)
        row = res.first()
        
        if row:
            pu, ward, lga, state = row
            print(f"PU: {pu.name if pu else 'None'}")
            print(f"Ward: {ward.name if ward else 'None'}")
            print(f"LGA: {lga.name if lga else 'None'}")
            print(f"State: {state.name if state else 'None'}")
        else:
            print("Row not found for PU ID.")

if __name__ == "__main__":
    asyncio.run(check_hierarchy())
