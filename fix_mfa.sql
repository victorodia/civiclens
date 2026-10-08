UPDATE users SET requires_password_reset = true WHERE is_2fa_enabled = false AND role IN ('admin', 'situation_room');
