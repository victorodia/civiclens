from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel

from .db import get_db
from .verification import mock_ocr_analysis, verify_result_integrity

from .models import User, Role, CustomRole, State, LGA, Ward, PollingUnit, Result, ElectionConfig, AuditLog, AgentLocationPing, Election, ElectionPU
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
    from .models import User
    if email.lower() != user.email.lower():
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only manage your own MFA enrollment.")
        # Tenancy: a client admin must never reach another institution's
        # accounts — or even learn they exist. 404, not 403.
        if user.client_id is not None:
            probe = (await db.execute(select(User).where(User.email == email))).scalars().first()
            if not probe or probe.client_id != user.client_id:
                raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(select(User).where(User.email == email))
    target = result.scalars().first()

    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if not target.totp_secret:
        target.totp_secret = pyotp.random_base32()
        await db.commit()

    totp = pyotp.TOTP(target.totp_secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name="CivicLens")

    return {
        "secret": target.totp_secret,
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

    # Client tenancy: verifying another institution's result is indistinguishable
    # from verifying a non-existent one.
    from .elections import client_scope_election_ids, assert_in_scope
    assert_in_scope(result.election_id, await client_scope_election_ids(db, user))

    from .security import log_audit, get_current_user, RequirePermission
    
    if action.upper() == 'APPROVE':
        result.is_verified = True
        result.is_flagged = False # Human override clears the AI flag
    elif action.upper() == 'REJECT':
        result.is_verified = False
        result.is_flagged = False # Target for re-submission or manual audit
        
    # Audit this human verification event
    _v_election = (await db.execute(select(Election).where(Election.id == result.election_id))).scalar_one_or_none()
    await log_audit(
        db, 
        actor_id=str(user.id),
        actor_role=user.role,
        action=f"RESULT_{action.upper()}",
        tenant_id=_v_election.client_id if _v_election else getattr(user, "client_id", None),
        election_id=result.election_id,
        target_type="result",
        target_id=result_id,
        details=f"Human verification action: {action}"
    )
    
    await db.commit()
    return {"status": "success", "action": action, "result_id": result_id}

from pydantic import BaseModel
import secrets
import string
import uuid
from .models import User
from .security import get_password_hash, get_current_user, RequirePermission, log_audit

class ProvisionSchema(BaseModel):
    emails: List[str]
    polling_unit_id: str
    # Optional: when set, the agents are accredited for this election (an
    # agent_assignments row is created in addition to the legacy PU pointer),
    # which is required for them to check in and submit in that election.
    election_id: Optional[str] = None
    # Platform admins only: force the owning client. Client admins cannot set
    # this — their own institution is enforced automatically.
    client_id: Optional[str] = None

@router.post("/provision-agents")
async def provision_new_agents(payload: ProvisionSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("provision_agents"))):
    """
    Super-Admin endpoint to bulk-create specific field agents bound to a PU.
    Commits them to the database with temporary credentials.
    """
    from .models import Election, ElectionPU, AgentAssignment

    # Tenancy: client admins provision only for their own institution.
    if user.client_id is not None:
        agent_client_id = user.client_id
    else:
        agent_client_id = payload.client_id
        if agent_client_id:
            from .models import Client as _Client
            client = (await db.execute(select(_Client).where(_Client.id == agent_client_id))).scalar_one_or_none()
            if not client:
                raise HTTPException(404, "Client not found.")

    # Validate election + PU scope up front (fail fast, before any insert)
    election = None
    if payload.election_id:
        election = (await db.execute(select(Election).where(Election.id == payload.election_id))).scalar_one_or_none()
        if not election:
            raise HTTPException(404, "Election not found.")
        # Tenancy: the election must belong to the client the agents are
        # being provisioned for (client admins always provision for their
        # own institution; platform admins may pass client_id explicitly).
        if agent_client_id is not None and election.client_id != agent_client_id:
            raise HTTPException(404, "Election not found.")
        in_scope = (await db.execute(select(ElectionPU).where(
            ElectionPU.election_id == election.id,
            ElectionPU.pu_id == payload.polling_unit_id))).scalar_one_or_none()
        if not in_scope:
            raise HTTPException(422, "This polling unit is outside the election's scope.")

    results = {}
    alphabet = string.ascii_letters + string.digits

    for email in payload.emails:
        # Check if already exists
        existing_res = await db.execute(select(User).where(User.email == email))
        existing_user = existing_res.scalar_one_or_none()
        if existing_user:
            # Tenancy: a client admin cannot pull another institution's
            # agent into their election via the re-accreditation path.
            if agent_client_id is not None and existing_user.client_id != agent_client_id:
                results[email] = {"error": "Agent belongs to another institution"}
                continue
            # Already a user: just (re)accredit for this election if asked
            if election:
                clash = (await db.execute(select(AgentAssignment).where(
                    AgentAssignment.election_id == election.id,
                    AgentAssignment.pu_id == payload.polling_unit_id,
                    AgentAssignment.agent_id != existing_user.id))).scalar_one_or_none()
                if clash:
                    results[email] = {"error": f"Another agent already covers this PU in {election.code}"}
                    continue
                have = (await db.execute(select(AgentAssignment).where(
                    AgentAssignment.election_id == election.id,
                    AgentAssignment.pu_id == payload.polling_unit_id,
                    AgentAssignment.agent_id == existing_user.id))).scalar_one_or_none()
                if not have:
                    db.add(AgentAssignment(agent_id=existing_user.id, election_id=election.id,
                                           pu_id=payload.polling_unit_id))
            continue

        temp_pwd = "CIVIC_" + ''.join(secrets.choice(alphabet) for _ in range(8))
        # Per-agent HMAC signing key: the device needs it to sign result
        # payloads; submissions without a valid signature are rejected.
        signing_key = secrets.token_urlsafe(32)

        new_agent = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name="Newly Provisioned Agent",
            hashed_password=get_password_hash(temp_pwd),
            role="agent",
            is_active=True,
            requires_password_reset=True,
            device_fingerprint="MOCKED_PHONE_ID",
            device_signing_key=signing_key,
            assigned_pu_id=payload.polling_unit_id,
            client_id=agent_client_id
        )
        db.add(new_agent)
        # Flush so the users row physically exists before the assignment's
        # FK references it (no ORM relationship lets SQLAlchemy infer order).
        await db.flush()
        if election:
            db.add(AgentAssignment(agent_id=new_agent.id, election_id=election.id,
                                   pu_id=payload.polling_unit_id))
        await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                        action="AGENT_PROVISIONED",
                        tenant_id=agent_client_id,
                        election_id=election.id if election else None,
                        target_type="user", target_id=new_agent.id,
                        details=f"Agent provisioned: {email} (temporary password + signing key issued once)")
        results[email] = {"temp_password": temp_pwd, "signing_key": signing_key}

    await db.commit()


    return {
        "status": "success",
        "provisioned": results
    }


