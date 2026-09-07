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

# Mock Redis Rate Limiter (In Prod, use 'slowapi' + Redis)
login_attempts = {}

def check_rate_limit(client_ip: str) -> bool:
    """
    Prevents brute-force attacks. 
    Limits to 20 attempts per minute per IP.
    """
    now = datetime.utcnow()
    attempts = login_attempts.get(client_ip, [])
    # Filter attempts in the last 60 seconds
    attempts = [a for a in attempts if now - a < timedelta(seconds=60)]
    
    if len(attempts) >= 20:
        return False
        
    attempts.append(now)
    login_attempts[client_ip] = attempts
    return True

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

def verify_payload_signature(payload_string: str, signature_b64: str) -> bool:
    """
    Verifies that the payload was signed by a trusted agent device.
    Uses HMAC-SHA256 with a pre-shared secret key.
    """
    # In production, keys should be unique per agent and stored in a HSM/Vault
    # and derived during the provisioning phase.
    SECRET_KEY_SIGNING = b"AGENT_DEVICE_SECRET_KEY" 
    
    try:
        # Re-generate the expected signature
        message = payload_string.encode()
        expected_signature = hmac.new(SECRET_KEY_SIGNING, message, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected_signature).decode()
        
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_b64, signature_b64)
    except Exception as e:
        print(f"[SECURITY ERROR] Signature verification failed: {e}")
        return False

# 4. Centralized Audit Logger
async def log_audit(db: AsyncSession, actor_id: str, action: str, target_id: str = None, details: str = None):
    """Writes a secure entry to the audit_logs table."""
    from .models import AuditLog
    new_log = AuditLog(
        actor_id=actor_id,
        action_type=action,
        target_entity_id=target_id,
        details=details
    )
    db.add(new_log)
    # We don't commit here; we let the parent transaction handle it.

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

