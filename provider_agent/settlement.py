import os
from typing import Dict, Any, Tuple, Optional
from web3 import Web3
from dotenv import load_dotenv

load_dotenv(override=True)

# Canonical EIP-3009 transferWithAuthorization ABI
EIP3009_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"}
        ],
        "name": "transferWithAuthorization",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

class PaymentSettlementEngine:
    def __init__(self):
        rpc_url = os.getenv("BSC_TESTNET_RPC")
        if not rpc_url:
            raise ValueError("CONFIGURATION ERROR: 'BSC_TESTNET_RPC' is required in .env")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Strict Settler Key Validation: Zero public dev key fallback
        key = os.getenv("SETTLER_PRIVATE_KEY", "").strip()
        if not key:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: 'SETTLER_PRIVATE_KEY' is missing in .env. "
                "Settlement engine refused to initialize with any insecure fallback keys."
            )
        if not key.startswith("0x") and len(key) == 64:
            key = "0x" + key
        self.settler_private_key = key

        token_env = os.getenv("B402_TOKEN_ADDRESS")
        if not token_env:
            raise ValueError("CONFIGURATION ERROR: 'B402_TOKEN_ADDRESS' is required in .env")
        self.default_token = Web3.to_checksum_address(token_env)

    def check_network_connection(self) -> Tuple[bool, int]:
        try:
            if not self.w3.is_connected():
                return False, 0
            return True, self.w3.eth.block_number
        except Exception:
            return False, 0

    def parse_signature_vrs(self, signature_hex: str) -> Tuple[int, bytes, bytes]:
        clean_sig = signature_hex.replace("0x", "")
        if len(clean_sig) != 130:
            raise ValueError(f"Invalid signature length: {len(clean_sig)} hex chars (expected 130).")

        sig_bytes = bytes.fromhex(clean_sig)
        r = sig_bytes[:32]
        s = sig_bytes[32:64]
        v = int(sig_bytes[64])

        if v < 27:
            v += 27

        return v, r, s

    def settle_payment(
        self, 
        payment_payload: Dict[str, Any],
        token_address: Optional[str] = None
    ) -> Dict[str, Any]:
        auth = payment_payload.get("authorization", {})
        sig = payment_payload.get("signature", "")
        target_token = Web3.to_checksum_address(token_address or self.default_token)

        connected, latest_block = self.check_network_connection()
        if not connected:
            raise ConnectionError(f"Cannot connect to node at {self.w3.provider.endpoint_uri}")

        chain_id = self.w3.eth.chain_id
        v, r, s = self.parse_signature_vrs(sig)
        nonce_bytes = bytes.fromhex(auth["nonce"].replace("0x", ""))

        settler_account = self.w3.eth.account.from_key(self.settler_private_key)
        token_contract = self.w3.eth.contract(address=target_token, abi=EIP3009_ABI)

        print(f"[*] Preparing on-chain transferWithAuthorization on {target_token} (Chain ID: {chain_id})...")

        tx_func = token_contract.functions.transferWithAuthorization(
            Web3.to_checksum_address(auth["from"]),
            Web3.to_checksum_address(auth["to"]),
            int(auth["value"]),
            int(auth["validAfter"]),
            int(auth["validBefore"]),
            nonce_bytes,
            v,
            r,
            s
        )

        nonce = self.w3.eth.get_transaction_count(settler_account.address)
        gas_price = self.w3.eth.gas_price

        tx_params = {
            "chainId": chain_id,
            "from": settler_account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 300000
        }

        try:
            gas_est = tx_func.estimate_gas({"from": settler_account.address})
            tx_params["gas"] = int(gas_est * 1.25)
        except Exception as est_err:
            print(f"[*] Gas estimation note: {est_err}. Defaulting to 300,000 gas limit.")

        built_tx = tx_func.build_transaction(tx_params)
        signed_tx = self.w3.eth.account.sign_transaction(built_tx, self.settler_private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        print(f"[*] Broadcasted tx: {tx_hash.hex()}. Awaiting on-chain receipt...")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        print(f"[✓] Transaction mined in block #{receipt.blockNumber} with status: {receipt.status}")

        explorer_url = f"https://testnet.bscscan.com/tx/{tx_hash.hex()}" if chain_id == 97 else None

        return {
            "settlement_method": "evm_onchain",
            "chain_id": chain_id,
            "token_contract": target_token,
            "transaction_hash": tx_hash.hex(),
            "explorer_url": explorer_url,
            "block_number": receipt.blockNumber,
            "status": "confirmed" if receipt.status == 1 else "reverted",
            "gas_used": receipt.gasUsed
        }