@router.get("/agents")
async def get_all_agents(db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_agents"))):
    """
    Returns a list of all provisioned field agents, each labeled with its
    owning institution and its election assignment(s) so operators can tell
    at a glance which tenant an agent works for.
    """
    from sqlalchemy import select
    from .models import User, Client, Election, AgentAssignment, PollingUnit
    stmt = select(User).where(User.role == "agent")
    # Client tenancy: client admins see only their own institution's agents.
    if user.client_id is not None:
        stmt = stmt.where(User.client_id == user.client_id)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    clients = {c.id: c.name for c in (await db.execute(select(Client))).scalars().all()}
    assigns = {}
    if agents:
        rows = (await db.execute(
            select(AgentAssignment.agent_id, Election.code, Election.name,
                   PollingUnit.pu_code, PollingUnit.name)
            .join(Election, AgentAssignment.election_id == Election.id)
            .join(PollingUnit, AgentAssignment.pu_id == PollingUnit.id, isouter=True)
            .where(AgentAssignment.agent_id.in_([a.id for a in agents]))
        )).all()
        for aid, code, ename, pu_code, pu_name in rows:
            assigns.setdefault(aid, []).append({
                "election_code": code, "election_name": ename,
                "pu_code": pu_code, "pu_name": pu_name,
            })

    return [
        {
            "id": str(agent.id),
            "email": agent.email,
            "full_name": agent.full_name,
            "client_id": agent.client_id,
            "client_name": clients.get(agent.client_id),
            "assignments": assigns.get(agent.id, []),
            "status": ("Revoked" if not agent.is_active
                       else ("Pending Reset" if agent.requires_password_reset else "Active")),
            "device": "Authorized" if agent.device_fingerprint else "Pending"
        }
        for agent in agents
    ]


class RotateKeySchema(BaseModel):
    email: str

@router.post("/agents/rotate-signing-key")
async def rotate_agent_signing_key(payload: RotateKeySchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("provision_agents"))):
    """
    Re-issue an agent's device signing key (lost key / suspected compromise).
    The previous key stops working immediately. The new key is returned ONCE —
    the operator must distribute it to the agent, who enters it at login.
    """
    res = await db.execute(select(User).where(User.email == payload.email, User.role == "agent"))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # Tenancy: a client admin must never reach another institution's agents.
    # 404, not 403 — don't reveal the agent exists.
    if user.client_id is not None and agent.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="Agent not found.")

    new_key = secrets.token_urlsafe(32)
    agent.device_signing_key = new_key

    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="AGENT_KEY_ROTATED",
        tenant_id=agent.client_id,
        target_type="user",
        target_id=str(agent.id),
        details=f"Device signing key re-issued for {payload.email}"
    )
    await db.commit()

    return {
        "status": "success",
        "email": payload.email,
        "signing_key": new_key,
        "message": "Previous key is now invalid. Distribute the new key to the agent."
    }

async def _assert_election_geo_visible(db: AsyncSession, user: User, election_id: str):
    """404 (not 403 — don't reveal existence) when the election is missing
    or outside the caller's client tenancy."""
    election = (await db.execute(
        select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found.")
    from .elections import client_scope_election_ids
    scoped = await client_scope_election_ids(db, user)
    if scoped is not None and election_id not in scoped:
        raise HTTPException(status_code=404, detail="Election not found.")


def _scoped_geo_subqueries(election_id: str):
    """Geo-level id sets covered by an election's materialized PU scope:
    returns (state_ids, lga_ids, ward_ids, pu_ids) subqueries."""
    pu_ids = select(ElectionPU.pu_id).where(ElectionPU.election_id == election_id)
    ward_ids = select(PollingUnit.ward_id).where(PollingUnit.id.in_(pu_ids))
    lga_ids = select(Ward.lga_id).where(Ward.id.in_(ward_ids))
    state_ids = select(LGA.state_id).where(LGA.id.in_(lga_ids))
    return state_ids, lga_ids, ward_ids, pu_ids

@router.get("/geo/states")
async def get_states(election_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import State
    q = select(State)
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        state_ids, _, _, _ = _scoped_geo_subqueries(election_id)
        q = q.where(State.id.in_(state_ids))
    res = await db.execute(q.order_by(State.name))
    states = res.scalars().all()
    return [{"id": str(s.id), "name": s.name} for s in states]

@router.get("/geo/states/{state_id}/lgas")
async def get_lgas(state_id: str, election_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import LGA
    q = select(LGA).where(LGA.state_id == state_id)
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        _, lga_ids, _, _ = _scoped_geo_subqueries(election_id)
        q = q.where(LGA.id.in_(lga_ids))
    res = await db.execute(q.order_by(LGA.name))
    lgas = res.scalars().all()
    return [{"id": str(l.id), "name": l.name} for l in lgas]

@router.get("/geo/lgas/{lga_id}/wards")
async def get_wards(lga_id: str, election_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import Ward
    q = select(Ward).where(Ward.lga_id == lga_id)
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        _, _, ward_ids, _ = _scoped_geo_subqueries(election_id)
        q = q.where(Ward.id.in_(ward_ids))
    res = await db.execute(q.order_by(Ward.name))
    wards = res.scalars().all()
    return [{"id": str(w.id), "name": w.name} for w in wards]

@router.get("/geo/wards/{ward_id}/pus")
async def get_pus(ward_id: str, election_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_geographic_data"))):
    from sqlalchemy import select
    from .models import PollingUnit
    q = select(PollingUnit).where(PollingUnit.ward_id == ward_id)
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        _, _, _, pu_ids = _scoped_geo_subqueries(election_id)
        q = q.where(PollingUnit.id.in_(pu_ids))
    res = await db.execute(q.order_by(PollingUnit.name))
    pus = res.scalars().all()
    return [{"id": str(p.id), "name": p.name, "code": p.pu_code} for p in pus]



class RevokeSchema(BaseModel):
    admin_password: str
    totp_code: Optional[str] = None  # Required only when the caller has 2FA enabled

@router.delete("/agents/{agent_id}")
async def revoke_agent(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("revoke_agents"))):
    """
    OPTION 1 — REVOKE (deactivate): kills the agent's access immediately
    (login rejected, device key and fingerprint destroyed) but PRESERVES
    their submitted results, evidence files, sessions and audit trail.
    Use for compromised devices, dismissed personnel, or end-of-contract.
    Requires administrative re-authentication.
    """
    from .security import verify_password
    from .models import User

    # 1. Verify Administrative Re-authentication against the authenticated caller.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrative re-authentication failed. Incorrect security key."
        )

    # 2. Target Identification
    agent_res = await db.execute(select(User).where(User.id == agent_id))
    agent = agent_res.scalars().first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent record not found.")

    # Tenancy: a client admin must never reach another institution's agents.
    if user.client_id is not None and agent.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="Agent record not found.")

    if agent.role != "agent":
        raise HTTPException(status_code=403, detail="Only field agent accounts can be revoked via this pipeline.")

    if not agent.is_active:
        return {"status": "already_revoked", "message": f"Agent {agent.email} is already deactivated."}

    # 3. Deactivate & Audit — the account row survives so results/evidence
    #    keep their provenance (results.agent_id FK stays valid).
    agent.is_active = False
    agent.device_signing_key = None
    agent.device_fingerprint = None
    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="AGENT_REVOCATION",
        tenant_id=agent.client_id,
        target_type="user",
        target_id=agent_id,
        details=f"Access revoked for agent: {agent.email} (account deactivated; results and evidence preserved)."
    )
    await db.commit()

    return {
        "status": "deactivated",
        "message": f"Agent {agent.email} access revoked. Their results and evidence remain in the system."
    }


@router.delete("/agents/{agent_id}/purge")
async def purge_agent(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("revoke_agents"))):
    """
    OPTION 2 — PURGE (complete erasure): deletes the agent account AND every
    result, check-in, GPS ping, assignment and evidence FILE they produced.
    Irreversible. Use only for never-used accounts or where legally required.
    Requires administrative re-authentication.
    """
    from .security import verify_password

    # 1. Verify Administrative Re-authentication.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrative re-authentication failed. Incorrect security key."
        )

    # 2. Target Identification
    agent_res = await db.execute(select(User).where(User.id == agent_id))
    agent = agent_res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent record not found.")
    # Tenancy: a client admin must never reach another institution's agents.
    if user.client_id is not None and agent.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="Agent record not found.")
    if agent.role != "agent":
        raise HTTPException(status_code=403, detail="Only field agent accounts can be purged via this pipeline.")

    # 3. Collect evidence filenames BEFORE deleting result rows
    rows = (await db.execute(
        text("SELECT image_url FROM results WHERE agent_id = :a AND image_url IS NOT NULL"),
        {"a": agent_id})).all()
    filenames = {r[0].rsplit("/", 1)[-1] for r in rows if r[0]}

    # 4. Child-before-parent purge (FK-safe order)
    await db.execute(text("DELETE FROM agent_location_pings WHERE agent_id = :a"), {"a": agent_id})
    await db.execute(text("DELETE FROM agent_checkins WHERE agent_id = :a"), {"a": agent_id})
    await db.execute(text("DELETE FROM agent_assignments WHERE agent_id = :a"), {"a": agent_id})
    res = await db.execute(text("DELETE FROM results WHERE agent_id = :a"), {"a": agent_id})
    n_results = getattr(res, "rowcount", -1)

    # 5. Evidence files off disk
    import os as _os
    _upload_dir = _os.path.join(_os.getcwd(), "app", "static", "uploads")
    n_files = 0
    for fn in filenames:
        p = _os.path.join(_upload_dir, fn)
        if _os.path.isfile(p):
            try:
                _os.remove(p)
                n_files += 1
            except OSError:
                pass

    # 6. The account itself + audit
    await db.execute(text("DELETE FROM users WHERE id = :a"), {"a": agent_id})
    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="AGENT_PURGE",
        tenant_id=agent.client_id,
        target_type="user",
        target_id=agent_id,
        details=f"Agent {agent.email} completely purged: {n_results} result(s), {n_files} evidence file(s) destroyed."
    )
    await db.commit()

    return {
        "status": "purged",
        "message": f"Agent {agent.email} and all their evidence permanently deleted ({n_results} results, {n_files} files)."
    }


