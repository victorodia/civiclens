"""Tenancy leak test: a client admin must not even learn that other clients
exist — every cross-client path returns 404 (or 403 for platform-only
operations), while own-client operations keep working.

    docker exec -w /app -e PYTHONPATH=/app civiclens-backend python /tmp/test_tenancy_wall.py
"""
import asyncio
import uuid

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy import select as sa_select

from app.db import AsyncSessionLocal
from app.models import Client, User
from app.security import get_password_hash
from app.admin import (
    RoleSchema, RotateKeySchema, RevokeSchema,
    factory_reset_system, get_system_users, create_system_user,
    update_system_user, delete_system_user, setup_mfa,
    rotate_agent_signing_key, revoke_agent, purge_agent, reactivate_agent,
    create_role, update_role, delete_role,
    SystemUserCreate, SystemUserUpdate,
)
from app.main import _ElectionConfigSchema, update_election_config

FAILED = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


async def expect(fn, status):
    try:
        await fn()
        return None
    except HTTPException as ex:
        return ex.status_code


async def main():
    async with AsyncSessionLocal() as db:
        ca = Client(id=str(uuid.uuid4()), name="ZZ WALL CLIENT A")
        cb = Client(id=str(uuid.uuid4()), name="ZZ WALL CLIENT B")
        db.add_all([ca, cb])
        await db.commit()

        pw_hash = get_password_hash("Sekret#123")
        admin_a = User(id=str(uuid.uuid4()), email=f"zz-wa-{uuid.uuid4().hex[:6]}@t.invalid",
                       hashed_password=pw_hash, full_name="ZZ WALL ADMIN A", role="admin", client_id=ca.id)
        admin_b = User(id=str(uuid.uuid4()), email=f"zz-wb-{uuid.uuid4().hex[:6]}@t.invalid",
                       hashed_password="x", full_name="ZZ WALL ADMIN B", role="admin", client_id=cb.id)
        plat = User(id=str(uuid.uuid4()), email=f"zz-wp-{uuid.uuid4().hex[:6]}@t.invalid",
                    hashed_password="x", full_name="ZZ WALL PLAT", role="admin", client_id=None)
        agent_a = User(id=str(uuid.uuid4()), email=f"zz-ag-a-{uuid.uuid4().hex[:6]}@t.invalid",
                       hashed_password="x", full_name="ZZ WALL AGENT A", role="agent", client_id=ca.id,
                       device_signing_key="k" * 32, device_fingerprint="fp", is_active=True)
        agent_b = User(id=str(uuid.uuid4()), email=f"zz-ag-b-{uuid.uuid4().hex[:6]}@t.invalid",
                       hashed_password="x", full_name="ZZ WALL AGENT B", role="agent", client_id=cb.id,
                       device_signing_key="k" * 32, device_fingerprint="fp", is_active=True)
        db.add_all([admin_a, admin_b, plat, agent_a, agent_b])
        await db.commit()

        # ── the wall: cross-client attempts must 404/403 ──
        st = await expect(lambda: factory_reset_system(RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a), 403)
        check("factory-reset as client admin -> 403", st == 403)

        users_a = await get_system_users(db=db, user=admin_a)
        emails = {u["email"] for u in users_a}
        check("system/users as client admin -> own client only",
              admin_a.email in emails and admin_b.email not in emails and plat.email not in emails)

        nu = await create_system_user(SystemUserCreate(
            email=f"zz-new-{uuid.uuid4().hex[:6]}@t.invalid", full_name="ZZ WALL NEW",
            role="analyst", password="Temp#12345"), db=db, user=admin_a)
        new_row = (await db.execute(sa_select(User).where(User.id == nu["id"]))).scalar_one()
        check("client admin creates staff bound to own client", new_row.client_id == ca.id)

        st = await expect(lambda: update_system_user(admin_b.id, SystemUserUpdate(full_name="HACKED"), db=db, user=admin_a), 404)
        check("update foreign admin -> 404", st == 404)
        st = await expect(lambda: update_system_user(plat.id, SystemUserUpdate(full_name="HACKED"), db=db, user=admin_a), 404)
        check("update platform admin -> 404", st == 404)
        st = await expect(lambda: delete_system_user(admin_b.id, db=db, user=admin_a), 404)
        check("delete foreign admin -> 404", st == 404)

        st = await expect(lambda: setup_mfa(email=admin_b.email, db=db, user=admin_a), 404)
        check("mfa/setup for foreign admin -> 404 (no TOTP leak)", st == 404)
        st = await expect(lambda: setup_mfa(email=admin_a.email, db=db, user=admin_a), 200)
        check("mfa/setup for self -> succeeds", st is None)

        st = await expect(lambda: rotate_agent_signing_key(RotateKeySchema(email=agent_b.email), db=db, user=admin_a), 404)
        check("rotate foreign agent key -> 404", st == 404)

        st = await expect(lambda: revoke_agent(agent_b.id, RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a), 404)
        check("revoke foreign agent -> 404", st == 404)
        st = await expect(lambda: purge_agent(agent_b.id, RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a), 404)
        check("purge foreign agent -> 404", st == 404)
        st = await expect(lambda: reactivate_agent(agent_b.id, RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a), 404)
        check("reactivate foreign agent -> 404", st == 404)

        st = await expect(lambda: create_role(RoleSchema(name=f"zz-role-{uuid.uuid4().hex[:6]}", permissions=[]), db=db, user=admin_a), 403)
        check("create role as client admin -> 403", st == 403)
        st = await expect(lambda: update_role("analyst", RoleSchema(name="analyst", permissions=[]), db=db, user=admin_a), 403)
        check("update role as client admin -> 403", st == 403)
        st = await expect(lambda: delete_role("viewer", db=db, user=admin_a), 403)
        check("delete role as client admin -> 403", st == 403)

        st = await expect(lambda: update_election_config(
            _ElectionConfigSchema(party_a_name="A", party_b_name="B", party_c_name="C", election_name="E"),
            db=db, user=admin_a), 403)
        check("write global election-config as client admin -> 403", st == 403)

        # ── positive controls: own-client operations still work ──
        r = await rotate_agent_signing_key(RotateKeySchema(email=agent_a.email), db=db, user=admin_a)
        check("rotate own agent key -> 200", bool(r.get("signing_key")))
        r = await revoke_agent(agent_a.id, RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a)
        check("revoke own agent -> 200", r.get("status") == "deactivated")
        r = await reactivate_agent(agent_a.id, RevokeSchema(admin_password="Sekret#123"), db=db, user=admin_a)
        check("reactivate own agent -> 200", bool(r.get("signing_key")))
        users_p = await get_system_users(db=db, user=plat)
        check("platform admin still sees everyone", len(users_p) >= 3)

        # ---- cleanup ----
        await db.execute(text("DELETE FROM users WHERE client_id IN (:a,:b)"), {"a": ca.id, "b": cb.id})
        await db.execute(text("DELETE FROM clients WHERE id IN (:a,:b)"), {"a": ca.id, "b": cb.id})
        await db.commit()
        print("sandbox cleaned up")

    print("\n=== %s ===" % ("ALL PASS" if not FAILED else f"{len(FAILED)} FAILURES: {FAILED}"))
    raise SystemExit(1 if FAILED else 0)


if __name__ == "__main__":
    asyncio.run(main())
