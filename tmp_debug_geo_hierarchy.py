import requests

BASE_URL = "http://127.0.0.1:8000/admin/geo"

def debug_geo():
    # 1. Get States
    print("Fetching States...")
    r = requests.get(f"{BASE_URL}/states")
    states = r.json()
    if not states:
        print("No states found!")
        return
    
    state = states[0]
    print(f"STATE: {state['name']} | ID: {state['id']}")
    
    # 2. Get LGAs for State
    print(f"Fetching LGAs for {state['name']}...")
    r_lga = requests.get(f"{BASE_URL}/states/{state['id']}/lgas")
    print(f"LGA Status: {r_lga.status_code}")
    lgas = r_lga.json()
    print(f"LGAs Found: {len(lgas)}")
    if lgas:
        print(f"SAMPLE LGA: {lgas[0]['name']} | ID: {lgas[0]['id']}")
        
        # 3. Get Wards for LGA
        lga = lgas[0]
        print(f"Fetching Wards for {lga['name']}...")
        r_ward = requests.get(f"{BASE_URL}/lgas/{lga['id']}/wards")
        wards = r_ward.json()
        print(f"Wards Found: {len(wards)}")
        if wards:
            ward = wards[0]
            print(f"SAMPLE WARD: {ward['name']} | ID: {ward['id']}")
            
            # 4. Get PUs for Ward
            print(f"Fetching PUs for {ward['name']}...")
            r_pu = requests.get(f"{BASE_URL}/wards/{ward['id']}/pus")
            pus = r_pu.json()
            print(f"PUs Found: {len(pus)}")

if __name__ == "__main__":
    debug_geo()