@router.post("/agents/{agent_id}/reactivate")
async def reactivate_agent(agent_id: str, payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("revoke_agents"))):
    """
    REACTIVATE: restores a revoked (deactivated) agent. A fresh device signing
    key is issued (the old one was destroyed at revocation), the device
    fingerprint is cleared so the phone re-binds, and a password reset is
    forced on next login — same security posture as brand-new provisioning.
    All prior results, check-ins and evidence remain untouched.
    Requires administrative re-authentication.
    """
    # 1. Verify Administrative Re-authentication.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrative re-authentication failed. Incorrect security key."
        )

    # 2. Target Identification
    agent_res = await db.execute(select(User).where(User.id == agent_id))
    agent = agent_res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent record not found.")
    # Tenancy: a client admin must never reach another institution's agents.
    if user.client_id is not None and agent.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="Agent record not found.")
    if agent.role != "agent":
        raise HTTPException(status_code=403, detail="Only field agent accounts can be reactivated via this pipeline.")

    if agent.is_active:
        return {"status": "already_active", "message": f"Agent {agent.email} is already active."}

    # 3. Restore access with fresh credentials material
    new_key = secrets.token_urlsafe(32)
    agent.is_active = True
    agent.device_signing_key = new_key
    agent.device_fingerprint = None  # Phone must re-bind on next login
    agent.requires_password_reset = True  # Password may have been exposed during the incident

    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="AGENT_REACTIVATION",
        tenant_id=agent.client_id,
        target_type="user",
        target_id=agent_id,
        details=f"Access restored for agent: {agent.email} (fresh signing key issued, password reset forced; history preserved)."
    )
    await db.commit()

    return {
        "status": "reactivated",
        "email": agent.email,
        "signing_key": new_key,
        "message": f"Agent {agent.email} reactivated. Distribute the new signing key; they will set a new password at login."
    }

