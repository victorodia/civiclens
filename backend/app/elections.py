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
    PollingUnit, Ward, LGA, State, Result, Client, AgentLocationPing,
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


async def resolve_default_election(db: AsyncSession, agent: User):
    """Legacy clients send no election_id. Resolve the election they mean:

    1. the GENERAL registry default, if one exists (pre-multi-tenant
       installs); otherwise
    2. the SINGLE election the agent is accredited for — only when
       unambiguous (exactly one distinct assignment).

    Returns (election, assignment). (None, None) when the intent is
    ambiguous (zero or multiple assignments): the caller must refuse,
    because collating into the wrong race is exactly the mismatch the
    multi-election design exists to prevent.
    """
    gen = (await db.execute(select(Election).where(Election.code == "GENERAL"))).scalar_one_or_none()
    if gen:
        return gen, None
    rows = (await db.execute(
        select(AgentAssignment).where(AgentAssignment.agent_id == agent.id)
    )).scalars().all()
    by_election = {}
    for r in rows:
        by_election.setdefault(r.election_id, r)
    if len(by_election) == 1:
        eid = next(iter(by_election))
        election = (await db.execute(select(Election).where(Election.id == eid))).scalar_one_or_none()
        return election, by_election[eid]
    return None, None


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
    await db.flush()  # materialize client.id before it lands in the audit row
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="CLIENT_CREATE",
                    tenant_id=client.id,
                    target_type="client", target_id=client.id,
                    details=f"Created client {name!r}")
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
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="CLIENT_UPDATE",
                    tenant_id=client.id,
                    target_type="client", target_id=client.id,
                    details=f"Updated client {client.name!r}")
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
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="CLIENT_DELETE",
                    tenant_id=client.id,
                    target_type="client", target_id=client.id,
                    details=f"Deleted client {client.name!r}")
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
        "client_id": e.client_id,
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
            if client_id == INTERNAL_CLIENT_ID:
                # Fresh installs: the platform's own tenant row is seeded on
                # first use instead of 404-ing election creation.
                client = Client(id=INTERNAL_CLIENT_ID, name="CivicLens Internal")
                db.add(client)
                await db.flush()
            else:
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
    await db.flush()  # materialize election.id before it lands in the audit row
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="ELECTION_CREATE",
                    tenant_id=election.client_id,
                    election_id=election.id,
                    target_type="election", target_id=election.id,
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
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="ELECTION_STATUS",
                    tenant_id=election.client_id,
                    election_id=election.id,
                    target_type="election", target_id=election.id,
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

    # Replace scope (single round-trip via DELETE + INSERT-from-SELECT).
    # Bulk-load fast path: the inserted pu_ids are selected FROM polling_units
    # itself, so referential integrity is guaranteed by construction — skip
    # the per-row FK triggers. This cuts a whole-country save (177k rows)
    # from ~113s to a few seconds. Restored to 'origin' before the audit row.
    await db.execute(text("SET LOCAL session_replication_role = replica"))
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
    await db.execute(text("SET LOCAL session_replication_role = origin"))
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="ELECTION_SCOPE",
                    tenant_id=election.client_id,
                    election_id=election.id,
                    target_type="election", target_id=election.id,
                    details=f"Scope set to {n_pus} PUs "
                            f"({len(payload.state_ids or [])} states, "
                            f"{len(payload.lga_ids or [])} LGAs); "
                            f"{getattr(removed, 'rowcount', '?')} assignments dropped")
    await db.commit()
    return {"status": "success", "election_id": election_id, "pus": n_pus}


class ElectionDeleteSchema(BaseModel):
    admin_password: str
    totp_code: Optional[str] = None  # required only when the caller has 2FA enabled


