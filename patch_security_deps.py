import os

file_path = "/home/ubuntu/civiclens/backend/app/security.py"

with open(file_path, "r") as f:
    content = f.read()

new_deps = """
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from .db import get_db
import json

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from .models import User, CustomRole
    from sqlalchemy import select
    
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
        
    return user

class RequirePermission:
    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        from .models import CustomRole
        from sqlalchemy import select
        
        # If it's a field agent, they shouldn't even be here. (Agents use agent portal)
        if user.role == "agent":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Field agents cannot access the admin API.")
            
        # Fetch the role
        stmt = select(CustomRole).where(CustomRole.name == user.role)
        res = await db.execute(stmt)
        role = res.scalar_one_or_none()
        
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not found or unassigned.")
            
        if self.permission not in role.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permission: {self.permission}")
            
        return user
"""

if "class RequirePermission:" not in content:
    content += "\n" + new_deps
    with open(file_path, "w") as f:
        f.write(content)
    print("security.py patched with dependencies!")
else:
    print("Dependencies already exist in security.py")
