import os
import re

file_path = "/home/ubuntu/civiclens/backend/app/models.py"

with open(file_path, "r") as f:
    content = f.read()

# Make sure we don't add it twice
if "class CustomRole(Base):" not in content:
    # Add JSON import if not present
    if "JSON" not in content:
        content = content.replace("from sqlalchemy import Column, ", "from sqlalchemy import Column, JSON, ")

    new_model = """
class CustomRole(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    permissions = Column(JSON, default=list) # Array of permission strings
    
"""
    # Insert it right before class User(Base)
    content = content.replace("class User(Base):", new_model + "class User(Base):")

    with open(file_path, "w") as f:
        f.write(content)
    print("models.py patched successfully!")
else:
    print("CustomRole already exists in models.py")
