import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship
from .db import Base

class ElectionConfig(Base):
    """
    Election Configuration: Stores party names and election metadata.
    Only one active config row (singleton pattern using id='global').
    """
    __tablename__ = "election_config"

    id = Column(String(36), primary_key=True, default="global")
    party_a_name = Column(String(100), default="Party A")
    party_b_name = Column(String(100), default="Party B")
    party_c_name = Column(String(100), default="Party C")
    election_name = Column(String(200), default="General Election")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(Base):
    """
    WORM (Write Once, Read Many) Audit Log Table.
    Every sensitive action (login, verification, manual override) MUST write an entry here.
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id = Column(String(36), index=True) # ID of user pushing the action
    action_type = Column(String(50), nullable=False)  # e.g., 'VERIFY_RESULT', 'DURESS_LOGIN'
    target_entity_id = Column(String(100), nullable=True) # Result ID or User ID being acted upon
    details = Column(Text, nullable=True) # JSON dump of pre/post states
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class CustomRole(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    permissions = Column(JSON, default=list) # Array of permission strings
    
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False) # Argon2 hash
    hashed_duress_password = Column(String(255), nullable=True) # Secondary hash for hostage situations
    full_name = Column(String(150), nullable=False)
    role = Column(String(20), default="agent") # Roles: admin, situation_room, agent
    
    # Advanced Security Columns
    is_active = Column(Boolean, default=True)
    device_fingerprint = Column(String(255), nullable=True) # Binds the account to one specific mobile phone
    device_signing_key = Column(String(64), nullable=True) # Per-agent HMAC key for payload signing (delivered at provisioning)
    is_2fa_enabled = Column(Boolean, default=False)
    totp_secret = Column(String(100), nullable=True)
    requires_password_reset = Column(Boolean, default=True) # Forces new agents to set a secure password immediately
    
    # Operational Tracking
    is_on_site = Column(Boolean, default=False)
    last_check_in = Column(DateTime, nullable=True)
    check_in_lat = Column(Float, nullable=True)
    check_in_lng = Column(Float, nullable=True)
    
    # Optional Hierarchy constraint (Agent bound to specific PU)
    assigned_pu_id = Column(String(36), ForeignKey("polling_units.id"), nullable=True)

class State(Base):
    __tablename__ = "states"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(10), unique=True, nullable=True)
    
    lgas = relationship("LGA", back_populates="state")

class LGA(Base):
    __tablename__ = "lgas"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    state_id = Column(String(36), ForeignKey("states.id"))
    
    state = relationship("State", back_populates="lgas")
    wards = relationship("Ward", back_populates="lga")

class Ward(Base):
    __tablename__ = "wards"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    lga_id = Column(String(36), ForeignKey("lgas.id"))
    
    lga = relationship("LGA", back_populates="wards")
    polling_units = relationship("PollingUnit", back_populates="ward")

class PollingUnit(Base):
    __tablename__ = "polling_units"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pu_code = Column(String(50), unique=True, nullable=False) # INEC Code format e.g., 01-02-03-004
    name = Column(String(255), nullable=False)
    ward_id = Column(String(36), ForeignKey("wards.id"))
    
    # Geofencing Anchor Coordinates
    expected_latitude = Column(String(50), nullable=True)
    expected_longitude = Column(String(50), nullable=True)
    
    ward = relationship("Ward", back_populates="polling_units")

class Result(Base):
    """
    Core Election Result Payload. 
    WORM logic implies updating this row is functionally prevented at the application tier once submitted.
    """
    __tablename__ = "results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pu_id = Column(String(36), ForeignKey("polling_units.id"), unique=True) # 1 PU = 1 Result record strictly
    agent_id = Column(String(36), ForeignKey("users.id"))
    
    # Tally
    party_a_votes = Column(Integer, default=0) # E.g., The main party
    party_b_votes = Column(Integer, default=0)
    party_c_votes = Column(Integer, default=0)
    total_valid_votes = Column(Integer, default=0)
    rejected_votes = Column(Integer, default=0)
    
    # Evidence & Verification
    image_url = Column(String(500), nullable=True) # Direct S3 bucket URL to Form EC8A image
    video_url = Column(String(500), nullable=True) # Direct S3 bucket URL to video evidence
    is_verified = Column(Boolean, default=False)
    is_compromised = Column(Boolean, default=False) # Triggered by the Duress password
    
    # AI/OCR Verification Data
    ai_party_a_votes = Column(Integer, nullable=True)
    ai_party_b_votes = Column(Integer, nullable=True)
    ai_party_c_votes = Column(Integer, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    is_flagged = Column(Boolean, default=False)
    
    # Submission Telemetry
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Presence trail: set when the agent had fewer GPS pings than expected
    # between verify-entry and submission. FLAG ONLY — the result is still
    # accepted; the situation room reviews flagged rows. (GPS drift, dead
    # batteries and backgrounded apps make a hard block unsafe.)
    gps_trail_flag = Column(Boolean, default=False)

    # Offline-First Timestamp capturing
    captured_at = Column(DateTime, nullable=False) # The actual time it was taken offline
    uploaded_at = Column(DateTime, default=datetime.utcnow) # The time it hit the server

    # Blockchain Anchoring (Polygon) — sha256 of the canonical result payload;
    # tx id recorded once the hash is anchored on-chain
    blockchain_hash = Column(String(66), nullable=True)
    blockchain_tx_id = Column(String(100), nullable=True)



# Alias for backward compatibility
Role = CustomRole


class AgentLocationPing(Base):
    """
    Presence Trail (GPS breadcrumbs).
    Between "Verify Entry" and result submission the agent portal transmits
    the device coordinates every PING_INTERVAL_MINUTES (default 30). Rows are
    append-only — nothing here is ever updated or deleted, so the trail is
    tamper-evident the same way results are. At submission time the server
    checks the trail and FLAGS (never blocks) a result whose agent has no
    recent location evidence.
    """
    __tablename__ = "agent_location_pings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    pu_id = Column(String(36), ForeignKey("polling_units.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    # True when the ping landed outside the assigned PU's geofence radius
    # (drift, indoor GPS, or the agent walked away) — recorded, not rejected.
    outside_geofence = Column(Boolean, default=False)
    distance_m = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
