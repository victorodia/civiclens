import os
path = '/home/ubuntu/civiclens/backend/app/main.py'
with open(path, 'r') as f:
    content = f.read()

target = 'allowed_hosts=["localhost", "127.0.0.1", "civiclens.io", "*.civiclens.io"]'
replacement = 'allowed_hosts=["*"]'

if target in content:
    content = content.replace(target, replacement)
    with open(path, 'w') as f:
        f.write(content)
    print("Replaced!")
else:
    print("Not found!")
