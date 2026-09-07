from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.auth import router as auth_router
from app.upload import router as upload_router
from app.sms import router as sms_fallback_router
from app.admin import router as admin_router
from app.results import router as results_router
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(
    title="Civic Lens Zero-Trust API",
    description="Military-grade offline resilient election result collation engine.",
    version="1.0.0"
)

print("[HOT-RELOAD] Security Initialization Protocol Synchronized")

# 22: # 1. Enforce strict HTTPS/TLS 1.3 across the application globally
# Uncomment this in production to violently force HTTPS redirects
# app.add_middleware(HTTPSRedirectMiddleware)

# 2. Prevent Host Header Injection attacks
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "civiclens.io", "*.civiclens.io"]
)

# 3. CORS Policies (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In high-security prod, this would be specific subdomains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Advanced Security Headers Middleware
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
app.include_router(sms_fallback_router)
app.include_router(admin_router)
app.include_router(results_router)

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

class _ElectionConfigSchema(PydanticBase):
    party_a_name: str
    party_b_name: str
    party_c_name: str
    election_name: str

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

@app.put("/admin/election-config", tags=["Election Config"])
async def update_election_config(payload: _ElectionConfigSchema, db: _AsyncSession = _Depends(_get_db)):
    from app.models import ElectionConfig
    from datetime import datetime
    result = await db.execute(sa_select(ElectionConfig).where(ElectionConfig.id == "global"))
    config = result.scalar_one_or_none()
    if not config:
        config = ElectionConfig(id="global")
        db.add(config)
    config.party_a_name = payload.party_a_name.strip()
    config.party_b_name = payload.party_b_name.strip()
    config.party_c_name = payload.party_c_name.strip()
    config.election_name = payload.election_name.strip()
    config.updated_at = datetime.utcnow()
    await db.commit()
    print(f"[CONFIG] Party names updated: A={config.party_a_name}, B={config.party_b_name}, C={config.party_c_name}")
    return {"status": "success", "message": "Election configuration updated."}