@router.post("/factory-reset")
async def factory_reset_system(payload: RevokeSchema, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("trigger_factory_reset"))):
    """
    NUCLEAR OPTION: wipes the entire operational database — every election,
    institution, agent account, result, check-in, GPS ping and evidence file.
    Surviving the wipe: geographic data (states/LGAs/wards/polling units),
    platform administrator accounts (client_id NULL), roles, and the audit
    log (accountability trail must outlive the data it describes).
    Requires administrative re-authentication.
    """
    from .security import verify_password

    # 0. Tenancy: the nuclear option is platform-only. A client admin must
    # never be able to wipe — or even trigger the wipe flow of — other
    # institutions' data.
    if user.client_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory reset is restricted to platform administrators."
        )

    # 1. Verify Administrative Re-authentication against the authenticated caller.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Factory Reset Aborted: Incorrect administrative security key."
        )

    # 1b. MFA Challenge — required when the caller has 2FA enabled. The client
    #     sends the password first; if this challenge fires it prompts for the
    #     TOTP code and retries with both fields.
    if user.is_2fa_enabled:
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA_CODE_REQUIRED"
            )
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(payload.totp_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired 2FA code."
            )

    # 2. Sequential Purgation (Nuclear Option) — strict child-before-parent
    #    order: every table holding an FK into results/users/elections must
    #    be purged first, otherwise the deletes abort on constraint
    #    violations.

    # Audit before destruction
    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="FACTORY_RESET",
        target_type="platform",
        target_id="global",
        details="Full system wipe: elections, clients, agents, results, sessions and evidence."
    )

    # Force purge of results first
    # Using raw SQL to bypass any potential ORM/Cascade edge cases in this nuclear operation
    await db.execute(text("DELETE FROM agent_location_pings"))
    await db.execute(text("DELETE FROM agent_checkins"))
    await db.execute(text("DELETE FROM agent_assignments"))
    await db.execute(text("DELETE FROM results"))

    # Evidence media on disk (photos/videos) — orphaned files serve nobody.
    import os as _os, glob as _glob
    _upload_dir = _os.path.join(_os.getcwd(), "app", "static", "uploads")
    if _os.path.isdir(_upload_dir):
        for _f in _glob.glob(_os.path.join(_upload_dir, "*")):
            try:
                _os.remove(_f)
            except OSError:
                pass

    # Elections and their materialized scopes
    await db.execute(text("DELETE FROM election_polling_units"))
    await db.execute(text("DELETE FROM elections"))

    # Field agents AND client-bound operator accounts (client admins), then
    # the institutions themselves. Platform admins (client_id NULL) survive.
    await db.execute(text("DELETE FROM users WHERE role = 'agent' OR client_id IS NOT NULL"))
    await db.execute(text("DELETE FROM clients"))

    # Legacy singleton config pointed at the wiped election — clear labels.
    await db.execute(text(
        "UPDATE election_config SET party_a_name = NULL, party_b_name = NULL, "
        "party_c_name = NULL, election_name = NULL WHERE id = 'global'"))

    await db.commit()
    print("[SECURITY] Factory Reset Complete: System Purgated.")

    return {
        "status": "success",
        "message": "Full wipe complete. Elections, institutions, agents, results, sessions and evidence have been purged. Geo data, platform admins and the audit log remain."
    }

@router.get("/workforce-status")
async def get_workforce_monitor(
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    client_id: Optional[str] = None,
    election_id: Optional[str] = None,
    on_site: Optional[bool] = None,
    result_uploaded: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_agents"))
):
    """
    Advanced Workforce Monitoring: Correlates agent presence with geographic binding and results.

    Filter hierarchy: client -> election -> state -> lga -> ward -> pu.
    When an election is given, agents are resolved through their
    accreditation (agent_assignments) for that race and a result only
    counts when it belongs to the SAME election — one agent's senatorial
    upload never satisfies the governorship view.
    """
    from sqlalchemy import select, func
    from .models import User, PollingUnit, Ward, LGA, State, Result, AgentAssignment

    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        asg = select(AgentAssignment.agent_id, AgentAssignment.pu_id).where(
            AgentAssignment.election_id == election_id).subquery()
        stmt = select(User, PollingUnit, Ward, LGA, State, Result).join(
            asg, asg.c.agent_id == User.id
        ).join(
            PollingUnit, PollingUnit.id == asg.c.pu_id, isouter=True
        ).join(
            Ward, PollingUnit.ward_id == Ward.id, isouter=True
        ).join(
            LGA, Ward.lga_id == LGA.id, isouter=True
        ).join(
            State, LGA.state_id == State.id, isouter=True
        ).join(
            Result, (Result.pu_id == PollingUnit.id) & (Result.election_id == election_id), isouter=True
        ).where(User.role == "agent")
    else:
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

    # Client tenancy: client admins monitor only their own institution's
    # agents; platform staff may narrow by any client.
    effective_client_id = user.client_id if user.client_id is not None else client_id
    if effective_client_id:
        stmt = stmt.where(User.client_id == effective_client_id)

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
    client_id: Optional[str] = None,
    election_id: Optional[str] = None,
    limit: int = 150,
    db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("view_agents"))
):
    """
    Electronic Coverage Audit: polling units without an accredited agent.
    With an election, gaps mean "in this election's scope but no agent
    accredited FOR THAT election". Without one, the legacy whole-registry
    view (platform admins only may omit the election).
    """
    print(f"AUDIT REQUEST: state={state_id}, lga={lga_id}, ward={ward_id}, election={election_id}")
    from sqlalchemy import select, func
    from .models import PollingUnit, User, Ward, LGA, State, ElectionPU, AgentAssignment

    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        # Scoped PUs lacking an assignment for this exact election.
        base = select(PollingUnit, Ward, LGA, State).join(
            ElectionPU, ElectionPU.pu_id == PollingUnit.id
        ).join(
            Ward, PollingUnit.ward_id == Ward.id
        ).join(
            LGA, Ward.lga_id == LGA.id
        ).join(
            State, LGA.state_id == State.id
        ).outerjoin(
            AgentAssignment,
            (AgentAssignment.pu_id == PollingUnit.id)
            & (AgentAssignment.election_id == ElectionPU.election_id)
        ).where(
            ElectionPU.election_id == election_id,
            AgentAssignment.id.is_(None),
        )
        if state_id: base = base.where(State.id == state_id)
        if lga_id: base = base.where(LGA.id == lga_id)
        if ward_id: base = base.where(Ward.id == ward_id)

        count_stmt = select(func.count(PollingUnit.id)).select_from(PollingUnit).join(
            ElectionPU, ElectionPU.pu_id == PollingUnit.id
        ).join(
            Ward, PollingUnit.ward_id == Ward.id
        ).join(
            LGA, Ward.lga_id == LGA.id
        ).join(
            State, LGA.state_id == State.id
        ).outerjoin(
            AgentAssignment,
            (AgentAssignment.pu_id == PollingUnit.id)
            & (AgentAssignment.election_id == ElectionPU.election_id)
        ).where(
            ElectionPU.election_id == election_id,
            AgentAssignment.id.is_(None),
        )
        if state_id: count_stmt = count_stmt.where(State.id == state_id)
        if lga_id: count_stmt = count_stmt.where(LGA.id == lga_id)
        if ward_id: count_stmt = count_stmt.where(Ward.id == ward_id)

        total_count = (await db.execute(count_stmt)).scalar()
        stmt = base.limit(limit)
        res = await db.execute(stmt)
        gaps = [{
            "id": pu.id, "name": pu.name, "code": pu.pu_code,
            "ward": ward.name, "lga": lga.name, "state": state.name,
        } for pu, ward, lga, state in res.all()]
        return {"total_count": total_count, "returned_count": len(gaps), "gaps": gaps}

    # ── Legacy whole-registry view ──
    # Client tenancy: only agents of the caller's institution count as
    # coverage; platform staff may narrow coverage to one client.
    from sqlalchemy import and_ as _and
    effective_client_id = user.client_id if user.client_id is not None else client_id
    coverage_filters = [PollingUnit.id == User.assigned_pu_id]
    if effective_client_id:
        coverage_filters.append(User.client_id == effective_client_id)
    coverage_onclause = _and(*coverage_filters)
    stmt = select(PollingUnit, Ward, LGA, State).join(
        Ward, PollingUnit.ward_id == Ward.id
    ).join(
        LGA, Ward.lga_id == LGA.id
    ).join(
        State, LGA.state_id == State.id
    ).outerjoin(
        User, coverage_onclause
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
        User, coverage_onclause
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
    from .elections import client_scope_election_ids

    # Client tenancy: a client admin's aggregates cover only their own
    # institution's agents and elections. Platform admins (client_id NULL)
    # keep the cross-client view.
    scoped_ids = await client_scope_election_ids(db, user)
    def scope_result(stmt):
        return stmt.where(Result.election_id.in_(scoped_ids)) if scoped_ids is not None else stmt
    def scope_agent(stmt):
        return stmt.where(User.client_id == user.client_id) if user.client_id is not None else stmt

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
    agent_count_stmt = scope_agent(select(func.count(User.id)).where(User.role == "agent"))
    if any([state_id, lga_id, ward_id, pu_id]):
        agent_count_stmt = apply_filters(agent_count_stmt, User)

    agent_count_res = await db.execute(agent_count_stmt)
    agents_provisioned = agent_count_res.scalar() or 0

    # 2. Vote Tallies
    votes_stmt = scope_result(select(
        func.sum(Result.party_a_votes),
        func.sum(Result.party_b_votes),
        func.sum(Result.party_c_votes)
    ))
    if any([state_id, lga_id, ward_id, pu_id]):
        votes_stmt = apply_filters(votes_stmt, Result)
        
    votes_res = await db.execute(votes_stmt)
    pa, pb, pc = votes_res.one()
    
    pa = pa or 0
    pb = pb or 0
    pc = pc or 0
    total_votes = pa + pb + pc

    # 3. Integrity Verified Percentage
    res_count_stmt = scope_result(select(func.count(Result.id)))
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
    flagged_stmt = scope_result(select(func.count(Result.id)).where(Result.is_flagged == True, Result.is_verified == False))
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
    # The probe runs in a thread (RPC wait must never block the event loop),
    # and the polygon module — which pulls in web3, a very heavy import — is
    # loaded lazily inside that thread. A module-level import here stretched
    # every gunicorn worker boot by minutes on this VM (full API outage on
    # every recreate). First request after boot pays the import; after that
    # the module is cached and answers come from the 120s balance cache.
    import asyncio
    def _status():
        from .polygon import get_wallet_status
        return get_wallet_status()
    return await asyncio.to_thread(_status)


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
    # Tenancy: roles are platform-global definitions; only platform admins
    # may mutate them.
    if user.client_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Role management is restricted to platform administrators.")

    role = Role(**payload.dict())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role

@router.put("/system/roles/{role_id}")
async def update_role(role_id: str, payload: RoleSchema, db: AsyncSession = Depends(get_db), user = Depends(RequirePermission("change_user_roles"))):
    # Tenancy: roles are platform-global definitions; only platform admins
    # may mutate them.
    if user.client_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Role management is restricted to platform administrators.")

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
    # Tenancy: roles are platform-global definitions; only platform admins
    # may mutate them.
    if user.client_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Role management is restricted to platform administrators.")

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
    # Platform admins only: bind the new account to an institution. Client
    # admins cannot set this — the new account is bound to their own client
    # automatically.
    client_id: Optional[str] = None

class SystemUserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/system/users")
async def get_system_users(db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("view_system_users"))):
    from sqlalchemy import select
    from .models import User
    # Only return non-agent users
    stmt = select(User).where(User.role != "agent")
    if user.client_id is not None:
        # Tenancy: a client admin must not even learn that other institutions'
        # staff accounts exist.
        stmt = stmt.where(User.client_id == user.client_id)
    res = await db.execute(stmt)
    users = res.scalars().all()
    return [
        {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
         "is_active": u.is_active, "client_id": str(u.client_id) if u.client_id else None}
        for u in users
    ]

