import os
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext

# Fast, highly secure Argon2 hashing algorithm
# We configure high memory/time costs to prevent brute-force cracking
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Production environment should pull these from AWS Secrets Manager / ENV
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "ultra_secure_super_secret_dev_key_DO_NOT_USE_IN_PROD")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12 # 12 hour shifts for field agents

# Login brute-force protection: Redis-backed failure counters with an
# in-memory per-process fallback. Two buckets per attempt:
#   login:email:{email} -> 8 failures / 10 min (lockout target)
#   login:ip:{ip}       -> 30 failures / 5 min  (rotating-email defence)
# Only FAILURES count; a successful login clears the email bucket so a
# legitimate user who typos a few times is never locked out.
import os as _rl_os
REDIS_URL = _rl_os.environ.get("REDIS_URL", "")
_EMAIL_FAIL_LIMIT = 8
_EMAIL_FAIL_WINDOW = 600
_IP_FAIL_LIMIT = 30
_IP_FAIL_WINDOW = 300

# In-memory fallback (per gunicorn worker) when Redis is unreachable.
_mem_fails: dict = {}


async def _redis_client():
    import redis.asyncio as aioredis
    return aioredis.from_url(REDIS_URL, socket_timeout=3, socket_connect_timeout=3)


async def check_login_rate_limits(email: str, ip: str = None) -> bool:
    """True = attempt allowed. Enforces both buckets."""
    key_email = f"login:email:{email.lower()}"
    key_ip = f"login:ip:{ip}" if ip else None
    try:
        r = await _redis_client()
        try:
            efails = int(await r.get(key_email) or 0)
            if efails >= _EMAIL_FAIL_LIMIT:
                return False
            if key_ip:
                ifails = int(await r.get(key_ip) or 0)
                if ifails >= _IP_FAIL_LIMIT:
                    return False
        finally:
            await r.close()
        return True
    except Exception:
        now = datetime.utcnow()
        for key, limit, window in ((key_email, _EMAIL_FAIL_LIMIT, _EMAIL_FAIL_WINDOW),
                                   (key_ip, _IP_FAIL_LIMIT, _IP_FAIL_WINDOW)):
            if not key:
                continue
            stamps = [t for t in _mem_fails.get(key, []) if now - t < timedelta(seconds=window)]
            if len(stamps) >= limit:
                return False
        return True


async def record_login_failure(email: str, ip: str = None) -> None:
    """Count a failed password/identity against both buckets."""
    key_email = f"login:email:{email.lower()}"
    key_ip = f"login:ip:{ip}" if ip else None
    try:
        r = await _redis_client()
        try:
            for key in (key_email, key_ip):
                if not key:
                    continue
                n = await r.incr(key)
                if n == 1:
                    await r.expire(key, _EMAIL_FAIL_WINDOW if key == key_email else _IP_FAIL_WINDOW)
        finally:
            await r.close()
        return
    except Exception:
        pass
    now = datetime.utcnow()
    for key in (key_email, key_ip):
        if key:
            _mem_fails.setdefault(key, []).append(now)


async def clear_login_failures(email: str) -> None:
    """A correct password wipes the email bucket (typos must not lock out)."""
    key_email = f"login:email:{email.lower()}"
    try:
        r = await _redis_client()
        try:
            await r.delete(key_email)
        finally:
            await r.close()
    except Exception:
        pass
    _mem_fails.pop(key_email, None)


# Timing equalizer: verifying against this hash costs the same Argon2 work as
# a real verify, so "account exists" cannot be detected by response time.
_TIMING_DUMMY_HASH = None

def get_timing_dummy_hash() -> str:
    global _TIMING_DUMMY_HASH
    if _TIMING_DUMMY_HASH is None:
        _TIMING_DUMMY_HASH = pwd_context.hash("civiclens-timing-equalizer")
    return _TIMING_DUMMY_HASH

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies standard matching password"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generates an Argon2 hash from a plaintext string"""
    return pwd_context.hash(password)

def is_duress_password(plain_password: str, normal_password_hash: str) -> bool:
    """
    CRITICAL SECURITY FUNCTION:
    If an agent appends a specific PIN or types their password backward under duress,
    this function detects it without triggering an outright 'Wrong Password' error.
    
    For MVP: Assuming the distress code simply involves appending '999' to the user's password.
    In a real scenario, this would be a secondary dedicated password.
    """
    if plain_password.endswith("999"):
        base_attempt = plain_password[:-3]
        if verify_password(base_attempt, normal_password_hash):
            return True
    return False

