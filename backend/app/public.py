"""Public, read-only API for the citizen portal.

These endpoints serve the public dashboard under /public/ without any login.
They expose only aggregates (vote tallies, counts, percentages) and the
geographic hierarchy — never agent identities, wallet data, or per-submission
detail. The authenticated equivalents live in admin.py behind
RequirePermission; these must stay in sync with them deliberately, not by
accident.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import State, LGA, Ward, PollingUnit, Result, User

router = APIRouter(prefix="/api/public", tags=["Public Read-Only API"])


# ---------- geographic hierarchy (same shapes as /admin/geo/*) ----------

@router.get("/geo/states")
async def public_states(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(State).order_by(State.name))
    return [{"id": str(s.id), "name": s.name} for s in res.scalars().all()]


@router.get("/geo/states/{state_id}/lgas")
async def public_lgas(state_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(LGA).where(LGA.state_id == state_id).order_by(LGA.name))
    return [{"id": str(l.id), "name": l.name} for l in res.scalars().all()]


@router.get("/geo/lgas/{lga_id}/wards")
async def public_wards(lga_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Ward).where(Ward.lga_id == lga_id).order_by(Ward.name))
    return [{"id": str(w.id), "name": w.name} for w in res.scalars().all()]


@router.get("/geo/wards/{ward_id}/pus")
async def public_pus(ward_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PollingUnit).where(PollingUnit.ward_id == ward_id).order_by(PollingUnit.name))
    return [{"id": str(p.id), "name": p.name, "code": p.pu_code} for p in res.scalars().all()]


# ---------- public collation aggregates ----------

@router.get("/stats/collation")
async def public_stats(
    state_id: Optional[str] = None,
    lga_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    pu_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Aggregated tallies for the public dashboard. Same math as the admin
    endpoint in admin.py, minus anything workforce-related is kept aggregate
    (counts only) — no personal data is exposed here."""

    def apply_filters(stmt, table):
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
            stmt = stmt.join(Ward, PollingUnit.ward_id == Ward.id) \
                       .join(LGA, Ward.lga_id == LGA.id).filter(LGA.state_id == state_id)
        return stmt

    agent_count_stmt = select(func.count(User.id)).where(User.role == "agent")
    if any([state_id, lga_id, ward_id, pu_id]):
        agent_count_stmt = apply_filters(agent_count_stmt, User)
    agents_provisioned = (await db.execute(agent_count_stmt)).scalar() or 0

    votes_stmt = select(
        func.sum(Result.party_a_votes),
        func.sum(Result.party_b_votes),
        func.sum(Result.party_c_votes),
    )
    if any([state_id, lga_id, ward_id, pu_id]):
        votes_stmt = apply_filters(votes_stmt, Result)
    pa, pb, pc = (await db.execute(votes_stmt)).one()
    pa, pb, pc = pa or 0, pb or 0, pc or 0

    res_count_stmt = select(func.count(Result.id))
    if any([state_id, lga_id, ward_id, pu_id]):
        res_count_stmt = apply_filters(res_count_stmt, Result)
    total_results = (await db.execute(res_count_stmt)).scalar() or 0

    if total_results > 0:
        verified_stmt = res_count_stmt.where(Result.is_verified == True)
        verified_results = (await db.execute(verified_stmt)).scalar() or 0
        verified_percentage = round((verified_results / total_results) * 100, 1)
    else:
        verified_percentage = 0.0

    flagged_stmt = select(func.count(Result.id)).where(
        Result.is_flagged == True, Result.is_verified == False
    )
    if any([state_id, lga_id, ward_id, pu_id]):
        flagged_stmt = apply_filters(flagged_stmt, Result)
    flagged_count = (await db.execute(flagged_stmt)).scalar() or 0

    return {
        "total_votes": pa + pb + pc,
        "party_a": pa,
        "party_b": pb,
        "party_c": pc,
        "verified_percentage": verified_percentage,
        "agents_provisioned": agents_provisioned,
        "flagged_count": flagged_count,
    }
