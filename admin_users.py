from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel
import uuid
import argon2

from .db import get_db
from .models import User

router = APIRouter(prefix="/system/users", tags=["System Users"])
ph = argon2.PasswordHasher()

class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str
    role: str

class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("")
async def get_system_users(db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.role != 'agent')
    res = await db.execute(stmt)
    users = res.scalars().all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_check_in": u.last_check_in.isoformat() if u.last_check_in else None,
            "is_2fa_enabled": u.is_2fa_enabled
        }
        for u in users
    ]

@router.post("")
async def create_system_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == user.email))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed = ph.hash(user.password)
    new_user = User(
        id=str(uuid.uuid4()),
        full_name=user.full_name,
        email=user.email,
        hashed_password=hashed,
        role=user.role,
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    return {"status": "success", "id": new_user.id}

@router.patch("/{user_id}")
async def update_system_user(user_id: str, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        
    await db.commit()
    return {"status": "success"}

@router.delete("/{user_id}")
async def delete_system_user(user_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await db.delete(user)
    await db.commit()
    return {"status": "success"}
