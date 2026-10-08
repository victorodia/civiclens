import os

file_path = "/home/ubuntu/civiclens/backend/app/auth.py"
with open(file_path, "r") as f:
    content = f.read()

# We need to find:
# user, pu, ward, lga, state = row
# and insert the check right after it

target = "user, pu, ward, lga, state = row"
if target in content:
    replacement = """user, pu, ward, lga, state = row

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been deactivated. Contact the system administrator.")
"""
    new_content = content.replace(target, replacement)
    
    with open(file_path, "w") as f:
        f.write(new_content)
    print("Patch applied successfully.")
else:
    print("Target string not found in auth.py")
