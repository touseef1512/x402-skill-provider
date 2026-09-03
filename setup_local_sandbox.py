import re
from pathlib import Path
from web3 import Web3
from eth_account import Account
from solcx import compile_source, install_solc

ROOT_DIR = Path(__file__).resolve().parent
LOCAL_RPC = "http://127.0.0.1:8545"

w3 = Web3(Web3.HTTPProvider(LOCAL_RPC))
if not w3.is_connected():
    raise ConnectionError("Local node is not running on http://127.0.0.1:8545!")

print(f"[*] Connected to local node. Chain ID: {w3.eth.chain_id}")

BUYER_ADDR = Web3.to_checksum_address("0x2708A4dad4BBD4450070C0151D360b6a9ed31165")
SETTLER_ADDR = Web3.to_checksum_address("0xD94156AdB6C3c7D6c666d81a8a64e71616A66D55")

# Account 0 on Anvil default accounts
ANVIL_GENESIS_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
genesis_acc = w3.eth.account.from_key(ANVIL_GENESIS_KEY)

# 1. Fund Buyer and Settler with free local ETH
print("[*] Funding Buyer and Settler with 10 local ETH each...")
for recipient in [BUYER_ADDR, SETTLER_ADDR]:
    tx = {
        "from": genesis_acc.address,
        "to": recipient,
        "value": w3.to_wei(10, "ether"),
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(genesis_acc.address)
    }
    signed = w3.eth.account.sign_transaction(tx, ANVIL_GENESIS_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)

print(f"[✓] Buyer balance  : {w3.from_wei(w3.eth.get_balance(BUYER_ADDR), 'ether')} ETH")
print(f"[✓] Settler balance: {w3.from_wei(w3.eth.get_balance(SETTLER_ADDR), 'ether')} ETH")

# 2. Compile and Deploy USDCCoinEIP3009
print("[*] Installing solc 0.8.20...")
install_solc("0.8.20")

SOLIDITY_SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract USDCCoinEIP3009 {
    string public name = "USD Coin";
    string public symbol = "USDC";
    uint8 public decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => mapping(bytes32 => bool)) public authorizationState;

    bytes32 public immutable DOMAIN_SEPARATOR;
    bytes32 public constant TRANSFER_WITH_AUTHORIZATION_TYPEHASH =
        keccak256("TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)");

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce);

    constructor() {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("USD Coin")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
        _mint(msg.sender, 1000000 * 1e18);
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function _mint(address to, uint256 amount) internal {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function transferWithAuthorization(
        address from,
        address to,
        uint256 value,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(block.timestamp > validAfter, "AUTH_NOT_YET_VALID");
        require(block.timestamp < validBefore, "AUTH_EXPIRED");
        require(!authorizationState[from][nonce], "AUTH_ALREADY_USED");

        bytes32 structHash = keccak256(
            abi.encode(
                TRANSFER_WITH_AUTHORIZATION_TYPEHASH,
                from,
                to,
                value,
                validAfter,
                validBefore,
                nonce
            )
        );

        bytes32 digest = keccak256(
            abi.encodePacked(
                "\\x19\\x01",
                DOMAIN_SEPARATOR,
                structHash
            )
        );

        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0) && signer == from, "INVALID_SIGNATURE");

        authorizationState[from][nonce] = true;
        emit AuthorizationUsed(from, nonce);

        require(balanceOf[from] >= value, "ERC20: transfer amount exceeds balance");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }
}
"""

print("[*] Compiling USDCCoinEIP3009 contract...")
compiled = compile_source(SOLIDITY_SOURCE, solc_version="0.8.20")
_, contract_interface = compiled.popitem()

bytecode = contract_interface["bin"]
abi = contract_interface["abi"]

# Deploy from genesis account
factory = w3.eth.contract(abi=abi, bytecode=bytecode)
deploy_tx = factory.constructor().build_transaction({
    "from": genesis_acc.address,
    "nonce": w3.eth.get_transaction_count(genesis_acc.address),
    "gas": 3000000,
    "gasPrice": w3.eth.gas_price
})
signed = w3.eth.account.sign_transaction(deploy_tx, ANVIL_GENESIS_KEY)
deploy_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(deploy_hash)
token_address = receipt.contractAddress
print(f"[✓] USDCCoinEIP3009 deployed locally at: {token_address}")

# 3. Mint 100 USDC to Buyer
token = w3.eth.contract(address=token_address, abi=abi)
mint_tx = token.functions.mint(BUYER_ADDR, int(100 * 1e18)).build_transaction({
    "from": genesis_acc.address,
    "nonce": w3.eth.get_transaction_count(genesis_acc.address),
    "gas": 100000,
    "gasPrice": w3.eth.gas_price
})
signed_mint = w3.eth.account.sign_transaction(mint_tx, ANVIL_GENESIS_KEY)
mint_hash = w3.eth.send_raw_transaction(signed_mint.raw_transaction)
w3.eth.wait_for_transaction_receipt(mint_hash)
print(f"[✓] Minted 100.00 USDC to Buyer: {BUYER_ADDR}")

# 4. Update .env for local sandbox testing
env_path = ROOT_DIR / ".env"
with open(env_path, "r") as f:
    env_text = f.read()

def update_or_add(text, key, value):
    pattern = rf"^{key}=.*"
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, f"{key}={value}", text, flags=re.MULTILINE)
    return text + f"\n{key}={value}\n"

env_text = update_or_add(env_text, "BSC_TESTNET_RPC", "http://127.0.0.1:8545")
env_text = update_or_add(env_text, "B402_TOKEN_ADDRESS", token_address)
env_text = update_or_add(env_text, "CHAIN_ID", "31337")

with open(env_path, "w") as f:
    f.write(env_text)

print("\n[✓] .env updated for local test:")
print(f"    • BSC_TESTNET_RPC    = http://127.0.0.1:8545")
print(f"    • CHAIN_ID           = 31337")
print(f"    • B402_TOKEN_ADDRESS = {token_address}")
print("="*60)
print("Local sandbox is ready! Now start provider and run orchestrator.")
