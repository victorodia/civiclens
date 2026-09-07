import asyncio
import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.db import AsyncSessionLocal
from app.models import User
from app.security import get_password_hash
from sqlalchemy import select

async def reset_admin():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.role == "admin"))
        admin = res.scalars().first()
        if admin:
            print(f"Resetting password for admin: {admin.email}")
            admin.hashed_password = get_password_hash("admin123")
            await db.commit()
            print("Password reset to 'admin123'")
        else:
            print("No admin user found. Creating one...")
            admin = User(
                email="admin@civiclens.io",
                full_name="System Administrator",
                hashed_password=get_password_hash("admin123"),
                role="admin",
                is_active=True,
                requires_password_reset=False
            )
            db.add(admin)
            await db.commit()
            print("Admin 'admin@civiclens.io' created with password 'admin123'")

if __name__ == "__main__":
    asyncio.run(reset_admin())
