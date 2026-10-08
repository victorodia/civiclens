import os
import re

file_path = "/home/ubuntu/civiclens/backend/app/admin.py"

with open(file_path, "r") as f:
    content = f.read()

if "RequirePermission" not in content:
    content = content.replace("from .security import", "from .security import RequirePermission, ")
    if "RequirePermission" not in content:
         content = content.replace("from .db import get_db", "from .db import get_db\nfrom .security import RequirePermission")

    # Map endpoints to permissions
    replacements = [
        (r'async def setup_mfa\(email: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def setup_mfa(email: str, db: AsyncSession = Depends(get_db)): # bypass'),
         
        (r'async def verify_mfa\(payload: TOTPVerifySchema, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def verify_mfa(payload: TOTPVerifySchema, db: AsyncSession = Depends(get_db)): # bypass'),
         
        (r'async def approve_result\(result_id: str, action: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def approve_result(result_id: str, action: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("approve_results"))):'),
         
        (r'async def provision_new_agents\(payload: ProvisionSchema, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def provision_new_agents(payload: ProvisionSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("provision_agents"))):'),
         
        (r'async def get_all_agents\(db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_all_agents(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_agents"))):'),
         
        (r'async def get_states\(db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_states(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_geographic_data"))):'),
         
        (r'async def get_lgas\(state_id: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_lgas(state_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_geographic_data"))):'),
         
        (r'async def get_wards\(lga_id: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_wards(lga_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_geographic_data"))):'),
         
        (r'async def get_pus\(ward_id: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_pus(ward_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_geographic_data"))):'),
         
        (r'async def revoke_agent\(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def revoke_agent(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("revoke_agents"))):'),
         
        (r'async def factory_reset_system\(payload: RevokeSchema, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def factory_reset_system(payload: RevokeSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("trigger_factory_reset"))):'),
         
        (r'async def get_system_health\(db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_system_health(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_live_telemetry"))):'),
         
        (r'async def get_all_documents\(db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_all_documents(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_results"))):'),
         
        (r'async def get_system_users\(db: AsyncSession = Depends\(get_db\)\):', 
         r'async def get_system_users(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_system_users"))):'),
         
        (r'async def create_system_user\(user: UserCreate, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def create_system_user(user: UserCreate, db: AsyncSession = Depends(get_db), auth_user = Depends(RequirePermission("create_system_users"))):'),
         
        (r'async def update_system_user\(user_id: str, payload: UserUpdate, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def update_system_user(user_id: str, payload: UserUpdate, db: AsyncSession = Depends(get_db), auth_user = Depends(RequirePermission("change_user_roles"))):'),
         
        (r'async def delete_system_user\(user_id: str, db: AsyncSession = Depends\(get_db\)\):', 
         r'async def delete_system_user(user_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("delete_system_users"))):')
    ]

    for old, new in replacements:
        content = re.sub(old, new, content)
        
    # Now let's inject the endpoint to manage custom roles!
    roles_endpoints = """
from pydantic import BaseModel
class RoleSchema(BaseModel):
    name: str
    permissions: list[str]

@router.get("/system/roles")
async def get_roles(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_system_users"))):
    from .models import CustomRole
    from sqlalchemy import select
    res = await db.execute(select(CustomRole))
    return res.scalars().all()

@router.post("/system/roles")
async def create_role(payload: RoleSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("create_system_users"))):
    from .models import CustomRole
    new_role = CustomRole(name=payload.name, permissions=payload.permissions)
    db.add(new_role)
    await db.commit()
    return {"status": "success"}
    
@router.patch("/system/roles/{role_id}")
async def update_role(role_id: str, payload: RoleSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("change_user_roles"))):
    from .models import CustomRole
    from sqlalchemy import select
    res = await db.execute(select(CustomRole).where(CustomRole.id == role_id))
    role = res.scalar_one_or_none()
    if role:
        role.name = payload.name
        role.permissions = payload.permissions
        await db.commit()
    return {"status": "success"}

@router.delete("/system/roles/{role_id}")
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("delete_system_users"))):
    from .models import CustomRole
    from sqlalchemy import select
    res = await db.execute(select(CustomRole).where(CustomRole.id == role_id))
    role = res.scalar_one_or_none()
    if role:
        await db.delete(role)
        await db.commit()
    return {"status": "success"}
"""
    content += roles_endpoints

    with open(file_path, "w") as f:
        f.write(content)
    print("admin.py patched successfully with RBAC dependencies!")
else:
    print("admin.py already has RequirePermission!")
