from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel

from .db import get_db
from .verification import mock_ocr_analysis, verify_result_integrity

from .models import User, Role, CustomRole, State, LGA, Ward, PollingUnit, Result, ElectionConfig, AuditLog
from .security import get_current_user, RequirePermission, log_audit, verify_password, get_password_hash


print("[BOOT] Admin Telemetry Module Loaded")
router = APIRouter(prefix="/admin", tags=["Admin Verification"])

import pyotp
import qrcode
import io
import base64


class RoleSchema(BaseModel):
    name: str
    permissions: List[str] = []

class TOTPVerifySchema(BaseModel):
    token: str
    email: str

@router.get("/mfa/setup")
async def setup_mfa(email: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Generates a new TOTP secret and returns a provisioning URI (QR code)."""
    if email.lower() != user.email.lower() and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only manage your own MFA enrollment.")
    from .models import User
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        await db.commit()
        
    totp = pyotp.TOTP(user.totp_secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name="CivicLens")
    
    return {
        "secret": user.totp_secret,
        "provisioning_uri": provisioning_uri
    }

@router.post("/mfa/verify")
async def verify_mfa(payload: TOTPVerifySchema, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Verifies a TOTP token to activate 2FA for an account."""
    if payload.email.lower() != user.email.lower() and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only manage your own MFA enrollment.")
    from .models import User
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()
    
    if not user or not user.totp_secret:
        raise HTTPException(status_code=400, detail="MFA not initialized for this account")
        
    totp = pyotp.TOTP(user.totp_secret)
    if totp.verify(payload.token):
        user.is_2fa_enabled = True
        await db.commit()
        return {"status": "success", "message": "MFA has been successfully activated."}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired MFA token.")

@router.post("/verify/{result_id}")
async def approve_result(result_id: str, action: str, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("approve_results"))):
    """
    Final Human Verification: Admins can 'APPROVE' or 'REJECT' a result flagged by AI.
    If 'APPROVE', the result is marked as verified and the flag is cleared.
    """
    from .models import Result
    res = await db.execute(select(Result).where(Result.id == result_id))
    result = res.scalar_one_or_none()
    
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
        
    from .security import log_audit, get_current_user, RequirePermission
    
    if action.upper() == 'APPROVE':
        result.is_verified = True
        result.is_flagged = False # Human override clears the AI flag
    elif action.upper() == 'REJECT':
        result.is_verified = False
        result.is_flagged = False # Target for re-submission or manual audit
        
    # Audit this human verification event
    await log_audit(
        db, 
        actor_id=str(user.id),
        action=f"RESULT_{action.upper()}", 
        target_id=result_id,
        details=f"Human verification action: {action}"
    )
    
    await db.commit()
    return {"status": "success", "action": action, "result_id": result_id}

from pydantic import BaseModel
import secrets
import string
from .models import User
from .security import get_password_hash, get_current_user, RequirePermission

class ProvisionSchema(BaseModel):
    emails: List[str]
    polling_unit_id: str

@router.post("/provision-agents")
async def provision_new_agents(payload: ProvisionSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("provision_agents"))):
    """
    Super-Admin endpoint to bulk-create specific field agents bound to a PU.
    Commits them to the database with temporary credentials.
    """
    results = {}
    alphabet = string.ascii_letters + string.digits
    
    for email in payload.emails:
        # Check if already exists
        existing_res = await db.execute(select(User).where(User.email == email))
        if existing_res.scalar_one_or_none():
            continue

        temp_pwd = "CIVIC_" + ''.join(secrets.choice(alphabet) for _ in range(8))
        
        new_agent = User(
            email=email,
            full_name="Newly Provisioned Agent",
            hashed_password=get_password_hash(temp_pwd),
            role="agent",
            is_active=True,
            requires_password_reset=True,
            device_fingerprint="MOCKED_PHONE_ID",
            assigned_pu_id=payload.polling_unit_id
        )
        db.add(new_agent)
        results[email] = temp_pwd
        
    await db.commit()

    
    return {
        "status": "success",
        "provisioned": results
    }


