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
from sqlalchemy import select, func, delete, text, insert, literal, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import (
    User, Election, ElectionPU, AgentAssignment, AgentCheckIn,
    PollingUnit, Ward, LGA, State, Result, Client,
)
from .security import RequirePermission, log_audit

router = APIRouter(prefix="/admin", tags=["Elections"])

VALID_TYPES = {"general", "presidential", "gubernatorial", "senatorial",
               "house_of_reps", "lga"}
VALID_STATUSES = {"upcoming", "live", "closed"}

INTERNAL_CLIENT_ID = "civiclens-internal"


async def client_scope_election_ids(db: AsyncSession, user: User):
    """
    Election visibility for this admin: None = platform super-admin
    (cross-client, sees every election); otherwise the id list of the
    elections owned by the caller's client.
    """
    if getattr(user, "client_id", None) is None:
        return None
    rows = await db.execute(select(Election.id).where(Election.client_id == user.client_id))
    return [r[0] for r in rows.all()]


def assert_in_scope(election_id: str, scoped_ids):
    """Raise 404 (not 403 — don't reveal existence) for out-of-scope access."""
    if scoped_ids is not None and election_id not in scoped_ids:
        raise HTTPException(404, "Election not found.")


class ClientCreateSchema(BaseModel):
    name: str
    contact_email: Optional[str] = None
    notes: Optional[str] = None


def _client_to_dict(c: Client, counts: dict) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "contact_email": c.contact_email,
        "notes": c.notes,
        "elections": counts.get("elections", 0),
        "agents": counts.get("agents", 0),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/clients")
