import requests
import json

BASE_URL = "http://127.0.0.1:8000/auth"

def verify_login_hierarchy():
    print("--- Verifying Geographic Binding in Login Response ---")
    
    # 1. Login as Agent
    payload = {
        "email": "victor.odia14@gmail.com",
        "password": "admin123",
        "device_fingerprint": "MOCKED_PHONE_ID"
    }
    
    r = requests.post(f"{BASE_URL}/login", json=payload)
    data = r.json()
    
    print(f"Status: {r.status_code}")
    print(json.dumps(data, indent=2))
    
    if r.status_code == 200 and data.get("assigned_pu"):
        pu = data["assigned_pu"]
        print("\nSUCCESS: Geographic Context Found.")
        print(f"Hierarchy: {pu['state']} > {pu['lga']} > {pu['ward']}")
        print(f"PU: {pu['name']} ({pu['pu_code']})")
    else:
        print("\nFAILURE: Missing Geographic Context or Login Failed.")

if __name__ == "__main__":
    verify_login_hierarchy()
