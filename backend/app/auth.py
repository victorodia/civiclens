from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .db import get_db
from .security import check_login_attempt, create_access_token, check_rate_limit
# from .models import User  # We would import this in a finalized system

router = APIRouter(prefix="/auth", tags=["Authentication"])

from pydantic import BaseModel

class LoginSchema(BaseModel):
    email: str
    password: str
    device_fingerprint: Optional[str] = None
    mfa_token: Optional[str] = None

@router.post("/login")
async def login(
    payload: LoginSchema,
    db: AsyncSession = Depends(get_db)
):
    email = payload.email
    password = payload.password
    device_fingerprint = payload.device_fingerprint
    """
    Highly secure login endpoint. 
    """
    # 0. Anti-Brute Force Protection
    client_ip = email # Use email as a proxy for rate limiting buckets in MVP
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. High-security lockout active for 60 seconds."
        )
    
    # 1. Database Lookup (with geographic hierarchy join)
    from sqlalchemy import select
    from sqlalchemy import func
    from .models import User, PollingUnit, Ward, LGA, State
    
    stmt = select(User, PollingUnit, Ward, LGA, State).join(
        PollingUnit, User.assigned_pu_id == PollingUnit.id, isouter=True
    ).join(
        Ward, PollingUnit.ward_id == Ward.id, isouter=True
    ).join(
        LGA, Ward.lga_id == LGA.id, isouter=True
    ).join(
        State, LGA.state_id == State.id, isouter=True
    ).filter(func.lower(User.email) == func.lower(email))

    res = await db.execute(stmt)
    row = res.first()
    
    if not row:
         print("[DEBUG AUTH] Row not found for email:", email)
         raise HTTPException(status_code=401, detail="Invalid credentials")

    user, pu, ward, lga, state = row
    print("[DEBUG AUTH] Found user:", user.email, "hashed_pwd:", user.hashed_password)
    print("[DEBUG AUTH] Input password:", password)

    # 2. Device Fingerprinting Challenge
    if user.device_fingerprint and device_fingerprint != user.device_fingerprint:
        print("[DEBUG AUTH] Device mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Unrecognized Device."
        )

    # 3. Password Validation
    is_authenticated, is_under_duress = check_login_attempt(
        password, 
        user.hashed_password, 
        user.hashed_duress_password
    )
    print("[DEBUG AUTH] is_authenticated:", is_authenticated)
    
    if not is_authenticated:
        print("[DEBUG AUTH] check_login_attempt failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3.5 MFA Challenge (TOTP)
    if user.is_2fa_enabled:
        if not payload.mfa_token:
            return {
                "access_token": None,
                "requires_mfa": True,
                "message": "Multi-Factor Authentication required."
            }
        
        import pyotp
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(payload.mfa_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA token."
            )
        print(f"[SECURITY] MFA Verified for user {user.email}")

    if user.requires_password_reset:
        return {
            "access_token": None,
            "requires_password_reset": True,
            "message": "Mandatory secure password reset required."
        }

    # 4. Generating the Secure JWT (Injecting the secret distress flag if under duress)
    if is_under_duress:
         print("!!! DURESS LOGIN DETECTED - MONITORING ACTIVE !!!")

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
        is_compromised=is_under_duress
    )

    # Geographic metadata for agents
    assigned_pu = None
    if pu:
        assigned_pu = {
            "id": pu.id,
            "pu_code": pu.pu_code,
            "name": pu.name,
            "ward": ward.name if ward else "Unknown",
            "lga": lga.name if lga else "Unknown",
            "state": state.name if state else "Unknown",
            "email": user.email,
            "is_on_site": user.is_on_site
        }

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "requires_password_reset": False,
        "assigned_pu": assigned_pu,
        "notice": "Login Successful."
    }

class CheckInSchema(BaseModel):
    email: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

@router.post("/agent/check-in")
async def agent_check_in(payload: CheckInSchema, db: AsyncSession = Depends(get_db)):
    """
    Electronic Muster Roll: Agents confirm physical arrival at the PU.
    """
    from datetime import datetime
    from .models import User
    from sqlalchemy import select

    # DEBUG: Log incoming payload to trace GPS data
    print(f"[CHECK-IN] Received payload: email={payload.email}, lat={payload.latitude}, lng={payload.longitude}")
    
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    user.is_on_site = True
    user.last_check_in = datetime.utcnow()
    user.check_in_lat = payload.latitude
    user.check_in_lng = payload.longitude
    await db.commit()
    
    print(f"[CHECK-IN] Persisted: lat={user.check_in_lat}, lng={user.check_in_lng}")
    return {"status": "success", "message": "Arrival confirmed. You are now ACTIVE on the muster roll."}

class SecurityInitializationSchema(BaseModel):
    email: str
    new_password: str
    duress_password: str

@router.post("/secure-initialization")
async def finalize_security_initialization(payload: SecurityInitializationSchema, db: AsyncSession = Depends(get_db)):
    """
    Mandatory Security Initialization:
    Updates the user's primary and duress passwords, effectively expiring the temporary admin-provided credential.
    """
    from .models import User
    from .security import get_password_hash
    from sqlalchemy import select
    
    # 1. Fetch the user
    stmt = select(User).filter(User.email == payload.email)
    res = await db.execute(stmt)
    user = res.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # 2. Update credentials
    user.hashed_password = get_password_hash(payload.new_password)
    user.hashed_duress_password = get_password_hash(payload.duress_password)
    user.requires_password_reset = False
    
    await db.commit()
    
    return {
        "status": "success",
        "message": "Security credentials fully initialized. Temporary password has been expired."
    }