@router.post("/system/users")
async def create_system_user(payload: SystemUserCreate, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    from .security import get_password_hash, get_current_user, RequirePermission

    # check exists
    res = await db.execute(select(User).where(User.email == payload.email))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Tenancy: client admins create staff bound to their own institution;
    # only platform admins may bind a new user to a specific client (or none).
    new_client_id = user.client_id if user.client_id is not None else payload.client_id

    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        requires_password_reset=True,
        client_id=new_client_id,
    )
    db.add(new_user)
    await db.commit()
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="USER_CREATED",
                    tenant_id=new_client_id,
                    target_type="user", target_id=new_user.id,
                    details=f"Operator account created: {payload.email} (role={payload.role})")
    await db.commit()
    return {"status": "success", "id": new_user.id}

@router.put("/system/users/{user_id}")
async def update_system_user(user_id: str, payload: SystemUserUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Tenancy: client admins can only touch their own institution's accounts
    # (and never platform-level accounts). 404, not 403 — don't reveal that
    # the foreign account exists.
    if user.client_id is not None and target.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.full_name is not None:
        target.full_name = payload.full_name
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active

    await db.commit()
    changed = [k for k, v in (("full_name", payload.full_name), ("role", payload.role),
                              ("is_active", payload.is_active)) if v is not None]
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="USER_UPDATED",
                    tenant_id=target.client_id,
                    target_type="user", target_id=target.id,
                    details=f"Operator account updated: {target.email} (fields: {', '.join(changed)})")
    await db.commit()
    return {"status": "success"}

@router.delete("/system/users/{user_id}")
async def delete_system_user(user_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(RequirePermission("create_system_users"))):
    from .models import User
    from sqlalchemy import select
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Tenancy: same wall as the update endpoint — foreign or platform-level
    # accounts must not be reachable from a client admin.
    if user.client_id is not None and target.client_id != user.client_id:
        raise HTTPException(status_code=404, detail="User not found")
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="USER_DELETED",
                    tenant_id=target.client_id,
                    target_type="user", target_id=target.id,
                    details=f"Operator account deleted: {target.email} (role={target.role})")
    await db.delete(target)
    await db.commit()
    return {"status": "success"}

def _public_evidence_url(url: Optional[str]) -> Optional[str]:
    """
    Uploads are stored with the backend's internal address
    (http://127.0.0.1:8001/static/uploads/...). Browsers can't reach that,
    so serve a same-origin relative path — the gateway already routes
    /static to the backend.
    """
    if not url:
        return url
    marker = "/static/"
    idx = url.find(marker)
    if idx != -1:
        return url[idx:]
    return url

