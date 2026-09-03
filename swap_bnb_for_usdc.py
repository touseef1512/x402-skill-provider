import os
import time
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

BSC_TESTNET_RPC = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
PANCAKE_ROUTER = Web3.to_checksum_address("0x9Ac64Cc6e4415144C455BD8E4837Fea55603e5c3")
WBNB_ADDR = Web3.to_checksum_address("0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd")
USDC_ADDR = Web3.to_checksum_address("0x64544969ed7EBf5f083679233325356EbE738930")

ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

def swap_bnb_for_usdc(amount_bnb: float = 0.01):
    w3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC))
    buyer_key = os.getenv("BUYER_PRIVATE_KEY", "").strip()
    if not buyer_key:
        raise ValueError("BUYER_PRIVATE_KEY not found in .env")
    if not buyer_key.startswith("0x") and len(buyer_key) == 64:
        buyer_key = "0x" + buyer_key

    buyer_account = w3.eth.account.from_key(buyer_key)
    buyer_addr = buyer_account.address

    balance_wei = w3.eth.get_balance(buyer_addr)
    balance_bnb = w3.from_wei(balance_wei, "ether")
    print(f"[*] Buyer address: {buyer_addr}")
    print(f"[*] Current tBNB Balance: {balance_bnb} tBNB")

    swap_wei = w3.to_wei(amount_bnb, "ether")
    if balance_wei < swap_wei:
        raise ValueError(f"Insufficient tBNB! Need at least {amount_bnb} tBNB, have {balance_bnb} tBNB.")

    router = w3.eth.contract(address=PANCAKE_ROUTER, abi=ROUTER_ABI)
    deadline = int(time.time()) + 600
    path = [WBNB_ADDR, USDC_ADDR]

    print(f"[*] Swapping {amount_bnb} tBNB for USDC via PancakeSwap Testnet Router...")

    tx = router.functions.swapExactETHForTokens(
        0,  # Accepts any market slippage on testnet
        path,
        buyer_addr,
        deadline
    ).build_transaction({
        "from": buyer_addr,
        "value": swap_wei,
        "gas": 250000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(buyer_addr),
        "chainId": 97
    })

    signed = w3.eth.account.sign_transaction(tx, buyer_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"[*] Broadcasted swap tx: https://testnet.bscscan.com/tx/{tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    print(f"[✓] Swap confirmed in block #{receipt.blockNumber}!")

    # Check new USDC balance
    usdc_contract = w3.eth.contract(address=USDC_ADDR, abi=ERC20_ABI)
    raw_bal = usdc_contract.functions.balanceOf(buyer_addr).call()
    print(f"[*] New Buyer USDC Balance: {raw_bal / 1e18:.4f} USDC")

if __name__ == "__main__":
    swap_bnb_for_usdc(amount_bnb=0.01)
