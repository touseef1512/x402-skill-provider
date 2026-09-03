import os
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

class B402BuyerClient:
    def __init__(self, private_key: Optional[str] = None):
        env_key = (private_key or os.getenv("BUYER_PRIVATE_KEY") or "").strip()
        if env_key:
            if not env_key.startswith("0x") and len(env_key) == 64:
                env_key = "0x" + env_key
            self.account = Account.from_key(env_key)
            print(f"[*] Buyer initialized with persistent wallet: {self.account.address}")
        else:
            self.account = Account.create()
            print(f"[*] Buyer initialized with ephemeral test wallet: {self.account.address}")

    def sign_authorization(self, reqs: Dict[str, Any]) -> Dict[str, Any]:
        network_str = reqs.get("network", "eip155:31337")
        chain_id = int(network_str.split(":")[1]) if ":" in network_str else 31337

        domain = {
            "name": "USD Coin",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(reqs["token"])
        }

        types = {
            "TransferWithAuthorization": reqs["types"]["TransferWithAuthorization"]
        }

        message = {
            "from": self.account.address,
            "to": Web3.to_checksum_address(reqs["payTo"]),
            "value": int(reqs["amount"]),
            "validAfter": int(reqs["validAfter"]),
            "validBefore": int(reqs["validBefore"]),
            "nonce": bytes.fromhex(reqs["nonce"].replace("0x", ""))
        }

        signable_msg = encode_typed_data(
            domain_data=domain,
            message_types=types,
            message_data=message
        )

        signed = Account.sign_message(signable_msg, private_key=self.account.key)

        return {
            "signature": signed.signature.hex(),
            "authorization": {
                "from": self.account.address,
                "to": reqs["payTo"],
                "value": reqs["amount"],
                "validAfter": reqs["validAfter"],
                "validBefore": reqs["validBefore"],
                "nonce": reqs["nonce"]
            }
        }

    def post_with_x402(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n[Buyer] Requesting resource from: {url}")
        resp = requests.post(url, json=payload, timeout=20)
        
        if resp.status_code == 200:
            print("[Buyer] Resource received without payment requirement.")
            return resp.json()

        if resp.status_code == 402:
            challenge = resp.json()
            reqs = challenge.get("paymentRequirements")
            if not reqs:
                raise RuntimeError(f"Missing paymentRequirements: {resp.text}")

            print(f"[Buyer] 402 Received! Required: {reqs.get('amount_formatted')} on {reqs.get('network')}")
            print(f"[Buyer] Recipient: {reqs.get('payTo')}")

            print("[Buyer] Signing EIP-712 TransferWithAuthorization off-chain...")
            payment_data = self.sign_authorization(reqs)

            authenticated_payload = {
                **payload,
                "payment": payment_data
            }

            print("[Buyer] Resubmitting request with cryptographic payment payload...")
            # Increased timeout to 60s to accommodate on-chain settlement + Tavily search
            paid_resp = requests.post(url, json=authenticated_payload, timeout=60)

            if paid_resp.status_code == 200:
                print("[Buyer] Payment accepted (200 OK)! Resource unlocked.")
                return paid_resp.json()
            else:
                raise RuntimeError(f"Payment submission failed [{paid_resp.status_code}]: {paid_resp.text}")

        raise RuntimeError(f"Unexpected response status [{resp.status_code}]: {resp.text}")