@router.delete("/elections/{election_id}")
async def delete_election(
    election_id: str,
    payload: ElectionDeleteSchema,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(RequirePermission("provision_agents")),
):
    """
    Delete an election AND everything bound to it: its results (including
    evidence files on disk), check-ins, GPS pings, assignments and scope
    rows. Field agents whose ONLY accreditation was this election are
    trashed too; agents still assigned to other elections are kept and
    simply lose this one. Requires administrative re-authentication, plus
    the 2FA code when the caller has TOTP enabled.
    """
    from .security import verify_password
    import pyotp

    # 1. Administrative re-authentication.
    if not verify_password(payload.admin_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Election deletion aborted: incorrect administrative security key."
        )

    # 1b. MFA challenge — the client sends the password first; on this
    #     challenge it prompts for the TOTP code and retries with both.
    if user.is_2fa_enabled:
        if not payload.totp_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="2FA_CODE_REQUIRED")
        if not pyotp.TOTP(user.totp_secret).verify(payload.totp_code, valid_window=1):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid or expired 2FA code.")

    # 2. Resolve the election (client tenancy respected).
    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(404, "Election not found.")
    assert_in_scope(election.id, await client_scope_election_ids(db, user))

    # 3. Capture agents accredited for THIS election and evidence filenames
    #    BEFORE any rows are deleted.
    candidate_ids = [r[0] for r in (await db.execute(
        select(AgentAssignment.agent_id)
        .where(AgentAssignment.election_id == election_id)
        .distinct())).all()]
    media_rows = (await db.execute(text(
        "SELECT image_url, video_url FROM results WHERE election_id = :e"),
        {"e": election_id})).all()
    filenames = set()
    for row in media_rows:
        for u in (row[0], row[1]):
            if u:
                filenames.add(u.rsplit("/", 1)[-1])

    # 4. Child-before-parent purge of everything bound to the election.
    res = await db.execute(text("DELETE FROM results WHERE election_id = :e"), {"e": election_id})
    n_results = getattr(res, "rowcount", -1)
    await db.execute(text("DELETE FROM agent_checkins WHERE election_id = :e"), {"e": election_id})
    await db.execute(text("DELETE FROM agent_location_pings WHERE election_id = :e"), {"e": election_id})
    await db.execute(text("DELETE FROM agent_assignments WHERE election_id = :e"), {"e": election_id})
    await db.execute(text("DELETE FROM election_polling_units WHERE election_id = :e"), {"e": election_id})

    # 5. Evidence files off disk.
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

    # 6. Trash agents whose only accreditation was this election — an agent
    #    with ANY remaining footprint (other assignments, results, check-ins
    #    or pings anywhere) is kept.
    n_agents = 0
    if candidate_ids:
        has_footprint = (
            select(AgentAssignment.agent_id).where(AgentAssignment.agent_id == User.id).exists()
            | select(Result.agent_id).where(Result.agent_id == User.id).exists()
            | select(AgentCheckIn.agent_id).where(AgentCheckIn.agent_id == User.id).exists()
            | select(AgentLocationPing.agent_id).where(AgentLocationPing.agent_id == User.id).exists()
        )
        r = await db.execute(delete(User).where(User.id.in_(candidate_ids)).where(~has_footprint))
        n_agents = getattr(r, "rowcount", -1)

    # 7. The election itself + audit trail.
    await db.execute(text("DELETE FROM elections WHERE id = :e"), {"e": election_id})
    await log_audit(
        db,
        actor_id=str(user.id),
        actor_role=user.role,
        action="ELECTION_DELETE",
        tenant_id=election.client_id,
        election_id=election_id,
        target_type="election",
        target_id=election_id,
        details=f"Election {election.name!r} ({election.code}) deleted: {n_results} result(s), "
                f"{n_files} evidence file(s), {n_agents} exclusive agent account(s) trashed."
    )
    await db.commit()

    return {
        "status": "deleted",
        "election_id": election_id,
        "message": f"Election {election.name} and everything bound to it deleted "
                   f"({n_results} results, {n_files} evidence files, {n_agents} exclusive agents)."
    }


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
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="AGENT_ASSIGN",
                    tenant_id=election.client_id,
                    election_id=election.id,
                    target_type="agent_assignment", target_id=agent.id,
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
    _u_election = (await db.execute(select(Election).where(Election.id == assignment.election_id))).scalar_one_or_none()
    await log_audit(db, actor_id=str(user.id), actor_role=user.role,
                    action="AGENT_UNASSIGN",
                    tenant_id=_u_election.client_id if _u_election else None,
                    election_id=assignment.election_id,
                    target_type="agent_assignment", target_id=agent_id,
                    details=f"Removed assignment {assignment_id}")
    await db.commit()
    return {"status": "success"}
