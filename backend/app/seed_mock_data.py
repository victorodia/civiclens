import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal, engine
from app.models import State, LGA, Ward, PollingUnit, Result, User
from datetime import datetime

async def seed_data():
    async with AsyncSessionLocal() as session:
        # Check if already seeded to prevent unique constraint errors
        from sqlalchemy import select
        existing_states = await session.execute(select(State).where(State.code == "LA"))
        if existing_states.scalar_one_or_none():
            print("Database already seeded. Skipping initial geometry.")
        else:
            # 1. States
            lagos = State(id=uuid.uuid4(), name="Lagos", code="LA")
            kano = State(id=uuid.uuid4(), name="Kano", code="KN")
            session.add_all([lagos, kano])
            await session.flush()

            # 2. LGAs
            ikeja = LGA(id=uuid.uuid4(), name="Ikeja", state_id=lagos.id)
            dala = LGA(id=uuid.uuid4(), name="Dala", state_id=kano.id)
            session.add_all([ikeja, dala])
            await session.flush()

            # 3. Wards
            ward_a = Ward(id=uuid.uuid4(), name="Ikeja Ward 1", lga_id=ikeja.id)
            session.add_all([ward_a])
            await session.flush()

            # 4. Polling Units
            pu1 = PollingUnit(
                id=uuid.uuid4(), 
                pu_code="01-01-01-001", 
                name="Ikeja Primary School", 
                ward_id=ward_a.id
            )
            session.add(pu1)
            await session.flush()

        # Always ensure the Test Agent exists and requires reset
        existing_agent = await session.execute(select(User).where(User.email == "agent_test@civiclens.io"))
        agent = existing_agent.scalar_one_or_none()
        
        if not agent:
            # Need a PU to link to
            res_pu = await session.execute(select(PollingUnit).limit(1))
            pu = res_pu.scalar_one()
            agent = User(
                email="agent_test@civiclens.io",
                full_name="Test Field Agent",
                hashed_password="mock_hash",
                role="agent",
                is_active=True,
                device_fingerprint="MOCKED_PHONE_ID",
                assigned_pu_id=pu.id,
                requires_password_reset=True
            )
            session.add(agent)
        else:
            agent.requires_password_reset = True
        
        await session.commit()
        print("Demo data seeded/updated successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
