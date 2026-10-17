"""Audit log read API — tenant-scoped, same wall as every other screen.

Platform super-admins (client_id NULL) read the full chain and may filter by
tenant. Client admins are silently restricted to their own institution's
rows (they cannot name another tenant — the tenant_id parameter is ignored
for them, and no response field reveals other tenants' existence beyond the
rows themselves). Field agents have a separate, narrower endpoint that
exposes only their own activity.
"""
import csv
import hashlib
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import AuditLog, User
from .security import (AUDIT_GENESIS_HASH, RequirePermission, audit_canonical,
                       get_current_user)

router = APIRouter(tags=["Audit Log"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
EXPORT_CAP = 50000


def _parse_ts(raw: Optional[str], field: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(422, f"{field} must be an ISO-8601 timestamp")


def _row_dict(r: AuditLog) -> dict:
    return {
        "seq": r.seq,
        "at": r.timestamp.isoformat() + "Z" if r.timestamp else None,
        "actor_id": r.actor_id,
        "actor_role": r.actor_role,
        "tenant_id": r.tenant_id,
        "action": r.action_type,
        "target_type": r.target_type,
        "target_id": r.target_entity_id,
        "election_id": r.election_id,
        "details": r.details,
        "ip_address": r.ip_address,
        "device_fingerprint": r.device_fingerprint,
        "prev_hash": r.prev_hash,
        "row_hash": r.row_hash,
    }


async def _filtered_query(db: AsyncSession, user: User,
                          from_ts: Optional[datetime], to_ts: Optional[datetime],
                          action: Optional[str], actor_id: Optional[str],
                          election_id: Optional[str], tenant_id: Optional[str]):
    """Builds the scoped WHERE clause. Returns (stmt, scope) where scope is
    'platform' (unrestricted reader) or 'tenant' (forced to own client_id)."""
    scope = "platform" if user.client_id is None else "tenant"
    stmt = select(AuditLog)
    if scope == "tenant":
        stmt = stmt.where(AuditLog.tenant_id == user.client_id)
    elif tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if from_ts:
        stmt = stmt.where(AuditLog.timestamp >= from_ts)
    if to_ts:
        stmt = stmt.where(AuditLog.timestamp <= to_ts)
    if action:
        stmt = stmt.where(AuditLog.action_type.ilike(f"{action}%"))
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if election_id:
        stmt = stmt.where(AuditLog.election_id == election_id)
    return stmt, scope


@router.get("/admin/audit-logs")
async def list_audit_logs(
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    election_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_audit_logs")),
):
    frm, to = _parse_ts(from_ts, "from"), _parse_ts(to_ts, "to")
    stmt, scope = await _filtered_query(db, user, frm, to, action, actor_id,
                                        election_id, tenant_id)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(AuditLog.seq.desc()).limit(limit).offset(offset)
    )).scalars().all()
    tip = (await db.execute(
        select(AuditLog.row_hash).where(AuditLog.row_hash.isnot(None))
        .order_by(AuditLog.seq.desc()).limit(1))).scalar()
    return {
        "scope": scope,
        "total": total,
        "chain_tip": tip,
        "rows": [_row_dict(r) for r in rows],
    }


@router.get("/admin/audit-logs/verify")
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_audit_logs")),
):
    """Recomputes row hashes to detect tampering.

    Platform admins get a FULL-chain verification: every row's stored hash
    must match its content AND its prev_hash must equal the previous row's
    hash (genesis constant for the first). Tenant admins get a CONTENT check
    over their own rows (each stored row_hash must match its stored fields) —
    they cannot link across the tenant boundary, which is reported honestly
    in the response.
    """
    scope = "platform" if user.client_id is None else "tenant"
    stmt = select(AuditLog).where(AuditLog.row_hash.isnot(None))
    if scope == "tenant":
        stmt = stmt.where(AuditLog.tenant_id == user.client_id)
    stmt = stmt.order_by(AuditLog.seq.asc())
    rows = (await db.execute(stmt)).scalars().all()

    expected_prev = AUDIT_GENESIS_HASH
    checked = 0
    for r in rows:
        recomputed = hashlib.sha256(audit_canonical(
            r.seq, r.timestamp, r.actor_id, r.actor_role, r.tenant_id,
            r.action_type, r.target_type, r.target_entity_id, r.election_id,
            r.details, r.ip_address, r.device_fingerprint,
            r.prev_hash).encode()).hexdigest()
        if recomputed != r.row_hash:
            return {"scope": scope, "valid": False, "rows_checked": checked,
                    "first_break_seq": r.seq,
                    "reason": "row_hash mismatch — content altered"}
        if scope == "platform" and (r.prev_hash or AUDIT_GENESIS_HASH) != expected_prev:
            return {"scope": scope, "valid": False, "rows_checked": checked,
                    "first_break_seq": r.seq,
                    "reason": "prev_hash linkage broken — row inserted, reordered or deleted"}
        expected_prev = r.row_hash
        checked += 1
    return {"scope": scope, "valid": True, "rows_checked": checked,
            "note": None if scope == "platform"
                    else "tenant-scope content check; full cross-tenant linkage is platform-verified"}


CSV_FIELDS = ["seq", "at", "actor_id", "actor_role", "tenant_id", "action",
              "target_type", "target_id", "election_id", "details",
              "ip_address", "device_fingerprint", "prev_hash", "row_hash"]


@router.get("/admin/audit-logs/export")
async def export_audit_logs(
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    election_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_audit_logs")),
):
    """CSV export of the (scoped) audit log for the client's own records."""
    frm, to = _parse_ts(from_ts, "from"), _parse_ts(to_ts, "to")
    stmt, scope = await _filtered_query(db, user, frm, to, action, actor_id,
                                        election_id, tenant_id)
    rows = (await db.execute(
        stmt.order_by(AuditLog.seq.asc()).limit(EXPORT_CAP))).scalars().all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for r in rows:
        writer.writerow(_row_dict(r))
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="civiclens_audit_{scope}_{stamp}.csv"'})


@router.get("/audit-logs/me")
async def list_my_activity(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """A field agent's own activity trail — nothing beyond their own actor_id."""
    if user.role != "agent":
        raise HTTPException(status_code=403,
                            detail="Only field agents use this endpoint.")
    total = (await db.execute(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.actor_id == user.id))).scalar_one()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.actor_id == user.id)
        .order_by(AuditLog.seq.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return {"total": total, "rows": [_row_dict(r) for r in rows]}
