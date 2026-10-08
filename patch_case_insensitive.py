import os
import re

files_to_check = [
    "/civiclens/backend/app/admin.py",
    "/civiclens/backend/app/auth.py",
    "/civiclens/backend/app/results.py",
    "/civiclens/backend/app/seed_admin.py",
    "/civiclens/backend/app/seed_mock_data.py"
]

def patch_file(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} - not found")
        return
        
    with open(filepath, 'r') as f:
        content = f.read()
        
    # Check if func is imported
    if "from sqlalchemy import func" not in content and "import func" not in content:
        # Add import at the top after from sqlalchemy import select
        if "from sqlalchemy import select" in content:
            content = content.replace("from sqlalchemy import select", "from sqlalchemy import select, func")
        else:
            content = "from sqlalchemy import func\n" + content
            
    # Replace User.email == <expr>
    # We can use a regex to capture what's on the right side up to the closing parenthesis
    # But some queries might be nested.
    # Let's do simple string replacements for the known ones:
    
    replacements = [
        ("User.email == email", "func.lower(User.email) == func.lower(email)"),
        ("User.email == payload.email", "func.lower(User.email) == func.lower(payload.email)"),
        ("User.email == payload.agent_email", "func.lower(User.email) == func.lower(payload.agent_email)"),
        ('User.email == "admin@civiclens.io"', 'func.lower(User.email) == func.lower("admin@civiclens.io")'),
        ('User.email == "agent_test@civiclens.io"', 'func.lower(User.email) == func.lower("agent_test@civiclens.io")')
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            
    if modified:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Patched {filepath}")
    else:
        print(f"No changes for {filepath}")

for f in files_to_check:
    patch_file(f)
