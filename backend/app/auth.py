from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .db import get_db
from .security import (
    check_login_attempt, create_access_token, check_login_rate_limits,
    record_login_failure, clear_login_failures, get_timing_dummy_hash,
    get_current_user, log_audit,
)
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
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    email = payload.email
    password = payload.password
    device_fingerprint = payload.device_fingerprint
    real_ip = request.client.host if request.client else None
    """
    Highly secure login endpoint.
    """
    # 0. Anti-Brute Force Protection — per-email AND per-IP buckets (Redis).
    if not await check_login_rate_limits(email, real_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later."
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
        # Timing equalizer: spend the same Argon2 work as a real verify so
        # account existence cannot be detected by response time.
        from .security import pwd_context as _pwd_ctx
        _pwd_ctx.verify(password, get_timing_dummy_hash())
        await record_login_failure(email, real_ip)
        await log_audit(db, action="LOGIN_FAILED",
                        details=f"Unknown email attempted login: {email}",
                        ip_address=real_ip)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user, pu, ward, lga, state = row

    if not user.is_active:
        await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                        action="LOGIN_INACTIVE",
                        tenant_id=getattr(user, "client_id", None),
                        target_type="user", target_id=str(user.id),
                        details=f"Deactivated account attempted login: {email}",
                        ip_address=real_ip)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been deactivated. Contact the system administrator.")

    # 2. Device Fingerprinting Challenge
    if user.device_fingerprint and device_fingerprint != user.device_fingerprint:
        await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                        action="LOGIN_DEVICE_REJECTED",
                        tenant_id=getattr(user, "client_id", None),
                        target_type="user", target_id=str(user.id),
                        details=f"Login rejected: unrecognized device for {email}",
                        ip_address=real_ip,
                        device_fingerprint=device_fingerprint)
        await db.commit()
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
    
    if not is_authenticated:
        print(f"[AUTH] Failed login attempt for {email}")
        await record_login_failure(email, real_ip)
        await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                        action="LOGIN_FAILED",
                        tenant_id=getattr(user, "client_id", None),
                        target_type="user", target_id=str(user.id),
                        details=f"Failed password for {email}",
                        ip_address=real_ip,
                        device_fingerprint=device_fingerprint)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Correct password: clear the email lockout bucket so a few typos can
    # never lock a legitimate agent out of election day.
    await clear_login_failures(email)

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
            await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                            action="MFA_REJECT",
                            tenant_id=getattr(user, "client_id", None),
                            target_type="user", target_id=str(user.id),
                            details=f"Invalid or expired MFA token at login for {email}",
                            ip_address=real_ip)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA token."
            )
        print(f"[SECURITY] MFA Verified for user {user.email}")

    # 3.55 Election-day gate for field agents: an agent whose accredited
    # elections are ALL non-live has nothing to do in the app yet, so no
    # token is issued. Placed after password + MFA verification (so nothing
    # leaks before the password is proven) and exempts agents still awaiting
    # their first password setup, so the bootstrap reset flow stays open.
    if user.role == "agent" and not user.requires_password_reset:
        from .models import AgentAssignment as _AA, Election as _EL
        _eids = [r[0] for r in (await db.execute(
            select(_AA.election_id).where(_AA.agent_id == user.id))).all()]
        if not _eids:
            # No accreditation at all: nothing to report, no reason to be in
            # the app. Same handling as the not-live gate below.
            _msg = "You are not accredited for any election. Contact your coordinator."
            print(f"[AUTH] Agent login blocked (no assignment): {email}")
            await log_audit(db, actor_id=str(user.id), actor_role="agent",
                            action="LOGIN_ELECTION_NOT_LIVE",
                            tenant_id=getattr(user, "client_id", None),
                            target_type="user", target_id=str(user.id),
                            details="Agent login blocked: no election assignment on record",
                            ip_address=real_ip,
                            device_fingerprint=device_fingerprint)
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_msg)
        if _eids:
            _statuses = (await db.execute(
                select(_EL.status).where(_EL.id.in_(_eids)))).scalars().all()
            if "live" not in _statuses:
                _msg = ("The election is not live yet. You will be able to "
                        "log in when voting begins." if "upcoming" in _statuses
                        else "The election is closed. Submissions for your "
                        "assignment are no longer open.")
                print(f"[AUTH] Agent login blocked (no live election): {email} statuses={_statuses}")
                await log_audit(db, actor_id=str(user.id), actor_role="agent",
                                action="LOGIN_ELECTION_NOT_LIVE",
                                tenant_id=getattr(user, "client_id", None),
                                target_type="user", target_id=str(user.id),
                                details=f"Agent login blocked: accredited election statuses={list(_statuses)}",
                                ip_address=real_ip,
                                device_fingerprint=device_fingerprint)
                await db.commit()
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_msg)

    # 3.6 Successful authentication — chained audit row. Duress logins get
    # their own action name so the situation room can filter the silent
    # alarm without parsing details.
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="LOGIN_DURESS" if is_under_duress else "LOGIN_SUCCESS",
                    tenant_id=getattr(user, "client_id", None),
                    target_type="user", target_id=str(user.id),
                    details=f"Login {'under DURESS ' if is_under_duress else ''}for {email} (role={user.role})",
                    ip_address=real_ip,
                    device_fingerprint=device_fingerprint)
    # The login path never wrote anything before, so there is no later
    # commit to piggyback on — without this the audit row rolls back.
    await db.commit()

    if user.requires_password_reset:
        return {
            "access_token": None,
            "role": user.role,
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

    # Geographic metadata for agents (legacy single-assignment shape)
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

    # Election-scoped assignments: one entry per (election, PU) the agent is
    # accredited for, with the per-election muster-roll state. The agent app
    # renders its verify-entry picker and result form from this list, so the
    # agent never free-types which election they are reporting for.
    assignments = []
    if user.role == "agent":
        from .models import AgentAssignment, Election, AgentCheckIn
        a_rows = (await db.execute(
            select(AgentAssignment, Election, PollingUnit, Ward, LGA, State)
            .join(Election, AgentAssignment.election_id == Election.id)
            .join(PollingUnit, AgentAssignment.pu_id == PollingUnit.id)
            .join(Ward, PollingUnit.ward_id == Ward.id, isouter=True)
            .join(LGA, Ward.lga_id == LGA.id, isouter=True)
            .join(State, LGA.state_id == State.id, isouter=True)
            .where(AgentAssignment.agent_id == user.id)
        )).all()
        ci_rows = (await db.execute(
            select(AgentCheckIn.election_id, func.max(AgentCheckIn.checked_in_at))
            .where(AgentCheckIn.agent_id == user.id, AgentCheckIn.is_active == True)
            .group_by(AgentCheckIn.election_id)
        )).all()
        on_site_by_election = {eid: ts for eid, ts in ci_rows}
        for a, el, apu, award, alga, astate in a_rows:
            assignments.append({
                "election_id": el.id,
                "election_name": el.name,
                "election_code": el.code,
                "election_type": el.type,
                "election_status": el.status,
                "party_a_name": el.party_a_name,
                "party_b_name": el.party_b_name,
                "party_c_name": el.party_c_name,
                "pu": {
                    "id": apu.id,
                    "pu_code": apu.pu_code,
                    "name": apu.name,
                    "ward": award.name if award else "Unknown",
                    "lga": alga.name if alga else "Unknown",
                    "state": astate.name if astate else "Unknown",
                },
                "is_on_site": el.id in on_site_by_election,
                "checked_in_at": on_site_by_election[el.id].isoformat() if el.id in on_site_by_election else None,
            })

    # Institution (client) tenancy label: NULL client_id = platform super-admin
    # and sees every institution; otherwise the portal header shows the
    # admin's owning institution so there is never ambiguity about which
    # election space they are working in.
    client_id = getattr(user, "client_id", None)
    client_name = None
    if client_id:
        from .models import Client as _Client
        _c = (await db.execute(select(_Client).where(_Client.id == client_id))).scalar_one_or_none()
        client_name = _c.name if _c else None

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "client_id": client_id,
        "client_name": client_name,
        "requires_password_reset": False,
        "assigned_pu": assigned_pu,
        "assignments": assignments,
        "notice": "Login Successful."
    }

