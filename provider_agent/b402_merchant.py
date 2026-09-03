import os
import time
import secrets
from typing import Dict, Any, Tuple
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from dotenv import load_dotenv

load_dotenv(override=True)

CHAIN_ID = int(os.getenv("CHAIN_ID", 97))
DEFAULT_NETWORK = f"eip155:{CHAIN_ID}"
USDC_DECIMALS = 18

def get_token_address() -> str:
    return os.getenv("B402_TOKEN_ADDRESS", "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0")

def get_merchant_address() -> str:
    return os.getenv("B402_MERCHANT_ADDRESS", "0xD94156AdB6C3c7D6c666d81a8a64e71616A66D55")

def get_eip712_types() -> Dict[str, Any]:
    return {
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
    }

def create_payment_requirements(
    resource_id: str,
    price_usdc: float = 0.50,
    validity_seconds: int = 300
) -> Dict[str, Any]:
    now = int(time.time())
    units = int(price_usdc * (10 ** USDC_DECIMALS))
    nonce = "0x" + secrets.token_hex(32)

    current_chain = int(os.getenv("CHAIN_ID", 97))

    return {
        "x402Version": 2,
        "resource": resource_id,
        "scheme": "exact",
        "network": f"eip155:{current_chain}",
        "token": Web3.to_checksum_address(get_token_address()),
        "amount": str(units),
        "amount_formatted": f"{price_usdc:.2f} USDC",
        "payTo": Web3.to_checksum_address(get_merchant_address()),
        "validAfter": now - 60,
        "validBefore": now + validity_seconds,
        "nonce": nonce,
        "types": get_eip712_types()
    }

def verify_eip712_payment_signature(
    payment_payload: Dict[str, Any],
    expected_requirements: Dict[str, Any]
) -> Tuple[bool, str]:
    try:
        auth = payment_payload.get("authorization", {})
        signature = payment_payload.get("signature")

        if not signature:
            return False, "Missing signature in payment payload."

        if Web3.to_checksum_address(auth.get("to")) != Web3.to_checksum_address(expected_requirements["payTo"]):
            return False, f"Recipient mismatch: {auth.get('to')} vs {expected_requirements['payTo']}"

        if str(auth.get("value")) != str(expected_requirements["amount"]):
            return False, f"Authorized value {auth.get('value')} does not match required {expected_requirements['amount']}."

        now = int(time.time())
        if now < auth.get("validAfter", 0) or now > auth.get("validBefore", 0):
            return False, "Authorization signature is outside validity window."

        network_str = expected_requirements.get("network", "eip155:31337")
        chain_id = int(network_str.split(":")[1]) if ":" in network_str else 31337

        domain = {
            "name": "USD Coin",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(expected_requirements["token"])
        }

        types = {
            "TransferWithAuthorization": get_eip712_types()["TransferWithAuthorization"]
        }

        message = {
            "from": Web3.to_checksum_address(auth.get("from")),
            "to": Web3.to_checksum_address(auth.get("to")),
            "value": int(auth.get("value")),
            "validAfter": int(auth.get("validAfter")),
            "validBefore": int(auth.get("validBefore")),
            "nonce": bytes.fromhex(auth.get("nonce").replace("0x", ""))
        }

        signable = encode_typed_data(
            domain_data=domain,
            message_types=types,
            message_data=message
        )

        recovered_address = Account.recover_message(signable, signature=signature)
        expected_from = Web3.to_checksum_address(auth.get("from"))

        if recovered_address.lower() != expected_from.lower():
            return False, f"Signature mismatch: recovered {recovered_address} vs expected {expected_from}"

        return True, recovered_address

    except Exception as e:
        return False, f"Cryptographic verification error: {str(e)}"