async def list_clients(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """
    Platform admins list every institution; a client admin sees only their
    own client.
    """
    stmt = select(Client).order_by(Client.created_at)
    if user.client_id is not None:
        stmt = stmt.where(Client.id == user.client_id)
    clients = (await db.execute(stmt)).scalars().all()

    counts = {}
    if clients:
        ids = [c.id for c in clients]
        e_rows = (await db.execute(
            select(Election.client_id, func.count())
            .where(Election.client_id.in_(ids)).group_by(Election.client_id))).all()
        a_rows = (await db.execute(
            select(User.client_id, func.count())
            .where(User.client_id.in_(ids), User.role == "agent")
            .group_by(User.client_id))).all()
        for cid, n in e_rows:
            counts.setdefault(cid, {})["elections"] = n
        for cid, n in a_rows:
            counts.setdefault(cid, {})["agents"] = n
    return {"clients": [_client_to_dict(c, counts.get(c.id, {})) for c in clients]}


@router.post("/clients", status_code=201)
async def create_client(
    payload: ClientCreateSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """Platform-admin only: client-admin accounts cannot create institutions."""
    if user.client_id is not None:
        raise HTTPException(status_code=403, detail="Only platform administrators may create clients.")
    name = payload.name.strip()
    existing = (await db.execute(select(Client).where(Client.name == name))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"A client named {name!r} already exists.")
    client = Client(name=name, contact_email=payload.contact_email, notes=payload.notes)
    db.add(client)
    await log_audit(db, actor_id=str(user.id), action="CLIENT_CREATE",
                    target_id=client.id, details=f"Created client {name!r}")
    await db.commit()
    await db.refresh(client)
    return _client_to_dict(client, {})


class ClientUpdateSchema(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/clients/{client_id}")
async def update_client(
    client_id: str,
    payload: ClientUpdateSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """Platform-admin only: rename or update a client's contact details."""
    if user.client_id is not None:
        raise HTTPException(status_code=403, detail="Only platform administrators may edit clients.")
    client = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found.")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(422, "Name must not be empty.")
        clash = (await db.execute(select(Client).where(Client.name == name, Client.id != client.id))).scalar_one_or_none()
        if clash:
            raise HTTPException(409, f"A client named {name!r} already exists.")
        client.name = name
    if payload.contact_email is not None:
        client.contact_email = payload.contact_email or None
    if payload.notes is not None:
        client.notes = payload.notes or None
    await log_audit(db, actor_id=str(user.id), action="CLIENT_UPDATE",
                    target_id=client.id, details=f"Updated client {client.name!r}")
    await db.commit()
    await db.refresh(client)
    return _client_to_dict(client, {})


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """Platform-admin only. Refuses while elections or accounts reference
    the client, so history can never be orphaned."""
    if user.client_id is not None:
        raise HTTPException(status_code=403, detail="Only platform administrators may delete clients.")
    client = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found.")
    e_n = (await db.execute(select(func.count()).select_from(Election)
                           .where(Election.client_id == client.id))).scalar_one()
    u_n = (await db.execute(select(func.count()).select_from(User)
                           .where(User.client_id == client.id))).scalar_one()
    if e_n or u_n:
        raise HTTPException(409,
                            f"Client still has {e_n} election(s) and {u_n} account(s) — "
                            "remove or reassign them first.")
    await log_audit(db, actor_id=str(user.id), action="CLIENT_DELETE",
                    target_id=client.id, details=f"Deleted client {client.name!r}")
    await db.delete(client)
    await db.commit()
    return {"status": "deleted", "id": client_id}


class ElectionCreateSchema(BaseModel):
    name: str
    code: str
    type: str = "general"
    # Platform admins only: owning client (defaults to the internal client).
    # Client admins cannot set this — their own client is enforced.
    client_id: Optional[str] = None
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
        "client_name": counts.get("client_name"),
    }


@router.get("/elections")
async def list_elections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_results")),
):
    # Client admins only ever see their own institution's elections; the
    # switcher in the admin portal renders exactly this list.
    stmt = select(Election).order_by(Election.created_at)
    if user.client_id is not None:
        stmt = stmt.where(Election.client_id == user.client_id)
    elections = (await db.execute(stmt)).scalars().all()

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

    # Platform admins see which institution each election belongs to; client
    # admins only ever list their own, so the label would be redundant noise.
    if user.client_id is None and elections:
        from .models import Client as _Client
        c_rows = (await db.execute(select(_Client.id, _Client.name))).all()
        c_map = {cid: name for cid, name in c_rows}
        for e in elections:
            counts.setdefault(e.id, {})["client_name"] = c_map.get(e.client_id)

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

    # Ownership: client admins can only ever create elections for their own
    # institution; platform admins pick a client (defaulting to internal).
    if user.client_id is not None:
        client_id = user.client_id
    else:
        client_id = payload.client_id or INTERNAL_CLIENT_ID
        client = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
        if not client:
            raise HTTPException(404, "Client not found.")

    election = Election(
        client_id=client_id,
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
    assert_in_scope(election.id, await client_scope_election_ids(db, user))

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
    assert_in_scope(election.id, await client_scope_election_ids(db, user))
    if not payload.state_ids and not payload.lga_ids:
        raise HTTPException(422, "Provide state_ids and/or lga_ids.")

    # Resolve the target PU set PURELY IN SQL. Materializing thousands of PU
    # ids into Python and replaying them as an IN(...) list OOM-killed
    # workers on whole-state scopes (956MB VM); the database does this set
    # work natively in one round-trip.
    conds = []
    if payload.state_ids:
        conds.append(LGA.state_id.in_(payload.state_ids))
    if payload.lga_ids:
        conds.append(Ward.lga_id.in_(payload.lga_ids))
    scope_select = (
        select(PollingUnit.id)
        .join(Ward, PollingUnit.ward_id == Ward.id)
        .join(LGA, Ward.lga_id == LGA.id)
        .where(or_(*conds))
    )
    n_pus = (await db.execute(
        select(func.count()).select_from(scope_select.subquery()))).scalar_one()
    if not n_pus:
        raise HTTPException(422, "The selected states/LGAs contain no polling units.")

    # Replace scope (single round-trip via DELETE + INSERT-from-SELECT)
    await db.execute(delete(ElectionPU).where(ElectionPU.election_id == election_id))
    await db.execute(
        insert(ElectionPU).from_select(
            ["election_id", "pu_id"],
            select(literal(election_id), PollingUnit.id)
            .join(Ward, PollingUnit.ward_id == Ward.id)
            .join(LGA, Ward.lga_id == LGA.id)
            .where(or_(*conds))
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
                    details=f"Scope set to {n_pus} PUs "
                            f"({len(payload.state_ids or [])} states, "
                            f"{len(payload.lga_ids or [])} LGAs); "
                            f"{getattr(removed, 'rowcount', '?')} assignments dropped")
    await db.commit()
    return {"status": "success", "election_id": election_id, "pus": n_pus}


@router.get("/elections/{election_id}/assignments")
async def list_election_assignments(
    election_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("view_agents")),
):
    assert_in_scope(election_id, await client_scope_election_ids(db, user))
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
    assert_in_scope(election.id, await client_scope_election_ids(db, user))
    # Tenancy: an agent can only ever be accredited within their own
    # institution's elections. Client admins may touch only their own
    # agents; platform admins may touch any agent but the election/agent
    # client must still match.
    if user.client_id is not None and agent.client_id != user.client_id:
        raise HTTPException(404, "Agent not found.")
    if agent.client_id is not None and agent.client_id != election.client_id:
        raise HTTPException(422, "This agent belongs to a different institution than the election.")
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
    assert_in_scope(assignment.election_id, await client_scope_election_ids(db, user))
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
