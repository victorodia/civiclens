import os
import re

file_path = "/home/ubuntu/civiclens/admin-portal/src/components/SystemUsers.jsx"

with open(file_path, "r") as f:
    content = f.read()

# Add a state for roles
if "const [roles, setRoles] = useState([]);" not in content:
    content = content.replace(
        "const [users, setUsers] = useState([]);",
        "const [users, setUsers] = useState([]);\n    const [roles, setRoles] = useState([]);"
    )

# Add a fetchRoles function
fetch_roles_code = """
    const fetchRoles = async () => {
        try {
            const res = await fetch('/admin/system/roles');
            if (res.ok) {
                const data = await res.json();
                setRoles(data);
            }
        } catch (error) {
            console.error("Failed to fetch roles", error);
        }
    };
"""

if "const fetchRoles =" not in content:
    content = content.replace(
        "const fetchUsers = async () => {",
        fetch_roles_code + "\n    const fetchUsers = async () => {"
    )

# Call fetchRoles in useEffect
if "fetchRoles();" not in content:
    content = content.replace(
        "fetchUsers();",
        "fetchUsers();\n        fetchRoles();"
    )

# Replace the static select options in the Create User Form
dynamic_options = """
                                                {roles.map(r => (
                                                    <option key={r.name} value={r.name}>{r.name.toUpperCase()}</option>
                                                ))}
"""
content = re.sub(
    r'<select\s+value=\{formData\.role\}[^>]*>.*?<\/select>',
    r'<select value={formData.role} onChange={(e) => setFormData({...formData, role: e.target.value})} className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors text-sm font-bold uppercase tracking-wider text-gray-700 dark:text-gray-300">' + dynamic_options + r'</select>',
    content,
    flags=re.DOTALL
)

# Replace the static select options in the User Table
table_select = """
                                            <select 
                                                value={user.role} 
                                                onChange={(e) => handleRoleChange(user.id, e.target.value)}
                                                className={`px-2 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold outline-none cursor-pointer bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`}
                                            >
                                                {roles.map(r => (
                                                    <option key={r.name} value={r.name}>{r.name.toUpperCase()}</option>
                                                ))}
                                            </select>
"""
content = re.sub(
    r'<select[^>]*onChange=\{\(e\) => handleRoleChange\(user\.id, e\.target\.value\)\}[^>]*>.*?<\/select>',
    table_select,
    content,
    flags=re.DOTALL
)

with open(file_path, "w") as f:
    f.write(content)

print("SystemUsers.jsx patched with dynamic roles!")