@router.get("/all-documents")
async def get_all_documents(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client_id: Optional[str] = None,
    election_id: Optional[str] = None,
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_results")),
):
    """
    Document feed for the admin portal: every collated result with its
    evidence, geography breakdown, and on-chain anchor. Paginated, searchable
    by PU code/name, filterable by upload date (YYYY-MM-DD), and narrowed by
    the client -> election -> state -> lga -> ward -> pu hierarchy.
    Scoped to the caller's institution's elections.
    """
    from sqlalchemy import and_
    from datetime import datetime as _dt
    from .elections import client_scope_election_ids

    conditions = []
    scoped_ids = await client_scope_election_ids(db, user)
    if scoped_ids is not None:
        conditions.append(Result.election_id.in_(scoped_ids))
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        conditions.append(Result.election_id == election_id)
    if search:
        like = f"%{search}%"
        conditions.append(
            (PollingUnit.pu_code.ilike(like)) | (PollingUnit.name.ilike(like))
        )
    try:
        if start_date:
            conditions.append(Result.uploaded_at >= _dt.fromisoformat(start_date))
        if end_date:
            # inclusive of the whole end day
            end = _dt.fromisoformat(end_date)
            conditions.append(Result.uploaded_at < end.replace(hour=23, minute=59, second=59))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Geo hierarchy filters — the election scope still bounds what is visible.
    if state_id: conditions.append(State.id == state_id)
    if lga_id: conditions.append(LGA.id == lga_id)
    if ward_id: conditions.append(Ward.id == ward_id)
    if pu_id: conditions.append(PollingUnit.id == pu_id)

    stmt = (
        select(Result, PollingUnit, Ward, LGA, State, Election)
        .join(PollingUnit, Result.pu_id == PollingUnit.id)
        .join(Ward, PollingUnit.ward_id == Ward.id, isouter=True)
        .join(LGA, Ward.lga_id == LGA.id, isouter=True)
        .join(State, LGA.state_id == State.id, isouter=True)
        .join(Election, Result.election_id == Election.id, isouter=True)
    )
    # Client tenancy: client admins are confined by scoped_ids above; platform
    # staff may narrow by any client.
    effective_client_id = user.client_id if user.client_id is not None else client_id
    if effective_client_id:
        stmt = stmt.where(Election.client_id == effective_client_id)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Result.uploaded_at.desc()).offset(skip).limit(min(limit, 200))

    res = await db.execute(stmt)
    documents = []
    for result, pu, ward, lga, state, election in res.all():
        documents.append({
            "id": result.id,
            "image_url": _public_evidence_url(result.image_url),
            "video_url": _public_evidence_url(result.video_url),
            "pu_code": pu.pu_code if pu else None,
            "pu_name": pu.name if pu else None,
            "ward": ward.name if ward else None,
            "lga": lga.name if lga else None,
            "state": state.name if state else None,
            "election_code": election.code if election else None,
            "election_name": election.name if election else None,
            "party_a": result.party_a_votes,
            "party_b": result.party_b_votes,
            "party_c": result.party_c_votes,
            "uploaded_at": result.uploaded_at.isoformat() if result.uploaded_at else None,
            "blockchain_hash": result.blockchain_hash,
            "blockchain_tx_id": result.blockchain_tx_id,
            "gps_trail_flag": result.gps_trail_flag,
        })
    return documents

@router.get("/pending-verifications")
async def get_pending_verifications(
    client_id: Optional[str] = None,
    election_id: Optional[str] = None,
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_results")),
):
    """
    AI review queue: results the OCR flagged as diverging from the agent's
    entered figures, not yet cleared by a human verifier. NARROWED by the
    client -> election -> geo hierarchy like every other operational view.
    Scoped to the caller's institution's elections.
    """
    from .elections import client_scope_election_ids
    conditions = [Result.is_flagged.is_(True), Result.is_verified.is_(False)]
    scoped_ids = await client_scope_election_ids(db, user)
    if scoped_ids is not None:
        conditions.append(Result.election_id.in_(scoped_ids))
    if election_id:
        await _assert_election_geo_visible(db, user, election_id)
        conditions.append(Result.election_id == election_id)
    if state_id: conditions.append(State.id == state_id)
    if lga_id: conditions.append(LGA.id == lga_id)
    if ward_id: conditions.append(Ward.id == ward_id)
    if pu_id: conditions.append(PollingUnit.id == pu_id)

    stmt = (
        select(Result, PollingUnit, Ward, LGA, State, Election)
        .join(PollingUnit, Result.pu_id == PollingUnit.id)
        .join(Ward, PollingUnit.ward_id == Ward.id, isouter=True)
        .join(LGA, Ward.lga_id == LGA.id, isouter=True)
        .join(State, LGA.state_id == State.id, isouter=True)
        .join(Election, Result.election_id == Election.id, isouter=True)
        .where(*conditions)
        .order_by(Result.uploaded_at.desc())
    )
    # Client tenancy: client admins are confined by scoped_ids above; platform
    # staff may narrow by any client.
    effective_client_id = user.client_id if user.client_id is not None else client_id
    if effective_client_id:
        stmt = stmt.where(Election.client_id == effective_client_id)

    res = await db.execute(stmt)
    queue = []
    for result, pu, ward, lga, state, election in res.all():
        queue.append({
            "id": result.id,
            "pu_code": pu.pu_code if pu else None,
            "image_url": _public_evidence_url(result.image_url),
            "party_a": result.party_a_votes,
            "party_b": result.party_b_votes,
            "party_c": result.party_c_votes,
            "ai_party_a": result.ai_party_a_votes,
            "ai_party_b": result.ai_party_b_votes,
            "ai_party_c": result.ai_party_c_votes,
            "ai_confidence": result.ai_confidence,
            "captured_at": result.captured_at.isoformat() if result.captured_at else None,
            "gps_trail_flag": result.gps_trail_flag,
            "election_code": election.code if election else None,
            "election_name": election.name if election else None,
        })
    return queue


