import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal, engine, Base
from app.models import User
from app.security import get_password_hash

async def seed_admin():
    async with engine.begin() as conn:
        # Create all tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if admin already exists
        from sqlalchemy import select
        result = await session.execute(select(User).filter(User.email == "admin@civiclens.io"))
        existing_user = result.scalars().first()

        if existing_user:
            print("Admin user already exists.")
            return

        # Create Super-Admin
        admin = User(
            email="admin@civiclens.io",
            full_name="System Administrator",
            hashed_password=get_password_hash("SecureAdmin2026!"),
            role="admin",
            is_active=True,
            requires_password_reset=False,
            device_fingerprint="ADMIN_TRUSTED_DEVICE"
        )
        
        session.add(admin)
        await session.commit()
        print("Super-Admin user created successfully!")
        print("Email: admin@civiclens.io")
        print("Password: SecureAdmin2026!")

if __name__ == "__main__":
    asyncio.run(seed_admin())