class CheckInSchema(BaseModel):
    email: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Election being checked in for. The agent picks this ONCE at verify-entry
    # (from their assignment list) and the resulting session binds every later
    # ping and the final submission to this election. Optional only for legacy
    # apps: when absent, the default election and legacy PU pointer apply.
    election_id: Optional[str] = None

@router.post("/agent/check-in")
async def agent_check_in(payload: CheckInSchema, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Electronic Muster Roll, scoped per election: agents confirm physical
    arrival at the PU FOR A SPECIFIC ELECTION. The check-in opens a session
    (agent_checkins row) that the submission endpoint later requires — so an
    agent verified for the Delta senatorial race cannot submit a governorship
    result, and vice versa.
    """
    from datetime import datetime
    from .models import AgentAssignment, AgentCheckIn, Election, PollingUnit
    from sqlalchemy import select as _select
    from sqlalchemy import text

    if current_user.role != "agent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only field agents can check in.")
    if payload.email.lower() != current_user.email.lower():
        await log_audit(db, actor_id=str(current_user.id), actor_role="agent",
                        action="CHECKIN_IDENTITY_REJECT",
                        tenant_id=getattr(current_user, "client_id", None),
                        target_type="agent_checkin", target_id=str(current_user.id),
                        details=f"Check-in email {payload.email} does not match the authenticated agent")
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Check-in identity does not match the authenticated agent.")

    print(f"[CHECK-IN] Received payload: email={payload.email}, lat={payload.latitude}, lng={payload.longitude}, election={payload.election_id}")

    # Resolve the election + PU for this check-in.
    assignment = None
    election = None
    if payload.election_id:
        assignment = (await db.execute(_select(AgentAssignment).where(
            AgentAssignment.agent_id == current_user.id,
            AgentAssignment.election_id == payload.election_id,
        ))).scalar_one_or_none()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not accredited for this election. Contact your coordinator."
            )
        election = (await db.execute(_select(Election).where(Election.id == payload.election_id))).scalar_one_or_none()
        assigned_pu_id = assignment.pu_id
    else:
        # Legacy fallback: default election (GENERAL if the registry still
        # has one, else the agent's single accredited election) + its PU.
        from .elections import resolve_default_election
        election, legacy_assignment = await resolve_default_election(db, current_user)
        if legacy_assignment:
            assigned_pu_id = legacy_assignment.pu_id
            assignment = legacy_assignment
        else:
            assigned_pu_id = current_user.assigned_pu_id
            if election and assigned_pu_id:
                assignment = (await db.execute(_select(AgentAssignment).where(
                    AgentAssignment.agent_id == current_user.id,
                    AgentAssignment.election_id == election.id,
                    AgentAssignment.pu_id == assigned_pu_id,
                ))).scalar_one_or_none()
        if not assigned_pu_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No assigned polling unit on record.")

    pu_res = await db.execute(_select(PollingUnit).where(PollingUnit.id == assigned_pu_id))
    pu = pu_res.scalar_one_or_none()

    # Geofence: when the assigned PU has anchor coordinates on record, the
    # check-in GPS must be within GEOFENCE_RADIUS_METRES of them.
    dist_m = None
    if pu and payload.latitude is not None and payload.longitude is not None:
        import math as _math
        import os as _os
        if pu.expected_latitude and pu.expected_longitude:
            try:
                anchor_lat, anchor_lng = float(pu.expected_latitude), float(pu.expected_longitude)
            except (TypeError, ValueError):
                anchor_lat = anchor_lng = None
            if anchor_lat is not None:
                radius = float(_os.environ.get("GEOFENCE_RADIUS_METRES", "200"))
                rlat1, rlat2 = _math.radians(payload.latitude), _math.radians(anchor_lat)
                dlat = _math.radians(anchor_lat - payload.latitude)
                dlng = _math.radians(float(pu.expected_longitude) - payload.longitude)
                a = _math.sin(dlat / 2) ** 2 + _math.cos(rlat1) * _math.cos(rlat2) * _math.sin(dlng / 2) ** 2
                dist_m = 2 * 6371000 * _math.asin(_math.sqrt(a))
                if dist_m > radius:
                    print(f"[CHECK-IN] Rejected: {payload.email} is {dist_m:.0f}m from PU {pu.pu_code} anchor")
                    await log_audit(db, actor_id=str(current_user.id), actor_role="agent",
                                    action="CHECKIN_GEOFENCE_REJECT",
                                    tenant_id=getattr(current_user, "client_id", None),
                                    election_id=election.id if election else None,
                                    target_type="agent_checkin", target_id=str(current_user.id),
                                    details=f"Check-in rejected: {int(dist_m)}m from PU {pu.pu_code} anchor (radius {int(radius)}m), election={election.code if election else 'legacy'}")
                    await db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Check-in rejected: you appear to be {int(dist_m)}m from your assigned polling unit. Move on-site and try again."
                    )

    # Open a fresh per-election session (the old one, if any, is closed).
    if election:
        await db.execute(
            text("UPDATE agent_checkins SET is_active = false "
                 "WHERE agent_id = :a AND election_id = :e AND is_active = true"),
            {"a": str(current_user.id), "e": election.id},
        )
        db.add(AgentCheckIn(
            agent_id=current_user.id,
            election_id=election.id,
            pu_id=assigned_pu_id,
            checked_in_at=datetime.utcnow(),
            latitude=payload.latitude,
            longitude=payload.longitude,
            is_active=True,
        ))

    # Keep the legacy user-row flags in sync so older admin views keep working.
    user = current_user
    user.is_on_site = True
    user.last_check_in = datetime.utcnow()
    user.check_in_lat = payload.latitude
    user.check_in_lng = payload.longitude
    await db.commit()

    await log_audit(db, actor_id=str(current_user.id), actor_role="agent",
                    action="CHECKIN_SUCCESS",
                    tenant_id=getattr(current_user, "client_id", None),
                    election_id=election.id if election else None,
                    target_type="agent_checkin", target_id=str(current_user.id),
                    details=f"Verify entry confirmed for {payload.email} at PU {pu.pu_code if pu else assigned_pu_id}"
                            + (f" ({int(dist_m)}m from anchor)" if dist_m is not None else " (no GPS fix)"))
    await db.commit()

    print(f"[CHECK-IN] Persisted: lat={user.check_in_lat}, lng={user.check_in_lng}, election={election.code if election else 'legacy'}")
    return {"status": "success", "election_id": election.id if election else None,
            "message": f"Arrival confirmed for {election.name if election else 'your assignment'}. You are now ACTIVE on the muster roll."}


class LocationPingSchema(BaseModel):
    email: str
    latitude: float
    longitude: float
    # Election context for the breadcrumb. Legacy apps may omit it; the ping
    # then attaches to the default election via the legacy PU pointer.
    election_id: Optional[str] = None

@router.post("/agent/location-ping")
async def agent_location_ping(payload: LocationPingSchema, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Presence-trail breadcrumb, scoped to the election the agent declared at
    verify-entry. Between "Verify Entry" and result submission the portal
    posts the device GPS every PING_INTERVAL_MINUTES (default 30). The ping
    is RECORDED, never rejected: drifting outside the geofence sets a flag on
    the row instead of failing the request. At submission time the server
    counts the pings FOR THAT ELECTION and flags thin trails.
    """
    from datetime import datetime
    from .models import AgentLocationPing, PollingUnit, AgentAssignment, Election
    from sqlalchemy import select as _select
    import math as _math
    import os as _os

    if current_user.role != "agent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only field agents can send location pings.")
    if payload.email.lower() != current_user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ping identity does not match the authenticated agent.")

    # Resolve the PU (and election) for this ping from the agent's assignment.
    election_id = None
    if payload.election_id:
        assignment = (await db.execute(_select(AgentAssignment).where(
            AgentAssignment.agent_id == current_user.id,
            AgentAssignment.election_id == payload.election_id,
        ))).scalar_one_or_none()
        if not assignment:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="No assignment on record for this election.")
        election_id = payload.election_id
        assigned_pu_id = assignment.pu_id
    else:
        election = (await db.execute(_select(Election).where(Election.code == "GENERAL"))).scalar_one_or_none()
        election_id = election.id if election else None
        assigned_pu_id = current_user.assigned_pu_id

    if not assigned_pu_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No assigned polling unit on record.")

    pu_res = await db.execute(_select(PollingUnit).where(PollingUnit.id == assigned_pu_id))
    pu = pu_res.scalar_one_or_none()

    outside, dist_m = False, None
    if pu and pu.expected_latitude and pu.expected_longitude:
        try:
            anchor_lat, anchor_lng = float(pu.expected_latitude), float(pu.expected_longitude)
            radius = float(_os.environ.get("GEOFENCE_RADIUS_METRES", "200"))
            rlat1, rlat2 = _math.radians(payload.latitude), _math.radians(anchor_lat)
            dlat = _math.radians(anchor_lat - payload.latitude)
            dlng = _math.radians(anchor_lng - payload.longitude)
            a = _math.sin(dlat / 2) ** 2 + _math.cos(rlat1) * _math.cos(rlat2) * _math.sin(dlng / 2) ** 2
            dist_m = 2 * 6371000 * _math.asin(_math.sqrt(a))
            outside = dist_m > radius
        except (TypeError, ValueError):
            pass  # unparseable anchors — record the ping without a verdict

    ping = AgentLocationPing(
        agent_id=current_user.id,
        pu_id=assigned_pu_id,
        election_id=election_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        outside_geofence=outside,
        distance_m=dist_m,
        recorded_at=datetime.utcnow(),
    )
    db.add(ping)
    await db.commit()

    interval = int(_os.environ.get("PING_INTERVAL_MINUTES", "30"))
    return {"status": "success", "next_ping_in_minutes": interval}


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

    # 1.5 Close the bootstrap window: only accounts awaiting their first
    # credential setup may use this endpoint.
    if not user.requires_password_reset:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Security initialization is closed for this account.")
        
    # 2. Update credentials
    user.hashed_password = get_password_hash(payload.new_password)
    user.hashed_duress_password = get_password_hash(payload.duress_password)
    user.requires_password_reset = False

    await db.commit()

    # Issue a short-lived initialization token so the just-initialized account
    # can complete MFA enrollment (/admin/mfa/setup + /admin/mfa/verify) without
    # a prior login session. The bootstrap window closes above (requires_password_reset
    # cleared), so this token can never be minted again for the account.
    from datetime import timedelta
    from .security import create_access_token
    init_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=timedelta(minutes=15),
    )

    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="PASSWORD_INITIALIZED",
                    tenant_id=getattr(user, "client_id", None),
                    target_type="user", target_id=str(user.id),
                    details=f"Primary and duress passwords set at first login for {payload.email}; temporary credential expired")
    await db.commit()

    return {
        "status": "success",
        "message": "Security credentials fully initialized. Temporary password has been expired.",
        "access_token": init_token
    }
