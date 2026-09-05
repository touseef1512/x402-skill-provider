"""
Negotiation Handler - Manages price negotiations between buyer and providers
Implements one-round negotiation with logging of full exchange
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, List

ROOT_DIR = Path(__file__).resolve().parent.parent
NEGOTIATION_LOG_PATH = ROOT_DIR / "negotiation_history.json"

class NegotiationManager:
    """Manages negotiations between buyer and provider"""
    
    MIN_ACCEPTABLE_FRACTION = 0.85
    
    # Acceptable margin for auto-accept (5% discount threshold)
    ACCEPTABLE_MARGIN = 0.05
    
    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self.negotiations: List = []
    
    @staticmethod
    def get_cost_floor(original_quote: float) -> float:
        """Get the minimum acceptable price for a skill"""
        return original_quote * NegotiationManager.MIN_ACCEPTABLE_FRACTION
    
    @staticmethod
    def evaluate_counter_offer(
        skill: str,
        original_quote: float,
        counter_offer: float,
        reason: str
    ) -> Tuple[bool, str]:
        """
        Evaluate a counter-offer from the buyer
        
        Returns: (accepted: bool, response_message: str)
        """
        cost_floor = NegotiationManager.get_cost_floor(original_quote)
        
        # Validate counter-offer
        if counter_offer < 0:
            return False, "Counter-offer must be positive"
        
        if counter_offer > original_quote:
            return False, "Counter-offer cannot exceed original quote"
        
        # Check if within acceptable margin
        discount_pct = (original_quote - counter_offer) / original_quote
        
        if counter_offer >= cost_floor:
            # Within acceptable range - accept
            return True, f"Counter-offer accepted. Discount: {discount_pct*100:.1f}%"
        else:
            # Below cost floor - reject
            gap = cost_floor - counter_offer
            return False, f"Counter-offer ${counter_offer:.4f} is below cost floor ${cost_floor:.4f} (gap: ${gap:.4f}). Offer rejected once - no further negotiation."
    
    @staticmethod
    def log_negotiation(
        provider_id: str,
        symbol: str,
        skill: str,
        original_quote: float,
        counter_offer: float,
        reason: str,
        accepted: bool,
        response: str,
        claimed_original_quote: Optional[float] = None
    ):
        """Log a negotiation exchange"""
        negotiation_record = {
            "timestamp": int(time.time()),
            "provider": provider_id,
            "symbol": symbol,
            "skill": skill,
            "exchange": {
                "original_quote_usdc": original_quote,
                "client_claimed_original_quote_usdc": claimed_original_quote,
                "buyer_counter_offer_usdc": counter_offer,
                "buyer_reason": reason,
                "accepted": accepted,
                "provider_response": response,
                "discount_pct": round((original_quote - counter_offer) / original_quote * 100, 2) if original_quote > 0 else 0
            }
        }
        
        # Append to log file
        logs = []
        if NEGOTIATION_LOG_PATH.exists():
            try:
                logs = json.loads(NEGOTIATION_LOG_PATH.read_text())
            except:
                logs = []
        
        logs.append(negotiation_record)
        NEGOTIATION_LOG_PATH.write_text(json.dumps(logs, indent=2))
        
        return negotiation_record


class NegotiationSchema:
    """Schema for negotiation requests and responses"""
    
    @staticmethod
    def validate_request(data: Dict) -> Tuple[bool, Optional[str]]:
        """Validate negotiation request format"""
        required_fields = ["quote_id", "symbol", "skill", "original_quote_usdc", "counter_offer_usdc", "reason"]
        
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        if data["counter_offer_usdc"] < 0:
            return False, "counter_offer_usdc must be non-negative"
        
        if len(data.get("reason", "")) > 500:
            return False, "reason must be ≤ 500 characters"
        
        return True, None
    
    @staticmethod
    def create_response(accepted: bool, message: str, counter_offer_approved: Optional[float] = None) -> Dict:
        """Create a standard negotiation response"""
        response = {
            "status": "accepted" if accepted else "rejected",
            "message": message,
            "timestamp": int(time.time())
        }
        
        if accepted and counter_offer_approved is not None:
            response["approved_price_usdc"] = counter_offer_approved
        
        return response
