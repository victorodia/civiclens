from app.main import app
for route in app.routes:
    print(f"ROUTE: {route.path} | METHODS: {route.methods}")
