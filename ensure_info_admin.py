import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from app.security import get_password_hash
from sqlalchemy import select

async def ensure_admin():
    async with AsyncSessionLocal() as db:
        # Check for info@ account
        res = await db.execute(select(User).where(User.email == "info@civiclens.io"))
        info_user = res.scalars().first()
        
        if info_user:
            print("Found info@ account. Updating role and password...")
            info_user.role = "admin"
            info_user.hashed_password = get_password_hash("admin123")
        else:
            print("Creating info@civiclens.io admin account...")
            info_user = User(
                email="info@civiclens.io",
                full_name="Principal Administrator",
                hashed_password=get_password_hash("admin123"),
                role="admin",
                is_active=True,
                requires_password_reset=False
            )
            db.add(info_user)
            
        await db.commit()
        print("Admin user info@civiclens.io is now ACTIVE with password 'admin123'.")

if __name__ == "__main__":
    asyncio.run(ensure_admin())
