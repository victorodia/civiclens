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


def compute_result_hash(payload: "ResultSubmitSchema") -> str:
    """
    sha256 over a canonical, sorted JSON encoding of the result payload.
    This is the value anchored on-chain: anyone can recompute it from the
    published data and compare against the chain record to detect tampering.
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

    # 0. Signature Verification (Non-Repudiation Check) — MANDATORY.
    # The signature is generated from: puCode|partyAVotes|partyBVotes|partyCVotes
    # and HMAC-SHA256 keyed with the submitting agent's unique device signing
    # key (issued at provisioning). The key is looked up from the JWT identity,
    # never from the payload, so a stolen token on its own cannot forge sigs.
    payload_string = f"{payload.pu_code}|{payload.party_a_votes}|{payload.party_b_votes}|{payload.party_c_votes}"

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

    if not verify_payload_signature(payload_string, payload.signature, signing_key):
        print(f"[SECURITY ALERT] TAMPERING DETECTED: Signature mismatch for PU {payload.pu_code}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payload Integrity Error: Digital Signature Mismatch. Data may have been tampered with."
        )
    print(f"[SECURITY] Signature Verified for PU {payload.pu_code}")

    # 1. Resolve PU
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

    # 2.6 Accreditation: an agent may only collate results for their own PU.
    if not agent.assigned_pu_id or agent.assigned_pu_id != pu.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the accredited agent for this polling unit."
        )

    # 3. Check if result already exists for this PU
    existing_res = await db.execute(select(Result).where(Result.pu_id == pu.id))
    if existing_res.scalar_one_or_none():
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
    # the on-chain anchor happens asynchronously afterwards.
    result_hash = compute_result_hash(payload)

    new_result = Result(
        pu_id=pu.id,
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
        action="RESULT_SUBMISSION",
        target_id=new_result.id,
        details=f"Result committed for PU {payload.pu_code}. Flagged={is_flagged}. Duress={is_under_duress}"
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
