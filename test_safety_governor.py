"""
Test script for Safety Governor (Circuit Breaker)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator_agent.safety_governor import SafetyGovernor
import json

def test_circuit_breaker():
    """Test circuit breaker functionality"""
    
    print("\n" + "="*80)
    print("🧪 SAFETY GOVERNOR (CIRCUIT BREAKER) TESTS")
    print("="*80)
    
    governor = SafetyGovernor()
    
    # TEST 1: Normal prices - should pass
    print("\n[TEST 1] Normal prices within rolling average...")
    for i in range(5):
        safe, reason = governor.check_purchase_safety("SOLUSDT", "news_risk", 0.50)
        print(f"  Purchase {i+1}: {'✓ PASS' if safe else '✗ FAIL - ' + str(reason)}")
    
    # TEST 2: Price deviation - should fail
    print("\n[TEST 2] Price deviation exceeds 2x threshold...")
    safe, reason = governor.check_purchase_safety("SOLUSDT", "news_risk", 1.50)
    print(f"  Result: {'✗ HALTED' if not safe else '✓ PASS'}")
    if not safe:
        print(f"  Reason: {reason}")
    
    # Reset for next tests
    governor.reset()
    print("\n[RESET] Circuit breaker reset for next test")
    
    # TEST 3: Consecutive failures
    print("\n[TEST 3] Consecutive settlement failures...")
    safe, reason = governor.check_purchase_safety("SOLUSDT", "correlation_break", 0.60, settlement_failed=True)
    print(f"  Failure 1: {'✓ PASS' if safe else '✗ HALTED'}")
    
    safe, reason = governor.check_purchase_safety("SOLUSDT", "correlation_break", 0.60, settlement_failed=True)
    print(f"  Failure 2: {'✓ PASS' if safe else '✗ HALTED - ' + str(reason)}")
    
    # Reset
    governor.reset()
    print("\n[RESET] Circuit breaker reset for velocity test")
    
    # TEST 4: Spend velocity
    print("\n[TEST 4] Spend velocity exceeds limit...")
    governor.MAX_SPEND_VELOCITY = 1.00  # Reduce limit for testing
    
    safe1, _ = governor.check_purchase_safety("SOLUSDT", "news_risk", 0.40)
    print(f"  Spend 1 ($0.40): {'✓ PASS' if safe1 else '✗ FAIL'}")
    
    safe2, _ = governor.check_purchase_safety("SOLUSDT", "correlation_break", 0.40)
    print(f"  Spend 2 ($0.40): {'✓ PASS' if safe2 else '✗ FAIL'}")
    
    safe3, reason = governor.check_purchase_safety("SOLUSDT", "deep_forensic_risk", 0.40)
    print(f"  Spend 3 ($0.40): {'✗ HALTED - ' + str(reason) if not safe3 else '✓ PASS'}")
    
    # Check status
    print("\n" + "="*80)
    print("📊 CIRCUIT BREAKER STATUS")
    print("="*80)
    status = governor.get_status()
    print(json.dumps(status, indent=2))
    
    # Check logs
    print("\n" + "="*80)
    print("📋 GOVERNOR LOG")
    print("="*80)
    print(json.dumps(governor.logs, indent=2))

if __name__ == "__main__":
    test_circuit_breaker()
