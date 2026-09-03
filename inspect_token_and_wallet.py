from web3 import Web3
from eth_account import Account

BSC_TESTNET_RPC = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
TOKEN_ADDRESS = Web3.to_checksum_address("0x64544969ed7EBf5f083679233325356EbE738930")

# Minimal ERC-20 ABI to query decimals and symbol
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

def main():
    print("[*] Connecting to BSC Testnet RPC...")
    w3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC))
    
    if not w3.is_connected():
        raise ConnectionError("Failed to connect to BSC Testnet RPC.")
        
    print(f"[*] Connected. Current Block: #{w3.eth.block_number}")

    # 1. Query On-Chain Token Details
    contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=ERC20_ABI)
    try:
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
        print(f"\n--- On-Chain Token Verification ---")
        print(f"Token Address : {TOKEN_ADDRESS}")
        print(f"Token Symbol  : {symbol}")
        print(f"Token Decimals: {decimals}")
    except Exception as e:
        print(f"[!] Could not query contract directly: {e}")
        decimals = None

    # 2. Generate a Brand New Merchant Wallet
    new_merchant = Account.create()
    print(f"\n--- Generated Secure Merchant Wallet ---")
    print(f"Merchant Address    : {new_merchant.address}")
    print(f"Merchant Private Key: {new_merchant.key.hex()}")
    print("----------------------------------------")
    print("Copy these to your .env file as B402_MERCHANT_ADDRESS and SETTLER_PRIVATE_KEY.")

if __name__ == "__main__":
    main()