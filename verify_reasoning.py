"""
Verify hashed reasoning receipts from purchase ledger
"""

import json
import hashlib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def verify_reasoning_hash(purchase_id: str, reasoning_text: str) -> dict:
    """
    Verify that a reasoning text matches the hash stored in the purchase ledger
    
    Args:
        purchase_id: Purchase ID to look up
        reasoning_text: The original reasoning text to verify
    
    Returns:
        {
            "match": bool,
            "purchase_id": str,
            "stored_hash": str,
            "computed_hash": str,
            "reasoning_preview": str
        }
    """
    ledger_path = ROOT_DIR / "purchase_ledger.json"
    
    if not ledger_path.exists():
        return {
            "match": False,
            "error": "Purchase ledger not found"
        }
    
    # Load ledger
    try:
        ledger = json.loads(ledger_path.read_text())
    except json.JSONDecodeError:
        return {
            "match": False,
            "error": "Failed to parse purchase ledger"
        }
    
    # Find purchase
    purchase = None
    for p in ledger:
        if p.get("purchase_id") == purchase_id:
            purchase = p
            break
    
    if purchase is None:
        return {
            "match": False,
            "error": f"Purchase ID '{purchase_id}' not found in ledger"
        }
    
    # Compute hash of provided reasoning
    computed_hash = hashlib.sha256(reasoning_text.encode()).hexdigest()
    
    # Get stored hash
    stored_hash = purchase.get("reasoning_hash")
    
    if stored_hash is None:
        return {
            "match": False,
            "purchase_id": purchase_id,
            "error": "No reasoning_hash stored for this purchase",
            "computed_hash": computed_hash
        }
    
    # Compare
    match = computed_hash == stored_hash
    
    return {
        "match": match,
        "purchase_id": purchase_id,
        "stored_hash": stored_hash,
        "computed_hash": computed_hash,
        "reasoning_preview": reasoning_text[:100] + ("..." if len(reasoning_text) > 100 else ""),
        "purchase_details": {
            "timestamp": purchase.get("timestamp"),
            "symbol": purchase.get("symbol"),
            "skill": purchase.get("skill"),
            "paid_usdc": purchase.get("paid_usdc"),
            "tx_hash": purchase.get("tx_hash")
        }
    }


def list_all_reasoning_hashes() -> list:
    """List all purchases with reasoning hashes"""
    ledger_path = ROOT_DIR / "purchase_ledger.json"
    
    if not ledger_path.exists():
        return []
    
    try:
        ledger = json.loads(ledger_path.read_text())
    except json.JSONDecodeError:
        return []
    
    return [
        {
            "purchase_id": p.get("purchase_id"),
            "timestamp": p.get("timestamp"),
            "symbol": p.get("symbol"),
            "skill": p.get("skill"),
            "paid_usdc": p.get("paid_usdc"),
            "tx_hash": p.get("tx_hash"),
            "reasoning_hash": p.get("reasoning_hash", "NOT SET")
        }
        for p in ledger
    ]


if __name__ == "__main__":
    import sys
    
    print("\n" + "="*80)
    print("🔐 REASONING RECEIPT VERIFICATION")
    print("="*80)
    
    # Show all purchases
    print("\n📋 PURCHASES WITH REASONING HASHES:")
    purchases = list_all_reasoning_hashes()
    
    if not purchases:
        print("  (No purchases found)")
    else:
        for p in purchases:
            status = "✓" if p["reasoning_hash"] != "NOT SET" else "✗"
            print(f"  {status} {p['purchase_id']} | {p['symbol']} | {p['skill']} | ${p['paid_usdc']}")
            print(f"    Hash: {p['reasoning_hash']}")
    
    # Interactive verification
    if len(sys.argv) > 1:
        print("\n" + "="*80)
        print("🔍 VERIFICATION TEST")
        print("="*80)
        
        purchase_id = sys.argv[1]
        reasoning_text = sys.argv[2] if len(sys.argv) > 2 else "Sample reasoning text"
        
        result = verify_reasoning_hash(purchase_id, reasoning_text)
        
        if result.get("match"):
            print(f"\n✅ VERIFICATION PASSED")
        else:
            print(f"\n❌ VERIFICATION FAILED")
            if result.get("error"):
                print(f"   Error: {result['error']}")
        
        print(f"\n   Purchase ID: {result.get('purchase_id')}")
        print(f"   Reasoning: {result.get('reasoning_preview')}")
        print(f"   Stored Hash: {result.get('stored_hash', 'N/A')}")
        print(f"   Computed Hash: {result.get('computed_hash')}")
