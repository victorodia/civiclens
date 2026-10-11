"""
Multi-election administration.

An election is a monitored race (gubernatorial, senatorial, LGA, ...) with its
own scope (set of polling units), its own party labels, and its own pool of
accredited agents. Several elections can be live at once; agents hold one
assignment per election and check in / submit strictly within an election
context.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, delete, text, insert, literal
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import (
    User, Election, ElectionPU, AgentAssignment, AgentCheckIn,
    PollingUnit, Ward, LGA, State, Result,
)
from .security import RequirePermission, log_audit

router = APIRouter(prefix="/admin", tags=["Elections"])

VALID_TYPES = {"general", "presidential", "gubernatorial", "senatorial",
               "house_of_reps", "lga"}
VALID_STATUSES = {"upcoming", "live", "closed"}


class ElectionCreateSchema(BaseModel):
    name: str
    code: str
    type: str = "general"
    party_a_name: Optional[str] = None
    party_b_name: Optional[str] = None
    party_c_name: Optional[str] = None


class ElectionStatusSchema(BaseModel):
    status: str


class ElectionScopeSchema(BaseModel):
    # Polling units are materialized from whole states and/or individual LGAs,
    # so a senatorial district (an arbitrary set of LGAs) scopes exactly like
    # a statewide race.
    state_ids: Optional[List[str]] = None
    lga_ids: Optional[List[str]] = None


class AssignmentCreateSchema(BaseModel):
    election_id: str
    pu_id: str


def _election_to_dict(e: Election, counts: dict) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "code": e.code,
        "type": e.type,
        "status": e.status,
        "party_a_name": e.party_a_name,
        "party_b_name": e.party_b_name,
        "party_c_name": e.party_c_name,
        "agents": counts.get("agents", 0),
        "submitted": counts.get("submitted", 0),
        "pus": counts.get("pus", 0),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/elections")
async def list_elections(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePermission("view_results")),
):
    elections = (await db.execute(select(Election).order_by(Election.created_at))).scalars().all()

    counts = {}
    if elections:
        ids = [e.id for e in elections]
        agent_rows = (await db.execute(
            select(AgentAssignment.election_id, func.count())
            .where(AgentAssignment.election_id.in_(ids))
            .group_by(AgentAssignment.election_id))).all()
        submitted_rows = (await db.execute(
            select(Result.election_id, func.count())
            .where(Result.election_id.in_(ids))
            .group_by(Result.election_id))).all()
        pu_rows = (await db.execute(
            select(ElectionPU.election_id, func.count())
            .where(ElectionPU.election_id.in_(ids))
            .group_by(ElectionPU.election_id))).all()
        for eid, n in agent_rows:
            counts.setdefault(eid, {})["agents"] = n
        for eid, n in submitted_rows:
            counts.setdefault(eid, {})["submitted"] = n
        for eid, n in pu_rows:
            counts.setdefault(eid, {})["pus"] = n

    return {"elections": [_election_to_dict(e, counts.get(e.id, {})) for e in elections]}


@router.post("/elections", status_code=201)
async def create_election(
    payload: ElectionCreateSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    code = payload.code.strip().upper()
    if payload.type not in VALID_TYPES:
        raise HTTPException(422, f"type must be one of {sorted(VALID_TYPES)}")
    existing = (await db.execute(select(Election).where(Election.code == code))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Election code {code} already exists.")

    election = Election(
        name=payload.name.strip(),
        code=code,
        type=payload.type,
        status="upcoming",
        party_a_name=payload.party_a_name or "Party A",
        party_b_name=payload.party_b_name or "Party B",
        party_c_name=payload.party_c_name or "Party C",
    )
    db.add(election)
    await log_audit(db, actor_id=str(user.id), action="ELECTION_CREATE",
                    target_id=election.id,
                    details=f"Created election {code} ({payload.type})")
    await db.commit()
    await db.refresh(election)
    return _election_to_dict(election, {})


@router.put("/elections/{election_id}/status")
async def set_election_status(
    election_id: str,
    payload: ElectionStatusSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(VALID_STATUSES)}")
    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(404, "Election not found.")

    election.status = payload.status
    await log_audit(db, actor_id=str(user.id), action="ELECTION_STATUS",
                    target_id=election.id,
                    details=f"Status {election.code} -> {payload.status}")
    await db.commit()
    return {"status": "success", "election_id": election.id, "new_status": payload.status}


@router.post("/elections/{election_id}/scope")
async def set_election_scope(
    election_id: str,
    payload: ElectionScopeSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """
    (Re)materialize the election's polling-unit scope from whole states
    and/or individual LGAs. Replaces any previous scope. Assignments to PUs
    that leave the scope are removed.
    """
    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(404, "Election not found.")
    if not payload.state_ids and not payload.lga_ids:
        raise HTTPException(422, "Provide state_ids and/or lga_ids.")

    # Resolve the target PU set
    pu_ids = set()
    if payload.state_ids:
        rows = (await db.execute(
            select(PollingUnit.id)
            .join(Ward, PollingUnit.ward_id == Ward.id)
            .join(LGA, Ward.lga_id == LGA.id)
            .where(LGA.state_id.in_(payload.state_ids)))).all()
        pu_ids.update(r[0] for r in rows)
    if payload.lga_ids:
        rows = (await db.execute(
            select(PollingUnit.id)
            .join(Ward, PollingUnit.ward_id == Ward.id)
            .where(Ward.lga_id.in_(payload.lga_ids)))).all()
        pu_ids.update(r[0] for r in rows)
    if not pu_ids:
        raise HTTPException(422, "The selected states/LGAs contain no polling units.")

    # Replace scope (single round-trip via DELETE + INSERT-from-SELECT)
    await db.execute(delete(ElectionPU).where(ElectionPU.election_id == election_id))
    await db.execute(
        insert(ElectionPU).from_select(
            ["election_id", "pu_id"],
            select(literal(election_id), PollingUnit.id).where(PollingUnit.id.in_(pu_ids))
        )
    )
    # Drop assignments that fell outside the new scope
    removed = await db.execute(
        delete(AgentAssignment)
        .where(AgentAssignment.election_id == election_id)
        .where(AgentAssignment.pu_id.notin_(select(ElectionPU.pu_id)
                                            .where(ElectionPU.election_id == election_id)))
    )
    await log_audit(db, actor_id=str(user.id), action="ELECTION_SCOPE",
                    target_id=election.id,
                    details=f"Scope set to {len(pu_ids)} PUs "
                            f"({len(payload.state_ids or [])} states, "
                            f"{len(payload.lga_ids or [])} LGAs); "
                            f"{getattr(removed, 'rowcount', '?')} assignments dropped")
    await db.commit()
    return {"status": "success", "election_id": election_id, "pus": len(pu_ids)}


@router.get("/elections/{election_id}/assignments")
async def list_election_assignments(
    election_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePermission("view_agents")),
):
    rows = (await db.execute(
        select(AgentAssignment, User, PollingUnit)
        .join(User, AgentAssignment.agent_id == User.id)
        .join(PollingUnit, AgentAssignment.pu_id == PollingUnit.id)
        .where(AgentAssignment.election_id == election_id))).all()
    return {"assignments": [{
        "assignment_id": a.id,
        "agent_id": u.id,
        "agent_email": u.email,
        "agent_name": u.full_name,
        "pu_id": p.id,
        "pu_code": p.pu_code,
        "pu_name": p.name,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a, u, p in rows]}


@router.post("/agents/{agent_id}/assignments", status_code=201)
async def create_assignment(
    agent_id: str,
    payload: AssignmentCreateSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    agent = (await db.execute(select(User).where(User.id == agent_id))).scalar_one_or_none()
    if not agent or agent.role != "agent":
        raise HTTPException(404, "Agent not found.")
    election = (await db.execute(select(Election).where(Election.id == payload.election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(404, "Election not found.")
    in_scope = (await db.execute(select(ElectionPU).where(
        ElectionPU.election_id == election.id,
        ElectionPU.pu_id == payload.pu_id))).scalar_one_or_none()
    if not in_scope:
        raise HTTPException(422, "This polling unit is outside the election's scope. Set the scope first.")
    clash = (await db.execute(select(AgentAssignment).where(
        AgentAssignment.election_id == election.id,
        AgentAssignment.pu_id == payload.pu_id))).scalar_one_or_none()
    if clash:
        raise HTTPException(409, "Another agent is already accredited for this PU in this election.")

    assignment = AgentAssignment(agent_id=agent.id, election_id=election.id, pu_id=payload.pu_id)
    db.add(assignment)
    # Keep the legacy user-row pointer in sync so older admin views keep working
    agent.assigned_pu_id = payload.pu_id
    await log_audit(db, actor_id=str(user.id), action="AGENT_ASSIGN",
                    target_id=agent.id,
                    details=f"Agent {agent.email} -> {election.code} / PU {payload.pu_id}")
    await db.commit()
    await db.refresh(assignment)
    return {"status": "success", "assignment_id": assignment.id}


@router.delete("/agents/{agent_id}/assignments/{assignment_id}")
async def delete_assignment(
    agent_id: str,
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    assignment = (await db.execute(select(AgentAssignment).where(
        AgentAssignment.id == assignment_id,
        AgentAssignment.agent_id == agent_id))).scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found.")
    # Deactivate any live check-in session for that election
    await db.execute(
        text("UPDATE agent_checkins SET is_active = false "
             "WHERE agent_id = :a AND election_id = :e AND is_active = true"),
        {"a": agent_id, "e": assignment.election_id},
    )
    await db.delete(assignment)
    await log_audit(db, actor_id=str(user.id), action="AGENT_UNASSIGN",
                    target_id=agent_id, details=f"Removed assignment {assignment_id}")
    await db.commit()
    return {"status": "success"}