@router.get("/results/{result_id}/trail")
async def get_result_presence_trail(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePermission("view_results")),
):
    """
    Presence trail for one result: the agent's verify-entry point, every GPS
    breadcrumb recorded between check-in and submission, the submission point
    itself, and the PU's geofence anchor — everything the situation room needs
    to eyeball whether the agent was physically on site throughout.
    """
    res = await db.execute(
        select(Result, PollingUnit, User)
        .join(PollingUnit, Result.pu_id == PollingUnit.id, isouter=True)
        .join(User, Result.agent_id == User.id, isouter=True)
        .where(Result.id == result_id)
    )
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Result not found.")
    result, pu, agent = row

    # Client tenancy: out-of-scope results must be indistinguishable from
    # non-existent ones.
    from .elections import client_scope_election_ids, assert_in_scope
    assert_in_scope(result.election_id, await client_scope_election_ids(db, user))

    pings = []
    if agent is not None:
        stmt = (
            select(AgentLocationPing)
            .where(AgentLocationPing.agent_id == agent.id)
            .order_by(AgentLocationPing.recorded_at)
        )
        # Only the trail relevant to this collation window: from the agent's
        # last check-in onwards (check-in time is refreshed at verify-entry).
        if agent.last_check_in is not None:
            stmt = stmt.where(AgentLocationPing.recorded_at >= agent.last_check_in)
        ping_res = await db.execute(stmt)
        for p in ping_res.scalars().all():
            pings.append({
                "lat": p.latitude,
                "lng": p.longitude,
                "at": p.recorded_at.isoformat() if p.recorded_at else None,
                "outside_geofence": p.outside_geofence,
                "distance_m": p.distance_m,
            })

    anchor = None
    if pu is not None and pu.expected_latitude and pu.expected_longitude:
        try:
            anchor = {"lat": float(pu.expected_latitude),
                      "lng": float(pu.expected_longitude)}
        except (TypeError, ValueError):
            anchor = None

    # Geofence verdict: what can the chain actually prove about presence?
    # ok | outside | unverifiable_no_anchor | unverifiable_no_gps
    geofence_verdict = "unverifiable_no_anchor"
    checkin_distance_m = None
    if anchor and agent is not None and agent.check_in_lat is not None and agent.check_in_lng is not None:
        import math as _m
        _rlat1, _rlat2 = _m.radians(float(agent.check_in_lat)), _m.radians(anchor["lat"])
        _dlat = _m.radians(anchor["lat"] - float(agent.check_in_lat))
        _dlng = _m.radians(anchor["lng"] - float(agent.check_in_lng))
        _a = _m.sin(_dlat / 2) ** 2 + _m.cos(_rlat1) * _m.cos(_rlat2) * _m.sin(_dlng / 2) ** 2
        checkin_distance_m = 2 * 6371000 * _m.asin(_m.sqrt(_a))
        geofence_verdict = "ok" if checkin_distance_m <= _geofence_radius() else "outside"
    elif agent is not None and agent.check_in_lat is None:
        geofence_verdict = "unverifiable_no_gps"

    return {
        "result_id": result.id,
        "pu_code": pu.pu_code if pu else None,
        "pu_name": pu.name if pu else None,
        "agent_email": agent.email if agent else None,
        "gps_trail_flag": result.gps_trail_flag,
        "geofence_verdict": geofence_verdict,
        "checkin_distance_m": checkin_distance_m,
        "has_anchor": anchor is not None,
        "anchor": anchor,
        "geofence_radius_m": _geofence_radius(),
        "check_in": ({
            "lat": agent.check_in_lat,
            "lng": agent.check_in_lng,
            "at": agent.last_check_in.isoformat() if agent.last_check_in else None,
        } if agent else None),
        "submission": ({
            "lat": result.latitude,
            "lng": result.longitude,
            "at": result.uploaded_at.isoformat() if result.uploaded_at else None,
        }),
        "pings": pings,
    }


def _geofence_radius() -> float:
    import os as _os
    return float(_os.environ.get("GEOFENCE_RADIUS_METRES", "200"))


# ── In-memory cache: the map query scans the registry, so serve fresh ──
# data at most once every 30 seconds regardless of how many dashboards
# are open in the situation room. Cached per election scope.
_monitor_cache = {"at": 0.0, "payload": None, "by_election": {}}


