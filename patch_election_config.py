import os
import re

file_path = "/home/ubuntu/civiclens/admin-portal/src/components/ElectionConfig.jsx"

with open(file_path, "r") as f:
    content = f.read()

if "import RoleManagement from './RoleManagement';" not in content:
    content = content.replace(
        "import SystemUsers from './SystemUsers';",
        "import SystemUsers from './SystemUsers';\nimport RoleManagement from './RoleManagement';"
    )

if "<RoleManagement />" not in content:
    content = content.replace(
        "<SystemUsers />",
        "<RoleManagement />\n            <div className=\"h-12\"></div>\n            <SystemUsers />"
    )

with open(file_path, "w") as f:
    f.write(content)

print("ElectionConfig.jsx patched with RoleManagement!")
