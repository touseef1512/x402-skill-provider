import os
import json
import time
import secrets
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from web3 import Web3
from eth_account.messages import encode_typed_data
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

class SecurityException(Exception):
    """Raised when an on-chain or off-chain cryptographic security boundary is violated."""
    pass

class B402BuyerClient:
    def __init__(self):
        rpc_url = os.getenv("RPC_URL", "http://127.0.0.1:8545")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.private_key = os.getenv("BUYER_PRIVATE_KEY")
        if not self.private_key:
            raise ValueError("BUYER_PRIVATE_KEY is missing from environment")
        
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.usdc_contract = os.getenv("USDC_CONTRACT_ADDRESS")
        if not self.usdc_contract or not self.usdc_contract.strip():
            raise ValueError("USDC_CONTRACT_ADDRESS is missing from environment")
        self.usdc_contract = self.usdc_contract.strip()
        self.chain_id = self.w3.eth.chain_id
        print(f"[*] Buyer initialized: {self.account.address} on Chain ID: {self.chain_id}")

    def sign_eip3009_authorization(self, payee: str, amount_usdc: float) -> Dict[str, Any]:
        amount_units = int(round(amount_usdc * 10**6))
        valid_after = 0
        valid_before = int(time.time()) + 3600
        
        # 32 bytes raw entropy formatted to strictly 64 hex characters
        raw_nonce = secrets.token_bytes(32)
        nonce_hex = raw_nonce.hex()

        full_message = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                "TransferWithAuthorization": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"}
                ]
            },
            "primaryType": "TransferWithAuthorization",
            "domain": {
                "name": "USD Coin",
                "version": "1",
                "chainId": self.chain_id,
                "verifyingContract": Web3.to_checksum_address(self.usdc_contract)
            },
            "message": {
                "from": Web3.to_checksum_address(self.account.address),
                "to": Web3.to_checksum_address(payee),
                "value": amount_units,
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": raw_nonce
            }
        }

        signable = encode_typed_data(full_message=full_message)
        signed = self.account.sign_message(signable)

        return {
            "from": self.account.address,
            "to": payee,
            "value": str(amount_units),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce_hex,
            "v": signed.v,
            "r": f"{signed.r:064x}",
            "s": f"{signed.s:064x}"
        }

    def post_with_x402(self, url: str, payload: Dict[str, Any], max_price_usdc: Optional[float] = None) -> Dict[str, Any]:
        print(f"[Buyer] Requesting resource: {url}")
        res = requests.post(url, json=payload)
        
        if res.status_code == 402:
            challenge = res.json()
            price = challenge.get("price_usdc")
            payee = challenge.get("payee")
            quote_id = challenge.get("quote_id")
            network = challenge.get("network")
            
            # SEC-08 Mitigation: Guard against blind signing and drain attacks
            if max_price_usdc is not None and price > max_price_usdc:
                raise SecurityException(
                    f"CRITICAL: Quoted price {price:.2f} USDC exceeds maximum authorized budget of {max_price_usdc:.2f} USDC. Aborting transaction."
                )
            
            print(f"[Buyer] 402 Received! Required: {price:.2f} USDC (Quote: {quote_id}) on {network}")
            auth_payload = self.sign_eip3009_authorization(payee, price)
            
            if quote_id:
                auth_payload["quote_id"] = quote_id
                payload["quote_id"] = quote_id

            headers = {"X-Payment-Authorization": json.dumps(auth_payload)}
            print("[Buyer] Submitting cryptographically signed EIP-712 authorization...")
            res2 = requests.post(url, json=payload, headers=headers)
            
            if res2.status_code == 200:
                print("[Buyer] Payment verified on-chain (200 OK)! Intelligence unlocked.")
                return res2.json()
            else:
                raise RuntimeError(f"Payment rejected ({res2.status_code}): {res2.text}")
        elif res.status_code == 200:
            return res.json()
        else:
            raise RuntimeError(f"Unexpected initial status ({res.status_code}): {res.text}")
