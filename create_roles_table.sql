CREATE TABLE IF NOT EXISTS roles (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    permissions JSONB DEFAULT '[]'::jsonb
);

INSERT INTO roles (id, name, permissions) 
VALUES (
    'role-super-admin', 
    'admin', 
    '["view_live_telemetry", "view_geographic_data", "view_results", "approve_results", "flag_results", "view_agents", "view_agent_locations", "provision_agents", "revoke_agents", "view_system_users", "create_system_users", "suspend_system_users", "change_user_roles", "delete_system_users", "view_audit_logs", "trigger_factory_reset"]'::jsonb
) ON CONFLICT (name) DO NOTHING;

INSERT INTO roles (id, name, permissions) 
VALUES (
    'role-analyst', 
    'analyst', 
    '["view_live_telemetry", "view_geographic_data", "view_results", "approve_results", "flag_results"]'::jsonb
) ON CONFLICT (name) DO NOTHING;

INSERT INTO roles (id, name, permissions) 
VALUES (
    'role-viewer', 
    'viewer', 
    '["view_live_telemetry", "view_geographic_data", "view_results"]'::jsonb
) ON CONFLICT (name) DO NOTHING;

-- Also we map the existing 'situation_room' users to 'analyst' for consistency if they exist, or just create a 'situation_room' role.
INSERT INTO roles (id, name, permissions) 
VALUES (
    'role-situation-room', 
    'situation_room', 
    '["view_live_telemetry", "view_geographic_data", "view_results", "approve_results", "flag_results"]'::jsonb
) ON CONFLICT (name) DO NOTHING;
