import asyncio
import hashlib
import json
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

from .db import get_db, AsyncSessionLocal
from .models import Result, PollingUnit, User
from .security import get_current_user, check_user_status, verify_payload_signature, log_audit

router = APIRouter(prefix="/results", tags=["Result Collation"])


async def _token_claims(authorization: Optional[str] = Header(None)) -> dict:
    """
    Decode the raw JWT claims. Used to surface the silent duress flag that
    login embeds in the token when an agent authenticates under coercion.
    """
    from .security import SECRET_KEY, ALGORITHM
    from jose import jwt as jose_jwt
    if not authorization:
        return {}
    try:
        token = authorization.replace("Bearer ", "")
        return jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return {}


def compute_result_hash(payload: "ResultSubmitSchema", election_code: Optional[str] = None) -> str:
    """
    sha256 over a canonical, sorted JSON encoding of the result payload.
    This is the value anchored on-chain: anyone can recompute it from the
    published data and compare against the chain record to detect tampering.
    The election code is part of the commitment, so the same tally submitted
    under two different elections yields two distinct, independently
    verifiable hashes.
    """
    canonical = {
        "agent_email": payload.agent_email,
        "captured_at": payload.captured_at,
        "party_a_votes": payload.party_a_votes,
        "party_b_votes": payload.party_b_votes,
        "party_c_votes": payload.party_c_votes,
        "pu_code": payload.pu_code,
        "total_valid": payload.total_valid,
    }
    if election_code:
        canonical["election_code"] = election_code
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return "0x" + digest


def _anchor_sync(result_hash: str) -> str:
    # The polygon module pulls in web3 (a ~30-60s CPU import). It MUST be
    # imported inside the worker thread — an import on the event loop
    # blocked a worker past gunicorn's timeout and got it SIGKILLed mid-submit.
    from .polygon import sync_anchor_hash
    return sync_anchor_hash(result_hash)


async def _anchor_onchain(result_id: str, result_hash: str) -> None:
    """
    Background task: anchor the result hash on Polygon, then record the tx id.
    Runs in a separate session so a chain/RPC failure never blocks or rolls
    back the submission. If anchoring fails, the hash remains stored and the
    anchor can be retried later.
    """
    try:
        tx_id = await asyncio.to_thread(_anchor_sync, result_hash)
        print(f"[BLOCKCHAIN] Anchored result {result_id} in tx {tx_id}")
    except Exception as e:
        # InsufficientGasError, RPC outages, timeouts — all non-fatal here.
        print(f"[BLOCKCHAIN] Anchoring failed for result {result_id}: {e}")
        return

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Result)
                .where(Result.id == result_id)
                .values(blockchain_tx_id=tx_id)
            )
            await session.commit()
    except Exception as e:
        print(f"[BLOCKCHAIN] Anchored ({tx_id}) but failed to record tx for {result_id}: {e}")
class ResultSubmitSchema(BaseModel):
    pu_code: str
    agent_email: str
    party_a_votes: int
    party_b_votes: int
    party_c_votes: int
    total_valid: int
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    ai_party_a_votes: Optional[int] = None
    ai_party_b_votes: Optional[int] = None
    ai_party_c_votes: Optional[int] = None
    ai_confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    captured_at: str # ISO Timestamp from client
    # Election this result belongs to. The election is ALWAYS resolved
    # server-side (never trusted from the client alone): when absent, the
    # submission binds to the default GENERAL election for legacy apps.
    election_id: Optional[str] = None

    # ADVANCED SECURITY FIELDS
    signature: Optional[str] = None
    signed_timestamp: Optional[str] = None

