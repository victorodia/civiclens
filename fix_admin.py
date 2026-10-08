import sys

with open('/home/ubuntu/civiclens/backend/app/admin.py', 'r') as f:
    lines = f.readlines()

# Find the start of our appended code. It started with "from fastapi import APIRouter"
# wait, actually let's just find the first @router.get("") that we added
# Actually, I can just use git checkout or something if it's in a git repo? No.
# I will just write a python script to strip it.
# Wait, I can just replace `router = APIRouter(prefix="/system/users", tags=["System Users"])`
# with just empty string and change the decorators.

content = "".join(lines)
start_idx = content.find("router = APIRouter(prefix=\"/system/users\", tags=[\"System Users\"])")
if start_idx != -1:
    # We remove everything from the start of our appended block
    # Actually our appended block starts with `from fastapi import APIRouter` but those might be used above.
    pass

# A better way: just replace `router = APIRouter(prefix="/system/users", tags=["System Users"])` with nothing.
# and then replace `@router.get("")` with `@router.get("/system/users")`
# and `@router.post("")` with `@router.post("/system/users")`
# and `@router.patch("/{user_id}")` with `@router.patch("/system/users/{user_id}")`
# and `@router.delete("/{user_id}")` with `@router.delete("/system/users/{user_id}")`

content = content.replace('router = APIRouter(prefix="/system/users", tags=["System Users"])', '')
content = content.replace('@router.get("")\nasync def get_system_users', '@router.get("/system/users")\nasync def get_system_users')
content = content.replace('@router.post("")\nasync def create_system_user', '@router.post("/system/users")\nasync def create_system_user')
content = content.replace('@router.patch("/{user_id}")\nasync def update_system_user', '@router.patch("/system/users/{user_id}")\nasync def update_system_user')
content = content.replace('@router.delete("/{user_id}")\nasync def delete_system_user', '@router.delete("/system/users/{user_id}")\nasync def delete_system_user')

# Also wait, did I append `from fastapi import APIRouter...` at the end? Yes.
# That's fine, python ignores it.

with open('/home/ubuntu/civiclens/backend/app/admin.py', 'w') as f:
    f.write(content)

print("Fixed!")
