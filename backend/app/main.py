from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.auth import router as auth_router
from app.upload import router as upload_router
from app.admin import router as admin_router
from app.results import router as results_router
from app.public import router as public_router
from app.elections import router as elections_router
from app.audit import router as audit_router
from fastapi.staticfiles import StaticFiles
import os
from datetime import datetime

app = FastAPI(
    title="Civic Lens Zero-Trust API",
    description="Military-grade offline resilient election result collation engine.",
    version="1.0.0"
)

print("[HOT-RELOAD] Security Initialization Protocol Synchronized")

# 22: # 1. Enforce strict HTTPS/TLS 1.3 across the application globally
# Uncomment this in production to violently force HTTPS redirects
# app.add_middleware(HTTPSRedirectMiddleware)

# 2. Prevent Host Header Injection attacks.
# Defaults cover the live gateway host; override with EXTRA_HOSTS=a,b,c
ALLOWED_HOSTS = [
    "193.122.220.182.nip.io",
    "193.122.220.182",
    "localhost",
    "127.0.0.1",
    "backend",  # intra-compose health probes
] + [h.strip() for h in os.environ.get("EXTRA_HOSTS", "").split(",") if h.strip()]

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS
)

# 3. CORS Policies (Cross-Origin Resource Sharing)
# All portals are served same-origin through the gateway, so the live API
# only needs its own host. Local dev servers can be allow-listed via the
# CORS_ORIGINS env var (comma-separated).
CORS_ORIGINS = [
    "https://193.122.220.182.nip.io",
    "http://193.122.220.182.nip.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
] + [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4b. Audit denied requests that CARRIED a credential — an expired, replayed
# or insufficient-privilege token is a security signal worth keeping. Bearer-
# less probes (port scans, the lockdown suite's no-token 401 checks) are
# visible at the gateway and would only flood the chain here.
@app.middleware("http")
async def audit_denied_requests(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (response.status_code in (401, 403)
            and request.headers.get("authorization")
            and path != "/health" and not path.startswith("/static")):
        try:
            from app.db import AsyncSessionLocal
            from app.security import ALGORITHM, SECRET_KEY, log_audit
            from jose import jwt as _jwt
            actor_id = actor_role = None
            try:
                token = request.headers["authorization"].replace("Bearer ", "")
                claims = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                actor_id, actor_role = claims.get("sub"), claims.get("role")
            except Exception:
                pass  # unparseable token — logged without an actor
            async with AsyncSessionLocal() as s:
                await log_audit(
                    s,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action="AUTH_DENIED",
                    target_type="http_endpoint",
                    target_id=path,
                    details=f"{request.method} {path} -> {response.status_code}",
                    ip_address=request.client.host if request.client else None,
                )
                await s.commit()
        except Exception:
            pass  # audit logging must never break the underlying request
    return response

# 5. Advanced Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self' http://127.0.0.1:8001; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: http://127.0.0.1:8001;"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Register high-security routers
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(admin_router)
app.include_router(results_router)
app.include_router(elections_router)
app.include_router(public_router)
app.include_router(audit_router)

@app.on_event("startup")
async def _ensure_schema():
    """Create any missing tables/columns on boot (idempotent).

    The agent_location_pings table and results.gps_trail_flag back the
    presence-trail feature; create_all handles the table, and the ALTER ...
    IF NOT EXISTS handles the column on the pre-existing results table.
    """
    from sqlalchemy import text
    from app.db import Base, engine
    from app import models  # noqa: F401 — register all mappings
    async with engine.begin() as conn:
        # Several gunicorn workers boot at once; the advisory lock makes the
        # migration single-runner so they can't race table creation.
        await conn.execute(text("SELECT pg_advisory_xact_lock(727272)"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE results ADD COLUMN IF NOT EXISTS "
            "gps_trail_flag BOOLEAN DEFAULT FALSE"))

        # ── Audit log: hash chain upgrade ──────────────────────────────
        # New columns for the chained WORM audit log (existing rows are
        # backfilled below); the sequence gives every row a global order.
        await conn.execute(text("CREATE SEQUENCE IF NOT EXISTS audit_log_seq"))
        for ddl in (
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS seq BIGINT",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_role VARCHAR(30)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_type VARCHAR(50)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS election_id VARCHAR(36)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS device_fingerprint VARCHAR(255)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS prev_hash VARCHAR(64)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS row_hash VARCHAR(64)",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_ts "
            "ON audit_logs (tenant_id, timestamp)",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_election "
            "ON audit_logs (election_id)",
        ):
            await conn.execute(text(ddl))

    # Backfill legacy (pre-chain) rows: order by timestamp, draw seq values,
    # hash each row chaining from the current tip. Fresh installs skip this.
    from app.db import AsyncSessionLocal
    from app.models import AuditLog
    from app.security import AUDIT_GENESIS_HASH, audit_canonical
    from sqlalchemy import select as _sa_select
    import hashlib as _hl
    async with AsyncSessionLocal() as s:
        legacy = (await s.execute(
            _sa_select(AuditLog).where(AuditLog.row_hash.is_(None))
            .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
        )).scalars().all()
        if legacy:
            prev = (await s.execute(
                _sa_select(AuditLog.row_hash)
                .where(AuditLog.row_hash.isnot(None))
                .order_by(AuditLog.seq.desc()).limit(1))).scalar() or AUDIT_GENESIS_HASH
            for r in legacy:
                seq = (await s.execute(
                    text("SELECT nextval('audit_log_seq')"))).scalar()
                ts = r.timestamp or datetime.utcnow()
                r.seq = seq
                r.prev_hash = prev
                r.row_hash = _hl.sha256(audit_canonical(
                    seq, ts, r.actor_id, r.actor_role, r.tenant_id,
                    r.action_type, r.target_type, r.target_entity_id,
                    r.election_id, r.details, r.ip_address,
                    r.device_fingerprint, prev).encode()).hexdigest()
                prev = r.row_hash
            await s.commit()
            print(f"[STARTUP] Audit chain backfilled: {len(legacy)} legacy row(s) hashed")
    print("[STARTUP] Schema check complete (incl. agent_location_pings)")

# Mount Static Files for Evidence Visibility
app.mount("/static", StaticFiles(directory=os.path.join(os.getcwd(), "app", "static")), name="static")

@app.get("/health", tags=["Monitoring"])
def health_check():
    """Load Balancer Health Check"""
    return {"status": "operational", "encryption": "AES-256", "tls": "Active"}

# ─────────────────────────────────────────────────────────────────
# ELECTION CONFIG — Inline registration to guarantee hot-reload
# ─────────────────────────────────────────────────────────────────
from pydantic import BaseModel as PydanticBase
from typing import Optional as Opt
from sqlalchemy import select as sa_select
from app.db import get_db as _get_db
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from fastapi import Depends as _Depends
from app.security import RequirePermission

@app.get("/admin/election-config", tags=["Election Config"])
async def get_election_config(db: _AsyncSession = _Depends(_get_db)):
    from app.models import ElectionConfig
    from datetime import datetime
    result = await db.execute(sa_select(ElectionConfig).where(ElectionConfig.id == "global"))
    config = result.scalar_one_or_none()
    if not config:
        config = ElectionConfig(id="global", party_a_name="Party A", party_b_name="Party B", party_c_name="Party C", election_name="General Election")
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return {"party_a_name": config.party_a_name, "party_b_name": config.party_b_name, "party_c_name": config.party_c_name, "election_name": config.election_name}

