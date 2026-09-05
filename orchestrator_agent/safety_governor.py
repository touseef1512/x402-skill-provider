"""
Circuit Breaker (Safety Governor)
Monitors purchase patterns and halts trading when safety thresholds are exceeded.

Halt Conditions:
1. Quote exceeds N× (default 2.0x) rolling average price for that skill
2. 2+ consecutive settlement failures  
3. Spend velocity exceeds configured rate (e.g., $1.00/minute)
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque

ROOT_DIR = Path(__file__).resolve().parent.parent

class SafetyGovernor:
    """Circuit breaker for trading safety"""
    
    # Configuration
    PRICE_DEVIATION_THRESHOLD = 2.0  # Halt if quote > 2.0x rolling avg
    CONSECUTIVE_FAILURES_LIMIT = 2   # Halt after 2 consecutive failures
    MAX_SPEND_VELOCITY = 2.00  # Maximum $2.00 per 60 seconds
    SPEND_VELOCITY_WINDOW = 60  # seconds
    ROLLING_AVERAGE_WINDOW = 10  # Number of prices to track
    
    def __init__(self):
        self.halted = False
        self.halt_reason = None
        self.halt_timestamp = None
        
        # Track prices per skill (for rolling average)
        self.price_history: Dict[str, deque] = {}
        
        # Track consecutive failures
        self.consecutive_failures = 0
        self.last_failure_skill = None
        
        # Track spend velocity
        self.spend_history: List[Tuple[float, float]] = []  # [(timestamp, amount)]
        
        # Governor log
        self.log_path = ROOT_DIR / "safety_governor_log.json"
        self.logs = []
        self._load_existing_logs()
    
    def _load_existing_logs(self):
        """Load existing logs from file"""
        if self.log_path.exists():
            try:
                self.logs = json.loads(self.log_path.read_text())
            except:
                self.logs = []
    
    def _save_logs(self):
        """Persist logs to file"""
        self.log_path.write_text(json.dumps(self.logs, indent=2))
    
    def _update_price_history(self, skill: str, price: float):
        """Track price for rolling average calculation"""
        if skill not in self.price_history:
            self.price_history[skill] = deque(maxlen=self.ROLLING_AVERAGE_WINDOW)
        self.price_history[skill].append(price)
    
    def _get_rolling_average(self, skill: str) -> Optional[float]:
        """Get rolling average price for a skill"""
        if skill not in self.price_history or len(self.price_history[skill]) == 0:
            return None
        return sum(self.price_history[skill]) / len(self.price_history[skill])
    
    def _check_price_deviation(self, skill: str, quote_price: float) -> Tuple[bool, Optional[str]]:
        """Check if quote deviates too much from rolling average"""
        rolling_avg = self._get_rolling_average(skill)
        
        if rolling_avg is None:
            # First quote - no baseline yet
            return True, None
        
        deviation_ratio = quote_price / rolling_avg
        
        if deviation_ratio > self.PRICE_DEVIATION_THRESHOLD:
            reason = f"Quote ${quote_price:.4f} exceeds {self.PRICE_DEVIATION_THRESHOLD}x rolling average (${rolling_avg:.4f})"
            return False, reason
        
        return True, None
    
    def _check_consecutive_failures(self, settlement_failed: bool, skill: str) -> Tuple[bool, Optional[str]]:
        """Check for consecutive settlement failures"""
        if settlement_failed:
            if skill == self.last_failure_skill:
                self.consecutive_failures += 1
            else:
                self.consecutive_failures = 1
                self.last_failure_skill = skill
            
            if self.consecutive_failures >= self.CONSECUTIVE_FAILURES_LIMIT:
                reason = f"{self.CONSECUTIVE_FAILURES_LIMIT}+ consecutive settlement failures on {skill}"
                return False, reason
        else:
            # Reset on success
            self.consecutive_failures = 0
            self.last_failure_skill = None
        
        return True, None
    
    def _check_spend_velocity(self, amount: float) -> Tuple[bool, Optional[str]]:
        """Check if spending velocity exceeds limit"""
        now = time.time()
        window_start = now - self.SPEND_VELOCITY_WINDOW
        
        # Remove old spend records outside window
        self.spend_history = [(ts, amt) for ts, amt in self.spend_history if ts > window_start]
        
        # Add current spend
        total_in_window = sum(amt for ts, amt in self.spend_history) + amount
        
        if total_in_window > self.MAX_SPEND_VELOCITY:
            velocity = total_in_window / self.SPEND_VELOCITY_WINDOW * 60  # annualized
            reason = f"Spend velocity ${velocity:.2f}/min exceeds limit ${self.MAX_SPEND_VELOCITY:.2f}/min"
            return False, reason
        
        # Record this spend if check passed
        self.spend_history.append((now, amount))
        return True, None
    
    def check_purchase_safety(
        self,
        symbol: str,
        skill: str,
        quote_price: float,
        settlement_failed: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if purchase is safe
        Returns: (safe: bool, halt_reason: Optional[str])
        """
        if self.halted:
            return False, f"Circuit breaker already halted: {self.halt_reason}"
        
        # Check 1: Price deviation
        safe, reason = self._check_price_deviation(skill, quote_price)
        if not safe:
            self._halt(reason)
            return False, reason
        
        # Check 2: Consecutive failures
        safe, reason = self._check_consecutive_failures(settlement_failed, skill)
        if not safe:
            self._halt(reason)
            return False, reason
        
        # Check 3: Spend velocity
        safe, reason = self._check_spend_velocity(quote_price)
        if not safe:
            self._halt(reason)
            return False, reason
        
        # All checks passed - update price history
        self._update_price_history(skill, quote_price)
        return True, None
    
    def _halt(self, reason: str):
        """Halt trading and log the reason"""
        self.halted = True
        self.halt_reason = reason
        self.halt_timestamp = int(time.time())
        
        log_entry = {
            "timestamp": self.halt_timestamp,
            "event": "circuit_breaker_halted",
            "reason": reason,
            "state": {
                "price_history_count": {sk: len(prices) for sk, prices in self.price_history.items()},
                "consecutive_failures": self.consecutive_failures,
                "last_failure_skill": self.last_failure_skill
            }
        }
        
        self.logs.append(log_entry)
        self._save_logs()
        
        print(f"\n🛑 CIRCUIT BREAKER ACTIVATED!")
        print(f"   Reason: {reason}")
        print(f"   Time: {self.halt_timestamp}")
        print(f"   Halting orchestrator...\n")
    
    def reset(self):
        """Reset the circuit breaker (for testing only)"""
        self.halted = False
        self.halt_reason = None
        self.halt_timestamp = None
        self.consecutive_failures = 0
        self.last_failure_skill = None
        
        log_entry = {
            "timestamp": int(time.time()),
            "event": "circuit_breaker_reset"
        }
        self.logs.append(log_entry)
        self._save_logs()
    
    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        return {
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "halt_timestamp": self.halt_timestamp,
            "price_history_count": {sk: len(prices) for sk, prices in self.price_history.items()},
            "consecutive_failures": self.consecutive_failures,
            "spend_in_window": sum(amt for ts, amt in self.spend_history),
            "config": {
                "price_deviation_threshold": self.PRICE_DEVIATION_THRESHOLD,
                "consecutive_failures_limit": self.CONSECUTIVE_FAILURES_LIMIT,
                "max_spend_velocity": self.MAX_SPEND_VELOCITY
            }
        }