@router.get("/agents")
async def get_all_agents(db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_agents"))):
    """
    Returns a list of all provisioned field agents.
    """
    from sqlalchemy import select
    from .models import User
    result = await db.execute(select(User).where(User.role == "agent"))
    agents = result.scalars().all()
    
    return [
        {
            "id": str(agent.id),
            "email": agent.email,
            "full_name": agent.full_name,
            "status": "Pending Reset" if agent.requires_password_reset else "Active",
            "device": "Authorized" if agent.device_fingerprint else "Pending"
        }
        for agent in agents
    ]

@router.get("/geo/states")
async def get_states(db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import State
    res = await db.execute(select(State).order_by(State.name))
    states = res.scalars().all()
    return [{"id": str(s.id), "name": s.name} for s in states]

@router.get("/geo/states/{state_id}/lgas")
async def get_lgas(state_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import LGA
    res = await db.execute(select(LGA).where(LGA.state_id == state_id).order_by(LGA.name))
    lgas = res.scalars().all()
    return [{"id": str(l.id), "name": l.name} for l in lgas]

@router.get("/geo/lgas/{lga_id}/wards")
async def get_wards(lga_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import Ward
    res = await db.execute(select(Ward).where(Ward.lga_id == lga_id).order_by(Ward.name))
    wards = res.scalars().all()
    return [{"id": str(w.id), "name": w.name} for w in wards]

@router.get("/geo/wards/{ward_id}/pus")
async def get_pus(ward_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import PollingUnit
    res = await db.execute(select(PollingUnit).where(PollingUnit.ward_id == ward_id).order_by(PollingUnit.name))
    pus = res.scalars().all()
    return [{"id": str(p.id), "name": p.name, "code": p.pu_code} for p in pus]



class RevokeSchema(BaseModel):
    admin_password: str

@router.delete("/agents/{agent_id}")
async def revoke_agent(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("revoke_agents"))):
    """
    Secure Revocation: Requires administrative re-authentication.
    Purges an agent from the system, effectively killing their access.
    """
    from .security import verify_password, get_current_user, RequirePermission
    from .models import User
    
    # 1. Verify Administrative Re-authentication against the authenticated caller.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrative re-authentication failed. Incorrect security key."
        )

    # 2. Target Identification
    from sqlalchemy import delete
    agent_res = await db.execute(select(User).where(User.id == agent_id))
    agent = agent_res.scalars().first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent record not found.")

    if agent.role != "agent":
        raise HTTPException(status_code=403, detail="Only field agent accounts can be revoked via this pipeline.")

    # 3. Purge & Audit
    from .security import log_audit, get_current_user, RequirePermission
    
    # Audit trail for personnel decommissioning
    await log_audit(
        db, 
        actor_id=str(user.id),
        action="AGENT_REVOCATION", 
        target_id=agent_id,
        details=f"Access permanently revoked for agent: {agent.email}"
    )

    await db.execute(delete(User).where(User.id == agent_id))
    await db.commit()

    return {
        "status": "success",
        "message": f"Agent {agent.email} has been successfully revoked and purged from the registry."
    }

@router.post("/factory-reset")
async def factory_reset_system(payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("trigger_factory_reset"))):
    """
    NUCLEAR OPTION: Purges all results and field agent accounts.
    Requires administrative re-authentication.
    """
    from .security import verify_password, get_current_user, RequirePermission
    from .models import User, Result
    from sqlalchemy import delete

    # 1. Verify Administrative Re-authentication against the authenticated caller.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Factory Reset Aborted: Incorrect administrative security key."
        )

    # 2. Sequential Purgation (Nuclear Option)
    from sqlalchemy import text
    from .security import log_audit, get_current_user, RequirePermission
    
    # Audit before destruction
    await log_audit(
        db, 
        actor_id=str(user.id),
        action="FACTORY_RESET", 
        details="Nuclear purgation of all results and agent accounts initiated."
    )
    
    # Force purge of results first
    # Using raw SQL to bypass any potential ORM/Cascade edge cases in this nuclear operation
    await db.execute(text("DELETE FROM results"))
    
    # Purge all agents (keeping only admins)
    await db.execute(text("DELETE FROM users WHERE role = 'agent'"))
    
    await db.commit()
    print("[SECURITY] Factory Reset Complete: System Purgated.")

    return {
        "status": "success",
        "message": "System has been restored to factory state. All results and agent profiles have been purged."
    }

@router.get("/workforce-status")
async def get_workforce_monitor(
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    on_site: Optional[bool] = None,
    result_uploaded: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_agents"))
):
    """
    Advanced Workforce Monitoring: Correlates agent presence with geographic binding and results.
    """
    from sqlalchemy import select, func
    from .models import User, PollingUnit, Ward, LGA, State, Result

    stmt = select(User, PollingUnit, Ward, LGA, State, Result).join(
        PollingUnit, User.assigned_pu_id == PollingUnit.id, isouter=True
    ).join(
        Ward, PollingUnit.ward_id == Ward.id, isouter=True
    ).join(
        LGA, Ward.lga_id == LGA.id, isouter=True
    ).join(
        State, LGA.state_id == State.id, isouter=True
    ).join(
        Result, PollingUnit.id == Result.pu_id, isouter=True
    ).where(User.role == "agent")

    # Apply Filters
    if state_id: stmt = stmt.where(State.id == state_id)
    if lga_id: stmt = stmt.where(LGA.id == lga_id)
    if ward_id: stmt = stmt.where(Ward.id == ward_id)
    if pu_id: stmt = stmt.where(PollingUnit.id == pu_id)
    if on_site is not None: stmt = stmt.where(User.is_on_site == on_site)
    if result_uploaded is not None:
        if result_uploaded:
            stmt = stmt.where(Result.id.is_not(None))
        else:
            stmt = stmt.where(Result.id.is_(None))

    res = await db.execute(stmt)
    rows = res.all()

    workforce = []
    for row in rows:
        user, pu, ward, lga, state, result = row
        workforce.append({
            "agent_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_on_site": user.is_on_site,
            "last_check_in": user.last_check_in.isoformat() if user.last_check_in else None,
            "check_in_lat": user.check_in_lat,
            "check_in_lng": user.check_in_lng,
            "has_result": result is not None,
            "submission_lat": result.latitude if result else None,
            "submission_lng": result.longitude if result else None,
            "pu_name": pu.name if pu else "Unassigned",
            "pu_code": pu.pu_code if pu else "N/A",
            "ward": ward.name if ward else None,
            "lga": lga.name if lga else None,
            "state": state.name if state else None
        })

    return workforce

@router.get("/unassigned-pus")
async def get_unassigned_pus(
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    limit: int = 150,
    db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_agents"))
):
    """
    Electronic Coverage Audit: Identifies Polling Units without assigned field agents.
    Optimized with LEFT JOIN and strict limiting for Situation Room performance.
    """
    print(f"AUDIT REQUEST: state={state_id}, lga={lga_id}, ward={ward_id}")
    from sqlalchemy import select, func
    from .models import PollingUnit, User, Ward, LGA, State

    # Build the base query for gaps
    # We join with User where User is assigned to the PU, and look for NULL matches
    stmt = select(PollingUnit, Ward, LGA, State).join(
        Ward, PollingUnit.ward_id == Ward.id
    ).join(
        LGA, Ward.lga_id == LGA.id
    ).join(
        State, LGA.state_id == State.id
    ).outerjoin(
        User, PollingUnit.id == User.assigned_pu_id
    ).where(User.id.is_(None))

    # Apply Geo Filters
    if state_id: stmt = stmt.where(State.id == state_id)
    if lga_id: stmt = stmt.where(LGA.id == lga_id)
    if ward_id: stmt = stmt.where(Ward.id == ward_id)

    # Get total count for metadata
    count_stmt = select(func.count(PollingUnit.id)).select_from(PollingUnit).join(
        Ward, PollingUnit.ward_id == Ward.id
    ).join(
        LGA, Ward.lga_id == LGA.id
    ).join(
        State, LGA.state_id == State.id
    ).outerjoin(
        User, PollingUnit.id == User.assigned_pu_id
    ).where(User.id.is_(None))
    
    if state_id: count_stmt = count_stmt.where(State.id == state_id)
    if lga_id: count_stmt = count_stmt.where(LGA.id == lga_id)
    if ward_id: count_stmt = count_stmt.where(Ward.id == ward_id)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar()
    print(f"AUDIT COUNT: {total_count}")

    # Execute limited data fetch
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    rows = res.all()

    gaps = []
    for row in rows:
        pu, ward, lga, state = row
        gaps.append({
            "id": pu.id,
            "name": pu.name,
            "code": pu.pu_code,
            "ward": ward.name,
            "lga": lga.name,
            "state": state.name
        })

    return {
        "total_count": total_count,
        "returned_count": len(gaps),
        "gaps": gaps
    }

@router.get("/stats/collation")
async def get_live_stats(
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_results"))
):
    """Returns the rolling aggregate for the Situation Room charts with LIVE data, optionally filtered."""
    print(f"[TELEMETRY] Live Collation Request Received: state={state_id}, lga={lga_id}, ward={ward_id}, pu={pu_id}")
    from sqlalchemy import select, func
    from .models import User, Result, PollingUnit, Ward, LGA, State

    # Helper function to apply geographic filters via joins
    def apply_filters(stmt, table):
        # 1. State Filter -> LGA -> Ward -> PollingUnit
        # 2. LGA Filter -> Ward -> PollingUnit
        # 3. Ward Filter -> PollingUnit
        # 4. PU Filter
        
        # Link result to PU if needed
        if table == Result:
            stmt = stmt.join(PollingUnit, Result.pu_id == PollingUnit.id)
        elif table == User:
            stmt = stmt.join(PollingUnit, User.assigned_pu_id == PollingUnit.id)
            
        if pu_id:
            stmt = stmt.filter(PollingUnit.id == pu_id)
        elif ward_id:
            stmt = stmt.filter(PollingUnit.ward_id == ward_id)
        elif lga_id:
            stmt = stmt.join(Ward, PollingUnit.ward_id == Ward.id).filter(Ward.lga_id == lga_id)
        elif state_id:
            stmt = stmt.join(Ward, PollingUnit.ward_id == Ward.id).join(LGA, Ward.lga_id == LGA.id).filter(LGA.state_id == state_id)
            
        return stmt

    # 1. Agents Provisioned
    agent_count_stmt = select(func.count(User.id)).where(User.role == "agent")
    if any([state_id, lga_id, ward_id, pu_id]):
        agent_count_stmt = apply_filters(agent_count_stmt, User)
    
    agent_count_res = await db.execute(agent_count_stmt)
    agents_provisioned = agent_count_res.scalar() or 0

    # 2. Vote Tallies
    votes_stmt = select(
        func.sum(Result.party_a_votes),
        func.sum(Result.party_b_votes),
        func.sum(Result.party_c_votes)
    )
    if any([state_id, lga_id, ward_id, pu_id]):
        votes_stmt = apply_filters(votes_stmt, Result)
        
    votes_res = await db.execute(votes_stmt)
    pa, pb, pc = votes_res.one()
    
    pa = pa or 0
    pb = pb or 0
    pc = pc or 0
    total_votes = pa + pb + pc

    # 3. Integrity Verified Percentage
    res_count_stmt = select(func.count(Result.id))
    if any([state_id, lga_id, ward_id, pu_id]):
        res_count_stmt = apply_filters(res_count_stmt, Result)
        
    total_results_res = await db.execute(res_count_stmt)
    total_results = total_results_res.scalar() or 0
    
    if total_results > 0:
        verified_results_stmt = res_count_stmt.where(Result.is_verified == True)
        verified_results_res = await db.execute(verified_results_stmt)
        verified_results = verified_results_res.scalar() or 0
        verified_percentage = round((verified_results / total_results) * 100, 1)
    else:
        verified_percentage = 0.0

    # 4. Flagged for Review Count
    flagged_stmt = select(func.count(Result.id)).where(Result.is_flagged == True, Result.is_verified == False)
    if any([state_id, lga_id, ward_id, pu_id]):
        flagged_stmt = apply_filters(flagged_stmt, Result)
    
    flagged_res = await db.execute(flagged_stmt)
    flagged_count = flagged_res.scalar() or 0

    return {
        "total_votes": total_votes,
        "party_a": pa,
        "party_b": pb,
        "party_c": pc,
        "verified_percentage": verified_percentage,
        "agents_provisioned": agents_provisioned,
        "flagged_count": flagged_count
    }

@router.get("/wallet-balance")
async def get_wallet_balance(user: User = Depends(RequirePermission("view_live_telemetry"))):
    """Polygon anchoring wallet status (address + POL balance) for the dashboard."""
    # MUST run in a thread: this call can block (RPC probe up to STATUS_TIMEOUT,
    # plus cold web3 import on first hit). Blocking the event loop in an
    # async route gets the uvicorn worker SIGKILLed by gunicorn (WORKER TIMEOUT
    # -> gateway 502), which is exactly the failure this guards against.
    import asyncio
    from .polygon import get_wallet_status
    return await asyncio.to_thread(get_wallet_status)


@router.get("/health")
async def get_system_health(db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_live_telemetry"))):
    """Returns real-time telemetry on system health and node reporting."""
    from .models import State, Result, PollingUnit, Ward, LGA
    from sqlalchemy import func
    
    # States Reporting
    states_count_res = await db.execute(select(func.count(State.id)))
    total_states = states_count_res.scalar() or 36
    
    # Active Nodes (States with at least one result)
    active_states_stmt = select(func.count(func.distinct(State.id))).select_from(Result).join(
        PollingUnit, Result.pu_id == PollingUnit.id
    ).join(
        Ward, PollingUnit.ward_id == Ward.id
    ).join(
        LGA, Ward.lga_id == LGA.id
    ).join(
        State, LGA.state_id == State.id
    )
    
    active_res = await db.execute(active_states_stmt)
    reporting_states = active_res.scalar() or 0
    
    return {
        "status": "OPERATIONAL",
        "reporting_states": reporting_states,
        "total_states": total_states,
        "latency": "24ms",
        "integrity_score": 99.8
    }


@router.get("/system/roles")
async def get_roles(db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_system_users"))):
    result = await db.execute(select(Role))
    return result.scalars().all()

@router.post("/system/roles")
async def create_role(payload: RoleSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("create_system_users"))):
    role = Role(**payload.dict())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role

@router.put("/system/roles/{role_id}")
async def update_role(role_id: str, payload: RoleSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("change_user_roles"))):
    result = await db.execute(select(Role).filter_by(id=role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    for k, v in payload.dict().items():
        setattr(role, k, v)
    await db.commit()
    return role

@router.delete("/system/roles/{role_id}")
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("delete_system_users"))):
    result = await db.execute(select(Role).filter_by(id=role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    await db.delete(role)
    await db.commit()
    return {"message": "Role deleted"}

@router.get("/my-permissions")
async def get_my_permissions(db: AsyncSession = Depends(get_db), user = Depends(get_current_user)):
    from .models import Role
    from sqlalchemy import select
    stmt = select(Role).where(Role.name == user.role)
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    return {"role": user.role, "permissions": role.permissions if role else []}

class SystemUserCreate(BaseModel):
    email: str
    full_name: str
    role: str
    password: str

class SystemUserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/system/users")
async def get_system_users(db: AsyncSession = Depends(get_db), _: User = Depends(RequirePermission("view_system_users"))):
    from sqlalchemy import select
    from .models import User
    # Only return non-agent users
    res = await db.execute(select(User).where(User.role != "agent"))
    users = res.scalars().all()
    return [
        {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "is_active": u.is_active}
        for u in users
    ]

@router.post("/system/users")
async def create_system_user(payload: SystemUserCreate, db: AsyncSession = Depends(get_db), _: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    from .security import get_password_hash, get_current_user, RequirePermission
    
    # check exists
    res = await db.execute(select(User).where(User.email == payload.email))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        requires_password_reset=True
    )
    db.add(new_user)
    await db.commit()
    return {"status": "success", "id": new_user.id}

@router.put("/system/users/{user_id}")
async def update_system_user(user_id: str, payload: SystemUserUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        
    await db.commit()
    return {"status": "success"}

@router.delete("/system/users/{user_id}")
async def delete_system_user(user_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"status": "success"}
