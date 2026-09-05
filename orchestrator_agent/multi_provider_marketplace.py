"""
Multi-Provider Marketplace Orchestrator
Requests quotes from all providers, compares pricing and specialties,
logs a comparison table, and selects the best value per skill.
"""

import json
import requests
import time
from typing import Dict, List, Tuple
from pathlib import Path
from tabulate import tabulate

ROOT_DIR = Path(__file__).resolve().parent.parent

# Provider endpoints
PROVIDERS = [
    {"id": "provider1_standard", "port": 5000, "name": "Standard"},
    {"id": "provider2_speed_specialist", "port": 5001, "name": "Speed Specialist"},
    {"id": "provider3_value_hunter", "port": 5002, "name": "Value Hunter"},
]

SKILLS = ["news_risk", "correlation_break", "deep_forensic_risk"]

class MultiProviderMarketplace:
    def __init__(self, symbol: str = "SOLUSDT"):
        self.symbol = symbol
        self.quotes: Dict[str, Dict] = {}  # {provider_id: {skill: quote_data}}
        self.comparison_log = []
        self.selected_providers = {}  # {skill: provider_id}
        
    def request_quotes_from_all_providers(self) -> bool:
        """Request quotes from all providers for all skills."""
        print("\n" + "="*80)
        print("🏪 MULTI-PROVIDER MARKETPLACE: FETCHING QUOTES FROM ALL PROVIDERS")
        print("="*80)
        
        # Map skill names to actual endpoint paths
        endpoint_map = {
            "news_risk": "news-risk",
            "correlation_break": "correlation",
            "deep_forensic_risk": "deep-forensic-risk"
        }
        
        for provider in PROVIDERS:
            provider_id = provider["id"]
            port = provider["port"]
            self.quotes[provider_id] = {}
            
            print(f"\n[Provider: {provider['name']} (Port {port})]")
            for skill in SKILLS:
                try:
                    endpoint_path = endpoint_map[skill]
                    endpoint = f"http://127.0.0.1:{port}/api/skills/{endpoint_path}"
                    
                    # First request: get quote
                    response = requests.post(
                        endpoint,
                        json={"symbol": self.symbol},
                        timeout=5
                    )
                    
                    if response.status_code == 402:
                        quote_data = response.json()
                        self.quotes[provider_id][skill] = {
                            "price": quote_data.get("price_usdc"),
                            "quote_id": quote_data.get("quote_id"),
                            "provider": provider_id,
                            "status": "quoted"
                        }
                        print(f"  ✓ {skill}: ${quote_data.get('price_usdc', 'N/A'):.2f} USDC (Quote ID: {quote_data.get('quote_id')})")
                    elif response.status_code == 200:
                        # Some providers might return full data even without auth
                        self.quotes[provider_id][skill] = {
                            "price": response.json().get("data", {}).get("pricing_applied_usdc", 0),
                            "provider": provider_id,
                            "status": "error_no_quote"
                        }
                        print(f"  ✗ {skill}: No quote returned (status 200 instead of 402)")
                    else:
                        self.quotes[provider_id][skill] = {
                            "price": None,
                            "provider": provider_id,
                            "status": f"error_{response.status_code}"
                        }
                        print(f"  ✗ {skill}: Error {response.status_code}")
                        
                except Exception as e:
                    self.quotes[provider_id][skill] = {
                        "price": None,
                        "provider": provider_id,
                        "status": f"error_exception"
                    }
                    print(f"  ✗ {skill}: Exception - {str(e)[:60]}")
        
        # Verify we got at least one quote per skill
        success = True
        for skill in SKILLS:
            prices = [
                self.quotes[p][skill]["price"] 
                for p in self.quotes 
                if self.quotes[p].get(skill, {}).get("price") is not None
            ]
            if not prices:
                print(f"\n[WARNING] No valid quotes received for {skill}")
                success = False
        
        return success
    
    def log_comparison_table(self):
        """Generate and log a pricing comparison table."""
        print("\n" + "="*80)
        print("📊 PRICING COMPARISON TABLE")
        print("="*80)
        
        # Build comparison rows
        rows = []
        for skill in SKILLS:
            row = [skill]
            best_price = None
            best_provider = None
            
            for provider in PROVIDERS:
                provider_id = provider["id"]
                quote = self.quotes.get(provider_id, {}).get(skill, {})
                price = quote.get("price")
                
                if price is not None:
                    row.append(f"${price:.2f}")
                    if best_price is None or price < best_price:
                        best_price = price
                        best_provider = provider_id
                else:
                    row.append("N/A")
            
            # Mark best price
            if best_provider:
                row.append(f"✓ {self.quotes[best_provider][skill]['provider']}")
                self.selected_providers[skill] = best_provider
            else:
                row.append("N/A")
            
            rows.append(row)
        
        # Create table
        headers = ["Skill"] + [p["name"] for p in PROVIDERS] + ["Best Value (Provider)"]
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        
        # Log comparison
        self.comparison_log = {
            "timestamp": int(time.time()),
            "symbol": self.symbol,
            "comparison_table": rows,
            "selected_providers": self.selected_providers
        }
        
        # Save to file
        log_file = ROOT_DIR / "marketplace_comparison.json"
        logs = []
        if log_file.exists():
            logs = json.loads(log_file.read_text())
        logs.append(self.comparison_log)
        log_file.write_text(json.dumps(logs, indent=2))
        
        print(f"\n[✓] Comparison logged to marketplace_comparison.json")
    
    def get_provider_for_skill(self, skill: str) -> str:
        """Get the best provider for a given skill."""
        return self.selected_providers.get(skill, PROVIDERS[0]["id"])
    
    def get_quote_for_skill(self, skill: str) -> Dict:
        """Get quote data for the selected provider's skill."""
        provider_id = self.get_provider_for_skill(skill)
        return self.quotes.get(provider_id, {}).get(skill, {})
    
    def print_marketplace_summary(self):
        """Print a summary of the marketplace comparison."""
        print("\n" + "="*80)
        print("🎯 MARKETPLACE SELECTION SUMMARY")
        print("="*80)
        
        for skill in SKILLS:
            provider_id = self.get_provider_for_skill(skill)
            quote = self.get_quote_for_skill(skill)
            price = quote.get("price", "N/A")
            
            provider_name = next(
                (p["name"] for p in PROVIDERS if p["id"] == provider_id),
                "Unknown"
            )
            
            print(f"  • {skill:25} → {provider_name:20} @ ${price:.2f}" if price != "N/A" else f"  • {skill:25} → {provider_name:20} @ {price}")


if __name__ == "__main__":
    marketplace = MultiProviderMarketplace("SOLUSDT")
    
    if marketplace.request_quotes_from_all_providers():
        marketplace.log_comparison_table()
        marketplace.print_marketplace_summary()
    else:
        print("\n[ERROR] Failed to get quotes from all providers")