@router.post("/submit")
async def submit_election_result(
    payload: ResultSubmitSchema,
    db: AsyncSession = Depends(get_db),
    agent: User = Depends(get_current_user),
    claims: dict = Depends(_token_claims),
    x_device_fingerprint: Optional[str] = Header(None),
):
    """
    Submits a final result from an agent.
    Requires a valid agent JWT; the submitter is the JWT identity, never the
    payload. Enforces device binding, PU accreditation, and WORM immutability.
    """

    # 0. Resolve the election FIRST — every downstream check (signature,
    # accreditation, muster roll, dedupe) binds to it. Explicit election_id
    # wins; a missing election_id means a legacy app and binds to the default
    # election — GENERAL if the registry still has one, else the single
    # election the agent is accredited for (refused as 409 when ambiguous).
    from .models import Election, AgentAssignment, AgentCheckIn
    from .elections import resolve_default_election
    if payload.election_id:
        election_res = await db.execute(select(Election).where(Election.id == payload.election_id))
        election = election_res.scalar_one_or_none()
        if not election:
            raise HTTPException(status_code=404, detail="Unknown election.")
    else:
        election, _legacy_assignment = await resolve_default_election(db, agent)
    if not election:
        raise HTTPException(status_code=409, detail="No election is configured on this server.")

    if election.status != "live":
        print(f"[SECURITY] Submission rejected: election {election.code} is {election.status}")
        # 409 (not 403): an upcoming/closed election is a TEMPORAL state,
        # not an authorization failure. The agent app keeps these drafts
        # queued and retries; a 403 would quarantine them forever.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"[ELECTION_NOT_OPEN] Submissions for {election.name} are not open yet (election is {election.status})."
        )

    # 1. Signature Verification (Non-Repudiation + Cross-Election Binding).
    # The signed string is puCode|ELECTIONCODE|A|B|C: the election code is
    # INSIDE the signature, so a payload minted for election A is
    # cryptographically invalid for election B — the client cannot lie about
    # which election it is reporting for. Legacy apps (no election context)
    # are accepted only on the default GENERAL election with the old
    # 4-field string; they can never reach an election-scoped race.
    payload_string = f"{payload.pu_code}|{election.code}|{payload.party_a_votes}|{payload.party_b_votes}|{payload.party_c_votes}"
    legacy_payload_string = f"{payload.pu_code}|{payload.party_a_votes}|{payload.party_b_votes}|{payload.party_c_votes}"

    if not payload.signature:
        print(f"[SECURITY ALERT] Unsigned submission attempt for PU {payload.pu_code}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payload Integrity Error: Missing Digital Signature."
        )

    signing_key = getattr(agent, "device_signing_key", None)
    if not signing_key:
        print(f"[SECURITY ALERT] Agent {agent.email} has no device signing key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not fully provisioned: no signing key on record."
        )

    signature_ok = verify_payload_signature(payload_string, payload.signature, signing_key)
    if not signature_ok and election.code == "GENERAL":
        # Legacy-format signature, default election only.
        signature_ok = verify_payload_signature(legacy_payload_string, payload.signature, signing_key)
    if not signature_ok:
        print(f"[SECURITY ALERT] TAMPERING DETECTED: Signature mismatch for PU {payload.pu_code} (election {election.code})")
        await log_audit(
            db,
            actor_id=agent.id,
            actor_role="agent",
            action="SIGNATURE_REJECT",
            tenant_id=election.client_id,
            election_id=election.id,
            target_type="result",
            target_id=payload.pu_code,
            details=f"Signature mismatch on submission. Election={election.code}, election_id_in_payload={payload.election_id}",
            device_fingerprint=x_device_fingerprint,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payload Integrity Error: Digital Signature Mismatch. Data may have been tampered with or signed for a different election."
        )
    print(f"[SECURITY] Signature Verified for PU {payload.pu_code} (election {election.code})")

    # 2. Resolve PU
    pu_res = await db.execute(select(PollingUnit).where(PollingUnit.pu_code == payload.pu_code))
    pu = pu_res.scalar_one_or_none()
    if not pu:
        raise HTTPException(status_code=404, detail=f"Polling Unit {payload.pu_code} not found in registry.")

    # 2. Authenticated Identity: the agent is whoever the JWT belongs to.
    if agent.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only provisioned field agents may submit results."
        )
    if payload.agent_email and payload.agent_email.lower() != agent.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payload identity does not match the authenticated agent."
        )

    # 2.5 Kill-Switch & Device Binding: the fingerprint must come from the
    # request header and match the device registered at provisioning time.
    if not await check_user_status(str(agent.id), x_device_fingerprint, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Agent account is inactive or device is unauthorized."
        )

    # 2.6 Accreditation: an agent may only collate results for a PU they are
    # assigned to IN THIS ELECTION. The same agent covering the same PU in a
    # governorship and a senatorial race holds two separate assignments;
    # either race rejects a submission lacking its own assignment.
    assignment_res = await db.execute(select(AgentAssignment).where(
        AgentAssignment.agent_id == agent.id,
        AgentAssignment.election_id == election.id,
        AgentAssignment.pu_id == pu.id,
    ))
    assignment = assignment_res.scalar_one_or_none()
    if not assignment:
        legacy_ok = (election.code == "GENERAL" and agent.assigned_pu_id == pu.id)
        if not legacy_ok:
            print(f"[SECURITY] Submission rejected: {agent.email} not accredited for PU {payload.pu_code} in {election.code}")
            await log_audit(
                db,
                actor_id=agent.id,
                actor_role="agent",
                action="ACCREDITATION_REJECT",
                tenant_id=election.client_id,
                election_id=election.id,
                target_type="result",
                target_id=payload.pu_code,
                details=f"Agent lacks an assignment for election {election.code} at this PU",
                device_fingerprint=x_device_fingerprint,
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You are not the accredited agent for this polling unit in {election.name}."
            )

    # 2.7 Muster-Roll Gate: an agent must have "Verified Entry" (checked in)
    # for THIS election before results can be collated, and the check-in
    # session must still be fresh. The session also pins the PU: a session
    # opened for the senatorial race cannot validate a governorship
    # submission.
    import os as _os
    max_age_hours = float(_os.environ.get("CHECKIN_MAX_AGE_HOURS", "4"))
    session_res = await db.execute(select(AgentCheckIn).where(
        AgentCheckIn.agent_id == agent.id,
        AgentCheckIn.election_id == election.id,
        AgentCheckIn.is_active == True,
    ).order_by(AgentCheckIn.checked_in_at.desc()))
    session = session_res.scalars().first()

    check_in_time, session_pu_id = None, None
    if session:
        check_in_time, session_pu_id = session.checked_in_at, session.pu_id
    elif election.code == "GENERAL" and agent.is_on_site:
        # Legacy fallback: user-row flags from before per-election sessions.
        check_in_time, session_pu_id = agent.last_check_in, agent.assigned_pu_id

    if check_in_time is None:
        print(f"[SECURITY] Submission rejected: agent {agent.email} has not verified entry for {election.code}")
        await log_audit(
            db,
            actor_id=agent.id,
            actor_role="agent",
            action="MUSTER_GATE_REJECT",
            tenant_id=election.client_id,
            election_id=election.id,
            target_type="result",
            target_id=payload.pu_code,
            details=f"Submission blocked: no Verify Entry session for election {election.code}",
            device_fingerprint=x_device_fingerprint,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You must Verify Entry at your polling unit before sending results."
        )
    check_in_age = (datetime.utcnow() - check_in_time).total_seconds() / 3600
    if check_in_age > max_age_hours:
        print(f"[SECURITY] Submission rejected: check-in stale ({check_in_age:.1f}h) for {agent.email} / {election.code}")
        await log_audit(
            db,
            actor_id=agent.id,
            actor_role="agent",
            action="MUSTER_STALE_REJECT",
            tenant_id=election.client_id,
            election_id=election.id,
            target_type="result",
            target_id=payload.pu_code,
            details=f"Submission blocked: Verify Entry session {check_in_age:.1f}h old (max {max_age_hours}h) for election {election.code}",
            device_fingerprint=x_device_fingerprint,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: Your entry verification has expired ({int(check_in_age)}h old). Verify Entry again before sending results."
        )
    if session_pu_id != pu.id:
        print(f"[SECURITY] Submission rejected: check-in session PU mismatch for {agent.email} ({election.code})")
        await log_audit(
            db,
            actor_id=agent.id,
            actor_role="agent",
            action="SESSION_PU_MISMATCH",
            tenant_id=election.client_id,
            election_id=election.id,
            target_type="result",
            target_id=payload.pu_code,
            details=f"Check-in session is for a different PU/election than the submission target. Election={election.code}",
            device_fingerprint=x_device_fingerprint,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Your verified entry does not match this polling unit for this election."
        )

    # 2.8 Presence-trail check (GPS breadcrumbs). The portal pings every
    # PING_INTERVAL_MINUTES (default 30) between Verify Entry and submission.
    # Only pings belonging to THIS election's session count — a trail built
    # for the senatorial race must not satisfy the governorship's presence
    # check. A thin trail FLAGS the result for the situation room — it never
    # blocks: GPS drift, dead batteries and backgrounded apps make a hard
    # gate unsafe.
    ping_interval_h = float(_os.environ.get("PING_INTERVAL_MINUTES", "30")) / 60.0
    hours_on_site = check_in_age  # computed by the freshness gate above
    from .models import AgentLocationPing
    pings_res = await db.execute(select(AgentLocationPing).where(
        AgentLocationPing.agent_id == agent.id,
        AgentLocationPing.election_id == election.id,
        AgentLocationPing.recorded_at >= check_in_time))
    pings = pings_res.scalars().all()
    expected = int(hours_on_site / ping_interval_h) if ping_interval_h > 0 else 0
    required = max(0, expected - 1)  # one missed ping of grace
    trail_ok = len(pings) >= required
    if trail_ok and hours_on_site >= 1.5:
        newest = max(p.recorded_at for p in pings) if pings else check_in_time
        trail_ok = (datetime.utcnow() - newest).total_seconds() <= 75 * 60
    gps_trail_flag = not trail_ok
    if gps_trail_flag:
        print(f"[SECURITY] Thin GPS trail for {agent.email} ({election.code}): "
              f"{len(pings)} pings in {hours_on_site:.1f}h (expected ~{expected})")

    # 3. Check if a result already exists for this PU in THIS election. The
    # same PU reports independently per election, so uniqueness is
    # (pu_id, election_id) — the senatorial result never collides with the
    # governorship result at the same PU.
    existing_res = await db.execute(select(Result).where(
        Result.pu_id == pu.id,
        Result.election_id == election.id))
    if existing_res.scalar_one_or_none():
        await log_audit(
            db,
            actor_id=agent.id,
            actor_role="agent",
            action="WORM_DUPLICATE_REJECT",
            tenant_id=election.client_id,
            election_id=election.id,
            target_type="result",
            target_id=payload.pu_code,
            details=f"Duplicate submission rejected (409): PU {payload.pu_code} already reported for {election.code}",
            device_fingerprint=x_device_fingerprint,
        )
        await db.commit()
        raise HTTPException(
            status_code=409, 
            detail="A result has already been collated for this Polling Unit. Collated data is immutable."
        )

    # 4. Create Result
    try:
        captured_dt = datetime.fromisoformat(payload.captured_at.replace('Z', '+00:00'))
        # asyncpg/timestamp columns require naive UTC — portals send ISO strings
        # with Z (offset-aware), which crashes the insert with
        # "can't subtract offset-naive and offset-aware datetimes".
        captured_dt = captured_dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        captured_dt = datetime.utcnow()

    # AI Flagging Heuristic: Flag for human review if agent and AI numbers diverge
    is_flagged = False
    if payload.ai_party_a_votes is not None:
        diff_a = abs(payload.party_a_votes - payload.ai_party_a_votes)
        diff_b = abs(payload.party_b_votes - payload.ai_party_b_votes)
        diff_c = abs(payload.party_c_votes - payload.ai_party_c_votes)
        
        # We flag if any party's count differs by more than 5 votes
        if any([diff_a > 5, diff_b > 5, diff_c > 5]):
            is_flagged = True

    # 4.5 Blockchain commitment: hash the canonical payload before persisting.
    # The hash is written in the same commit as the result (WORM-friendly);
    # the on-chain anchor happens asynchronously afterwards. The election
    # code goes into the commitment so each race's tally anchors separately.
    result_hash = compute_result_hash(payload, election.code)

    new_result = Result(
        pu_id=pu.id,
        election_id=election.id,
        agent_id=agent.id,
        party_a_votes=payload.party_a_votes,
        party_b_votes=payload.party_b_votes,
        party_c_votes=payload.party_c_votes,
        total_valid_votes=payload.total_valid,
        
        # Store AI verification breadcrumbs
        ai_party_a_votes=payload.ai_party_a_votes,
        ai_party_b_votes=payload.ai_party_b_votes,
        ai_party_c_votes=payload.ai_party_c_votes,
        ai_confidence=payload.ai_confidence,
        is_flagged=is_flagged,
        gps_trail_flag=gps_trail_flag,

        image_url=payload.image_url,
        video_url=payload.video_url,
        
        # Submission Telemetry
        latitude=payload.latitude,
        longitude=payload.longitude,

        captured_at=captured_dt,
        uploaded_at=datetime.utcnow(),
        blockchain_hash=result_hash
    )

    # 4.6 Duress: if the login JWT carried the silent duress flag, the
    # submission is accepted (so the coercer sees no error) but permanently
    # marked compromised for the situation room.
    is_under_duress = bool(claims.get("duress_flag"))
    if is_under_duress:
        new_result.is_compromised = True
        print(f"[SECURITY] Duress-flagged submission recorded for PU {payload.pu_code}")

    db.add(new_result)

    # 5. Audit Logging (WORM Compliance)
    await log_audit(
        db,
        actor_id=agent.id,
        actor_role="agent",
        action="RESULT_SUBMISSION",
        tenant_id=election.client_id,
        election_id=election.id,
        target_type="result",
        target_id=new_result.id,
        details=f"Result committed for PU {payload.pu_code} (election {election.code}). Flagged={is_flagged}. Duress={is_under_duress}. GpsTrailFlag={gps_trail_flag}",
        device_fingerprint=x_device_fingerprint,
    )

    await db.commit()
    await db.refresh(new_result)

    print(f"[COLLATION] New result committed: PU={payload.pu_code}, Total={payload.total_valid}")

    # 6. Anchor the commitment hash on Polygon in the background (non-blocking).
    asyncio.create_task(_anchor_onchain(new_result.id, result_hash))

    return {
        "status": "success",
        "result_id": new_result.id,
        "blockchain_hash": result_hash,
        "message": "Result successfully collated and signed. Hash anchored on-chain."
    }
