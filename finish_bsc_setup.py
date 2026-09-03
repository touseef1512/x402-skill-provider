import os
import re
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

BSC_RPC = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
TOKEN_ADDR = Web3.to_checksum_address("0xadf72084A92d4D0f45536067F3FF3b65eA192609")
BUYER_ADDR = Web3.to_checksum_address("0x2708A4dad4BBD4450070C0151D360b6a9ed31165")
SETTLER_KEY = os.getenv("SETTLER_PRIVATE_KEY", "").strip()

if not SETTLER_KEY.startswith("0x") and len(SETTLER_KEY) == 64:
    SETTLER_KEY = "0x" + SETTLER_KEY

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
settler_acc = w3.eth.account.from_key(SETTLER_KEY)

print(f"[*] Connected to BSC Testnet (Chain ID: {w3.eth.chain_id})")
print(f"[*] Target Token: {TOKEN_ADDR}")
print(f"[*] Settler Address: {settler_acc.address}")

# Minimal ABI for mint and balanceOf
MINT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

token = w3.eth.contract(address=TOKEN_ADDR, abi=MINT_ABI)

# Fetch latest pending nonce
nonce = w3.eth.get_transaction_count(settler_acc.address, "pending")
print(f"[*] Using fresh nonce: {nonce}")
print(f"[*] Minting 50.00 USDC to Buyer ({BUYER_ADDR})...")

mint_tx = token.functions.mint(BUYER_ADDR, int(50 * 1e18)).build_transaction({
    "from": settler_acc.address,
    "nonce": nonce,
    "gas": 100000,
    "gasPrice": w3.eth.gas_price,
    "chainId": 97
})

signed_mint = w3.eth.account.sign_transaction(mint_tx, SETTLER_KEY)
mint_hash = w3.eth.send_raw_transaction(signed_mint.raw_transaction)
print(f"[*] Broadcasted mint tx: https://testnet.bscscan.com/tx/{mint_hash.hex()}")

receipt = w3.eth.wait_for_transaction_receipt(mint_hash, timeout=60)
print(f"[✓] Mint confirmed in block #{receipt.blockNumber}!")

buyer_bal = token.functions.balanceOf(BUYER_ADDR).call()
print(f"[*] Buyer USDC Balance on BSC Testnet: {buyer_bal / 1e18:.2f} USDC")

# Update .env
env_path = ROOT_DIR / ".env"
with open(env_path, "r") as f:
    env_text = f.read()

def update_or_add(text, key, value):
    pattern = rf"^{key}=.*"
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, f"{key}={value}", text, flags=re.MULTILINE)
    return text + f"\n{key}={value}\n"

env_text = update_or_add(env_text, "BSC_TESTNET_RPC", BSC_RPC)
env_text = update_or_add(env_text, "B402_TOKEN_ADDRESS", TOKEN_ADDR)
env_text = update_or_add(env_text, "CHAIN_ID", "97")

with open(env_path, "w") as f:
    f.write(env_text)

print("\n[✓] .env updated for BSC Testnet:")
print(f"    • BSC_TESTNET_RPC    = {BSC_RPC}")
print(f"    • CHAIN_ID           = 97")
print(f"    • B402_TOKEN_ADDRESS = {TOKEN_ADDR}")
print("=" * 60)