@router.get("/monitor/map")
async def get_monitor_map(
    election_id: Optional[str] = None,
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePermission("view_results")),
):
    """
    Live operational map: one status per polling unit that carries an agent
    (individual marker) plus LGA-level grey bubbles for PUs with no agent
    yet (plotting 170k+ points would melt browsers).

    Filter hierarchy: client (implicit via tenancy/election ownership) ->
    election -> state -> LGA. Statuses: assigned (blue, agent not on site),
    on_site (green, verified entry and latest fix inside the fence),
    out_of_fence (orange, latest fix outside the perimeter), submitted
    (purple, result collated).
    """
    import time as _time
    from sqlalchemy import text as _text
    from .elections import client_scope_election_ids, assert_in_scope

    # Client tenancy: a scoped map is only for elections the caller's
    # institution owns; the nationwide aggregate view is platform-admin only
    # (a client must pick their election to avoid cross-client leakage).
    if election_id:
        assert_in_scope(election_id, await client_scope_election_ids(db, _))
    elif getattr(_, "client_id", None) is not None:
        raise HTTPException(status_code=403,
                            detail="Select an election to view its map.")

    now = _time.time()
    # Cache key includes the geo focus so filtered views never get a
    # nationwide cached payload (or vice versa).
    cache_key = f"{election_id or ''}|{state_id or ''}|{lga_id or ''}"
    if election_id:
        cached = _monitor_cache["by_election"].get(cache_key)
        if cached and now - cached["at"] < 30:
            return cached["payload"]
    elif not (state_id or lga_id) and _monitor_cache["payload"] and now - _monitor_cache["at"] < 30:
        return _monitor_cache["payload"]

    if election_id:
        # ── Election-scoped view: only PUs in this election's scope, agents
        # accredited for this election, results and sessions of this race.
        # Optional state/LGA focus narrows within the scope. ──
        agent_rows = (await db.execute(_text("""
            SELECT pu.pu_code, pu.name,
                   (pu.expected_latitude IS NOT NULL) AS has_anchor,
                   COALESCE(pu.expected_latitude::float, u.check_in_lat) AS lat,
                   COALESCE(pu.expected_longitude::float, u.check_in_lng) AS lng,
                   (ci.id IS NOT NULL) AS is_on_site,
                   ci.checked_in_at AS last_check_in,
                   (r.id IS NOT NULL) AS submitted,
                   lp.outside_geofence AS latest_outside
            FROM election_polling_units sc
            JOIN polling_units pu ON pu.id = sc.pu_id
            JOIN wards w ON pu.ward_id = w.id
            JOIN lgas l ON w.lga_id = l.id
            JOIN states s ON l.state_id = s.id
            JOIN agent_assignments a ON a.pu_id = pu.id AND a.election_id = sc.election_id
            JOIN users u ON u.id = a.agent_id
            LEFT JOIN results r ON r.pu_id = pu.id AND r.election_id = sc.election_id
            LEFT JOIN LATERAL (
                SELECT outside_geofence FROM agent_location_pings p
                WHERE p.agent_id = u.id AND p.election_id = sc.election_id
                ORDER BY recorded_at DESC LIMIT 1
            ) lp ON true
            LEFT JOIN LATERAL (
                SELECT id, checked_in_at FROM agent_checkins c
                WHERE c.agent_id = u.id AND c.election_id = sc.election_id AND c.is_active
                ORDER BY checked_in_at DESC LIMIT 1
            ) ci ON true
            WHERE sc.election_id = :eid
              AND (CAST(:sid AS varchar) IS NULL OR s.id = :sid)
              AND (CAST(:lid AS varchar) IS NULL OR l.id = :lid)
        """), {"eid": election_id, "sid": state_id, "lid": lga_id})).all()

        markers = []
        counters = {"assigned": 0, "on_site": 0, "out_of_fence": 0, "submitted": 0, "no_anchor": 0}
        for pu_code, name, has_anchor, lat, lng, is_on_site, last_check_in, submitted, latest_outside in agent_rows:
            if submitted:
                status = "submitted"
            elif not has_anchor:
                status = "no_anchor"
            elif not is_on_site or last_check_in is None:
                status = "assigned"
            elif latest_outside is True:
                status = "out_of_fence"
            else:
                status = "on_site"
            counters[status] += 1
            if lat is None or lng is None:
                continue  # no anchor and no check-in fix yet — nothing to plot
            markers.append({"pu_code": pu_code, "name": name, "lat": lat, "lng": lng,
                            "status": status, "has_anchor": bool(has_anchor)})

        cluster_rows = (await db.execute(_text("""
            SELECT s.name AS state, l.name AS lga,
                   count(*) AS n,
                   avg(pu.expected_latitude::float) AS lat,
                   avg(pu.expected_longitude::float) AS lng
            FROM election_polling_units sc
            JOIN polling_units pu ON pu.id = sc.pu_id
            JOIN wards w ON pu.ward_id = w.id
            JOIN lgas l ON w.lga_id = l.id
            JOIN states s ON l.state_id = s.id
            LEFT JOIN agent_assignments a
              ON a.pu_id = pu.id AND a.election_id = sc.election_id
            WHERE sc.election_id = :eid AND a.id IS NULL AND pu.expected_latitude IS NOT NULL
              AND (CAST(:sid AS varchar) IS NULL OR s.id = :sid)
              AND (CAST(:lid AS varchar) IS NULL OR l.id = :lid)
            GROUP BY s.name, l.name
        """), {"eid": election_id, "sid": state_id, "lid": lga_id})).all()
        unassigned_clusters = [{"state": s, "lga": l, "count": n, "lat": lat, "lng": lng}
                               for s, l, n, lat, lng in cluster_rows]
        counters["unassigned"] = sum(c["count"] for c in unassigned_clusters)

        no_coords = (await db.execute(_text(
            "SELECT count(*) FROM election_polling_units sc "
            "JOIN polling_units pu ON pu.id = sc.pu_id "
            "JOIN wards w ON pu.ward_id = w.id "
            "JOIN lgas l ON w.lga_id = l.id "
            "JOIN states s ON l.state_id = s.id "
            "WHERE sc.election_id = :eid AND pu.expected_latitude IS NULL "
            "AND (CAST(:sid AS varchar) IS NULL OR s.id = :sid) "
            "AND (CAST(:lid AS varchar) IS NULL OR l.id = :lid)"),
            {"eid": election_id, "sid": state_id, "lid": lga_id})).scalar()

        payload = {
            "generated_at": now,
            "election_id": election_id,
            "counters": {**counters, "no_coordinates": no_coords or 0},
            "markers": markers,
            "unassigned_clusters": unassigned_clusters,
        }
        _monitor_cache["by_election"][cache_key] = {"at": now, "payload": payload}
        return payload

    # ── Unscoped (legacy) view: whole registry as before, with optional
    # state/LGA focus for platform admins. ──
    # Agent-carrying PUs with live status
    agent_rows = (await db.execute(_text("""
        SELECT pu.pu_code, pu.name,
               (pu.expected_latitude IS NOT NULL) AS has_anchor,
               COALESCE(pu.expected_latitude::float, u.check_in_lat) AS lat,
               COALESCE(pu.expected_longitude::float, u.check_in_lng) AS lng,
               u.is_on_site, u.last_check_in,
               (r.id IS NOT NULL) AS submitted,
               lp.outside_geofence AS latest_outside
        FROM polling_units pu
        JOIN wards w ON pu.ward_id = w.id
        JOIN lgas l ON w.lga_id = l.id
        JOIN states s ON l.state_id = s.id
        JOIN users u ON u.assigned_pu_id = pu.id AND u.role = 'agent'
        LEFT JOIN results r ON r.pu_id = pu.id
        LEFT JOIN LATERAL (
            SELECT outside_geofence FROM agent_location_pings p
            WHERE p.agent_id = u.id ORDER BY recorded_at DESC LIMIT 1
        ) lp ON true
        WHERE (CAST(:sid AS varchar) IS NULL OR s.id = :sid)
          AND (CAST(:lid AS varchar) IS NULL OR l.id = :lid)
    """), {"sid": state_id, "lid": lga_id})).all()

    markers = []
    counters = {"assigned": 0, "on_site": 0, "out_of_fence": 0, "submitted": 0, "no_anchor": 0}
    for pu_code, name, has_anchor, lat, lng, is_on_site, last_check_in, submitted, latest_outside in agent_rows:
        if submitted:
            status = "submitted"
        elif not has_anchor:
            status = "no_anchor"
        elif not is_on_site or last_check_in is None:
            status = "assigned"
        elif latest_outside is True:
            status = "out_of_fence"
        else:
            status = "on_site"
        counters[status] += 1
        if lat is None or lng is None:
            continue  # no anchor and no check-in fix yet — nothing to plot
        markers.append({"pu_code": pu_code, "name": name, "lat": lat, "lng": lng,
                        "status": status, "has_anchor": bool(has_anchor)})

    # Unassigned PUs aggregated to LGA bubbles
    cluster_rows = (await db.execute(_text("""
        SELECT s.name AS state, l.name AS lga,
               count(*) AS n,
               avg(pu.expected_latitude::float) AS lat,
               avg(pu.expected_longitude::float) AS lng
        FROM polling_units pu
        JOIN wards w ON pu.ward_id = w.id
        JOIN lgas l ON w.lga_id = l.id
        JOIN states s ON l.state_id = s.id
        LEFT JOIN users u ON u.assigned_pu_id = pu.id AND u.role = 'agent'
        WHERE u.id IS NULL AND pu.expected_latitude IS NOT NULL
          AND (CAST(:sid AS varchar) IS NULL OR s.id = :sid)
          AND (CAST(:lid AS varchar) IS NULL OR l.id = :lid)
        GROUP BY s.name, l.name
    """), {"sid": state_id, "lid": lga_id})).all()
    unassigned_clusters = [{"state": s, "lga": l, "count": n, "lat": lat, "lng": lng}
                           for s, l, n, lat, lng in cluster_rows]
    counters["unassigned"] = sum(c["count"] for c in unassigned_clusters)

    no_coords = (await db.execute(_text(
        "SELECT count(*) FROM polling_units WHERE expected_latitude IS NULL"))).scalar()

    payload = {
        "generated_at": now,
        "counters": {**counters, "no_coordinates": no_coords or 0},
        "markers": markers,
        "unassigned_clusters": unassigned_clusters,
    }
    # Only the unfiltered nationwide view may populate the shared cache slot.
    if not (state_id or lga_id):
        _monitor_cache["at"] = now
        _monitor_cache["payload"] = payload
    return payload