def check_login_attempt(plain_password: str, normal_password_hash: str, duress_password_hash: Optional[str] = None) -> Tuple[bool, bool]:
    """
    Electronic Muster Roll / Zero-Trust Verification.
    Returns: (is_authenticated, is_under_duress)
    """
    # 1. Check primary password
    if verify_password(plain_password, normal_password_hash):
        return True, False
        
    # 2. Check secret duress password (if configured)
    if duress_password_hash and verify_password(plain_password, duress_password_hash):
        return True, True  # SECRET FLAG - Let them in, but monitor everything!
        
    # 3. Legacy MVP distress check (999 suffix)
    if is_duress_password(plain_password, normal_password_hash):
        return True, True
        
    return False, False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, is_compromised: bool = False):
    """
    Generates a JWT. 
    If is_compromised is True, the payload silently carries a 'duress_flag' parameter.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    
    # Secretly embed the duress flag into the token so the DB layer knows later
    if is_compromised:
        to_encode.update({"duress_flag": True})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# 3. HMAC-SHA256 Payload Verification
import hmac
import hashlib
import base64

def verify_payload_signature(payload_string: str, signature_b64: str, signing_key: str) -> bool:
    """
    Verifies that the payload was signed by the specific agent's device.
    Uses HMAC-SHA256 with the agent's unique pre-shared key (issued at
    provisioning, stored on the user record). Constant-time comparison.
    """
    if not signing_key:
        return False
    try:
        message = payload_string.encode()
        expected_signature = hmac.new(signing_key.encode(), message, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected_signature).decode()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_b64, signature_b64)
    except Exception as e:
        print(f"[SECURITY ERROR] Signature verification failed: {e}")
        return False

# 4. Centralized Audit Logger — hash-chained, WORM
import hashlib as _audit_hashlib

AUDIT_GENESIS_HASH = _audit_hashlib.sha256(b"civiclens-audit-genesis-v1").hexdigest()
_AUDIT_APPEND_LOCK_KEY = 919191  # pg advisory lock: serializes chain appends across workers

def audit_canonical(seq, ts, actor_id, actor_role, tenant_id, action,
                    target_type, target_id, election_id, details,
                    ip_address, device_fingerprint, prev_hash):
    """Canonical string the row_hash commits to. Field order is fixed; any
    change here must be mirrored in the /admin/audit-logs/verify endpoint."""
    return "|".join("" if v is None else str(v) for v in (
        seq, ts, actor_id, actor_role, tenant_id, action, target_type,
        target_id, election_id, details, ip_address, device_fingerprint,
        prev_hash))

async def log_audit(db: AsyncSession, actor_id: str = None, action: str = None,
                    target_id: str = None, details: str = None,
                    actor_role: str = None, tenant_id: str = None,
                    target_type: str = None, election_id: str = None,
                    ip_address: str = None, device_fingerprint: str = None):
    """Appends a hash-chained entry to the audit_logs table.

    Chain safety: a transaction-scoped advisory lock serializes appends, so
    concurrent gunicorn workers always extend the single tip. The row is
    committed by the caller's transaction (same pattern as before); on
    rollback the row vanishes but the chain stays valid because linkage is
    by hash, not by consecutive seq values (nextval gaps are harmless).
    Never log secrets: passwords, duress indicators beyond a flag, TOTP
    seeds and signing keys must never appear in `details`.
    """
    from .models import AuditLog
    from sqlalchemy import select as _select, text as _text
    try:
        await db.execute(_text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_APPEND_LOCK_KEY})
    except Exception:
        pass  # sqlite dev environments have no advisory locks — best effort only
    seq = (await db.execute(_text("SELECT nextval('audit_log_seq')"))).scalar()
    tip = (await db.execute(
        _select(AuditLog.row_hash)
        .where(AuditLog.row_hash.isnot(None))
        .order_by(AuditLog.seq.desc()).limit(1))).scalar()
    prev_hash = tip or AUDIT_GENESIS_HASH
    ts = datetime.utcnow()
    row_hash = _audit_hashlib.sha256(audit_canonical(
        seq, ts, actor_id, actor_role, tenant_id, action, target_type,
        target_id, election_id, details, ip_address, device_fingerprint,
        prev_hash).encode()).hexdigest()
    db.add(AuditLog(
        seq=seq,
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
        action_type=action,
        target_type=target_type,
        target_entity_id=target_id,
        election_id=election_id,
        details=details,
        ip_address=ip_address,
        device_fingerprint=device_fingerprint,
        timestamp=ts,
        prev_hash=prev_hash,
        row_hash=row_hash,
    ))

# 5. Production Kill-Switch & Status Enforcement
async def check_user_status(user_id: str, device_fingerprint: str, db: AsyncSession) -> bool:
    """
    Enforces the Remote Kill-Switch.
    Checks if the user account is active AND if the device is still authorized.
    """
    from .models import User
    from sqlalchemy import select
    
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if not user:
        return False
        
    if not user.is_active:
        print(f"[SECURITY] Access Denied: User {user_id} has been REVOKED.")
        return False
        
    if user.device_fingerprint and user.device_fingerprint != device_fingerprint:
        print(f"[SECURITY] Access Denied: Unauthorized device attempt for User {user_id}.")
        return False
        
    return True



from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from .db import get_db
import json

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from .models import User, CustomRole
    from sqlalchemy import select
    
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
        
    return user

class RequirePermission:
    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        from .models import CustomRole
        from sqlalchemy import select
        
        # If it's a field agent, they shouldn't even be here. (Agents use agent portal)
        if user.role == "agent":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Field agents cannot access the admin API.")
            
        # Fetch the role
        stmt = select(CustomRole).where(CustomRole.name == user.role)
        res = await db.execute(stmt)
        role = res.scalar_one_or_none()
        
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not found or unassigned.")
            
        if self.permission not in role.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permission: {self.permission}")
            
        return user
