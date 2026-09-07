import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User, PollingUnit, Ward, LGA, State
from sqlalchemy import select, func
from app.security import verify_password, check_login_attempt

async def test():
    db = AsyncSessionLocal()
    stmt = select(User, PollingUnit, Ward, LGA, State).join(
        PollingUnit, User.assigned_pu_id == PollingUnit.id, isouter=True
    ).join(
        Ward, PollingUnit.ward_id == Ward.id, isouter=True
    ).join(
        LGA, Ward.lga_id == LGA.id, isouter=True
    ).join(
        State, LGA.state_id == State.id, isouter=True
    ).filter(func.lower(User.email) == func.lower('info@civiclens.io'))
    
    res = await db.execute(stmt)
    row = res.first()
    
    print('Row found:', row is not None)
    if row:
        user = row[0]
        print('User:', user.email, 'hashed_pwd:', user.hashed_password)
        is_authenticated, is_under_duress = check_login_attempt(
            'admin123', 
            user.hashed_password, 
            user.hashed_duress_password
        )
        print('Password match:', is_authenticated)
    await db.close()

if __name__ == '__main__':
    asyncio.run(test())
