import json
import requests
import os

STATES_TO_KEEP = ["lagos", "abuja", "ogun", "rivers", "kano", "kaduna", "anambra", "delta", "borno", "kogi"]

def fetch_and_filter():
    url = "https://raw.githubusercontent.com/afeibukun/nigerian-state-lgas-wards-polling-units/main/states-and-lgas-and-wards-and-polling-units.json"
    print(f"Fetching data from {url}...")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        full_data = response.json()
        
        filtered_data = []
        for state in full_data:
            name = state.get("state", "").lower()
            if name in STATES_TO_KEEP:
                filtered_data.append(state)
        
        # Ensure we create directory
        os.makedirs("backend/app", exist_ok=True)
        output_path = "backend/app/inec_data_subset.json"
        with open(output_path, "w") as f:
            json.dump(filtered_data, f, indent=2)
            
        print(f"Success! Filtered {len(filtered_data)} states. Saved to {output_path}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_and_filter()
