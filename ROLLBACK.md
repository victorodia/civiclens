# CivicLens Baseline & Rollback Runbook

Baseline tag: baseline-2026-10-08 (branch: master)
All new work happens on branch: hardening

## Rules
- Never run 'docker compose up --build' from master while it is serving.
- Rebuild the live stack only from the 'hardening' branch, and only after approval.
- Secrets live in ./.env (chmod 600, never committed). .env.example is the template.

## Code rollback
    cd ~/civiclens && git checkout master && git reset --hard baseline-2026-10-08
    sudo docker compose up -d --build

## Data rollback
    gunzip -c ~/backups/civiclens_baseline_2026-10-08.sql.gz | sudo docker exec -i civiclens-db psql -U civiclens_user civiclens
    tar xzf ~/backups/civiclens_uploads_2026-10-08.tar.gz -C ~/civiclens/backend

## Known follow-ups (hardening branch)
- Rotate POSTGRES_PASSWORD (old value exists in git history up to the baseline parent commit).
- Rotate the Polygon wallet key (archived from the old /civiclens copy: ~/backups/civiclens_old_root_copy_FULL.tar.gz).
- Backend JWT fallback key and HMAC signing key are hardcoded in app/security.py.
