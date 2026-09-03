import os
import re
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv
from solcx import compile_source, install_solc

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

BSC_RPC = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
BUYER_ADDR = Web3.to_checksum_address("0x2708A4dad4BBD4450070C0151D360b6a9ed31165")
SETTLER_KEY = os.getenv("SETTLER_PRIVATE_KEY", "").strip()

if not SETTLER_KEY.startswith("0x") and len(SETTLER_KEY) == 64:
    SETTLER_KEY = "0x" + SETTLER_KEY

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
settler_acc = w3.eth.account.from_key(SETTLER_KEY)

print(f"[*] Deploying EIP-3009 USDC to BSC Testnet (Chain ID: {w3.eth.chain_id})...")
print(f"[*] Settler Deployer : {settler_acc.address}")
print(f"[*] Settler Gas      : {w3.from_wei(w3.eth.get_balance(settler_acc.address), 'ether')} tBNB")

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

compiled = compile_source(SOLIDITY_SOURCE, solc_version="0.8.20")
_, contract_interface = compiled.popitem()
bytecode = contract_interface["bin"]
abi = contract_interface["abi"]

# 1. Deploy Contract
factory = w3.eth.contract(abi=abi, bytecode=bytecode)
deploy_tx = factory.constructor().build_transaction({
    "from": settler_acc.address,
    "nonce": w3.eth.get_transaction_count(settler_acc.address),
    "gas": 2000000,
    "gasPrice": w3.eth.gas_price,
    "chainId": 97
})

signed_deploy = w3.eth.account.sign_transaction(deploy_tx, SETTLER_KEY)
deploy_hash = w3.eth.send_raw_transaction(signed_deploy.raw_transaction)
print(f"[*] Broadcasted deployment tx: https://testnet.bscscan.com/tx/{deploy_hash.hex()}")

receipt = w3.eth.wait_for_transaction_receipt(deploy_hash, timeout=60)
token_addr = receipt.contractAddress
print(f"✅ Contract deployed on BSC Testnet at: {token_addr}")

# 2. Mint 50.00 USDC to Buyer on BSC Testnet
token = w3.eth.contract(address=token_addr, abi=abi)
print(f"[*] Minting 50.00 USDC to Buyer ({BUYER_ADDR})...")
mint_tx = token.functions.mint(BUYER_ADDR, int(50 * 1e18)).build_transaction({
    "from": settler_acc.address,
    "nonce": w3.eth.get_transaction_count(settler_acc.address),
    "gas": 100000,
    "gasPrice": w3.eth.gas_price,
    "chainId": 97
})
signed_mint = w3.eth.account.sign_transaction(mint_tx, SETTLER_KEY)
mint_hash = w3.eth.send_raw_transaction(signed_mint.raw_transaction)
w3.eth.wait_for_transaction_receipt(mint_hash, timeout=60)
print(f"✅ Minted! Tx: https://testnet.bscscan.com/tx/{mint_hash.hex()}")

# 3. Update .env for BSC Testnet production
env_path = ROOT_DIR / ".env"
with open(env_path, "r") as f:
    env_text = f.read()

def update_or_add(text, key, value):
    pattern = rf"^{key}=.*"
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, f"{key}={value}", text, flags=re.MULTILINE)
    return text + f"\n{key}={value}\n"

env_text = update_or_add(env_text, "BSC_TESTNET_RPC", BSC_RPC)
env_text = update_or_add(env_text, "B402_TOKEN_ADDRESS", token_addr)
env_text = update_or_add(env_text, "CHAIN_ID", "97")

with open(env_path, "w") as f:
    f.write(env_text)

print(f"\n[✓] .env permanently updated for BSC Testnet (Chain ID 97):")
print(f"    • B402_TOKEN_ADDRESS = {token_addr}")
print(f"    • BscScan Token Link = https://testnet.bscscan.com/address/{token_addr}")
print("="*60)
