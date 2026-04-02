import json

import requests

BASE_URL = "http://127.0.0.1:8080/api/v1/paper"
ACCOUNT_ID = "paper-default"


def test_equity_history():
    try:
        url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/equity-history"
        print(f"Testing: {url}")
        resp = requests.get(url)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            print(f"Data received: {len(data)} points")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Connection failed: {e}")


if __name__ == "__main__":
    test_equity_history()
