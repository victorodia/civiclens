import json
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.db import AsyncSessionLocal, engine
from app.models import State, LGA, Ward, PollingUnit

async def seed_geography():
    async with AsyncSessionLocal() as db:
        print("Cleaning old geography...")
        # Clean up existing geography to prevent duplicates
        await db.execute(delete(PollingUnit))
        await db.execute(delete(Ward))
        await db.execute(delete(LGA))
        await db.execute(delete(State))
        await db.commit()

        path = "backend/app/inec_data_subset.json"
        if not os.path.exists(path):
            print(f"Error: {path} not found.")
            return

        with open(path, "r") as f:
            data = json.load(f)

        print(f"Seeding {len(data)} states...")
        
        for state_data in data:
            state_name = state_data["state"].upper()
            state = State(id=uuid.uuid4(), name=state_name, code=state_name[:3])
            db.add(state)
            
            for lga_idx, lga_data in enumerate(state_data.get("lgas", [])):
                lga_name = lga_data["lga"].upper()
                lga = LGA(id=uuid.uuid4(), name=lga_name, state_id=state.id)
                db.add(lga)
                
                for ward_idx, ward_data in enumerate(lga_data.get("wards", [])):
                    ward_name = ward_data["ward"].upper()
                    ward = Ward(id=uuid.uuid4(), name=ward_name, lga_id=lga.id)
                    db.add(ward)
                    
                    for pu_idx, pu_name in enumerate(ward_data.get("polling_units", [])):
                        # Generate a mock INEC code for demo if not present
                        # format: StateCode-LGACode-WardCode-PUID
                        pu_code = f"{state.code}-{lga_idx:02d}-{ward_idx:02d}-{pu_idx:03d}"
                        pu = PollingUnit(
                            id=uuid.uuid4(),
                            pu_code=pu_code,
                            name=pu_name.upper(),
                            ward_id=ward.id
                        )
                        db.add(pu)
            
            # Commit periodically for memory efficiency if needed, or at end
            print(f"Added {state_name}")

        await db.commit()
        print("Real geography seeding complete!")

if __name__ == "__main__":
    import os
    import sys
    # Ensure app is in path
    sys.path.append(os.path.join(os.getcwd(), "backend"))
    asyncio.run(seed_geography())
