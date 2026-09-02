import requests
import json
import time

url = "http://127.0.0.1:5000/api/v1/skill/convergence"

# Agent B prepares the payload for a specific ecosystem token
payload = {
    "agent_id": "agent_alpha_seeker",
    "x402_hash": f"0xmockhash{int(time.time())}", 
    "symbol": "DUSKUSDT"
}

print(f"Agent B (Buyer): Requesting Convergence Signal for {payload['symbol']}...")
print("Agent B (Buyer): Submitting 0.50 USDC via Binance x402...")

# Execute the programmable payment request
response = requests.post(url, json=payload)

print(f"\nProvider Response [HTTP {response.status_code}]:")
print(json.dumps(response.json(), indent=2))