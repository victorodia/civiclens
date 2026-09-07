import requests
import json

BASE_URL = "http://127.0.0.1:8000/admin"

def test_revocation():
    print("--- Verifying Secure Revocation Workflow ---")
    
    # 1. Fetch Agents
    r = requests.get(f"{BASE_URL}/agents")
    try:
        agents = r.json()
    except:
        print(f"Failed to parse JSON. Status: {r.status_code}")
        return

    if not agents:
        print("No agents found. Please provision one first.")
        return
    
    target_id = agents[0]['id']
    target_email = agents[0]['email']
    print(f"Target Agent: {target_email} ({target_id})")
    
    # 2. Test Wrong Password
    print("\n[TEST 1] Testing with WRONG admin password...")
    payload = {"admin_password": "IncorrectPassword123"}
    r = requests.delete(f"{BASE_URL}/agents/{target_id}", json=payload)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
    if r.status_code == 401:
        print("PASSED: Backend correctly rejected invalid password.")
    else:
        print("FAILED: Backend did not return 401 for wrong password.")

    # 3. Test Correct Password
    print("\n[TEST 2] Testing with CORRECT admin password...")
    payload = {"admin_password": "admin123"}
    r = requests.delete(f"{BASE_URL}/agents/{target_id}", json=payload)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
    if r.status_code == 200:
        print(f"PASSED: Agent {target_email} revoked.")
    else:
        print(f"FAILED: Backend rejected correct password or failed deletion.")

if __name__ == "__main__":
    test_revocation()
