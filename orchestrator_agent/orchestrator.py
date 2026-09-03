import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

from free_binance_skill import fetch_free_binance_signal
from b402_buyer import B402BuyerClient

SKILL_CATALOG = {
    "correlation_break": {
        "name": "Cross-Asset Correlation Break Detector",
        "url": "http://127.0.0.1:5000/api/skills/correlation",
        "cost_usdc": 0.50,
        "description": "Calculates statistical decoupling from BTC/ETH benchmarks over a 48h rolling window."
    },
    "news_risk": {
        "name": "Regulatory & Exploit Security Scanner",
        "url": "http://127.0.0.1:5000/api/skills/news-risk",
        "cost_usdc": 0.50,
        "description": "Live Tavily search scanning for hacks, lawsuits, outages, and vulnerabilities in the last 48h."
    }
}

class TheAnalystOrchestrator:
    def __init__(self, initial_budget_usdc: float = 2.00):
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key or gemini_key.startswith("your_"):
            raise ValueError("GEMINI_API_KEY is missing or unconfigured in .env")
            
        self.ai_client = genai.Client(api_key=gemini_key)
        self.buyer_client = B402BuyerClient()
        self.budget = initial_budget_usdc
        self.initial_budget = initial_budget_usdc
        self.model_name = "gemini-3.6-flash"

    def _generate_with_retry(self, prompt: str, temperature: float = 0.2) -> str:
        """Retries with exponential backoff on temporary 503 traffic spikes."""
        for attempt in range(4):
            try:
                response = self.ai_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=temperature
                    )
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if ("503" in err_str or "UNAVAILABLE" in err_str) and attempt < 3:
                    wait_time = (attempt + 1) * 3
                    print(f"[*] Gemini API 503 temporary demand spike. Retrying in {wait_time}s (Attempt {attempt+1}/4)...")
                    time.sleep(wait_time)
                    continue
                raise e

    def evaluate_budget_and_needs(self, symbol: str, free_data: Dict[str, Any]) -> Dict[str, Any]:
        print("\n" + "="*70)
        print("🧠 PHASE 1: AUTONOMOUS BUDGET REASONING (Gemini 3.6 Flash)")
        print("="*70)

        prompt = f"""
You are "The Analyst", an autonomous economic AI agent evaluating crypto assets on Binance.
You have a strict remaining budget of {self.budget:.2f} USDC. Every skill purchase costs REAL capital over the x402 protocol.

Target Asset: {symbol}
Free Baseline Market Data (0.00 USDC):
- Current Price: ${free_data.get('last_price', 0):,.2f}
- 24h Change: {free_data.get('price_change_percent_24h')}%
- 24h Quote Volume: ${free_data.get('quote_volume_24h_usdt', 0):,.2f}
- 24h VWAP: ${free_data.get('weighted_avg_price', 0):,.2f}
- Baseline Heuristic: {free_data.get('baseline_bias')}

Available Paid Skills Catalog:
1. "correlation_break" (Cost: 0.50 USDC): Identifies statistical price decoupling from BTC/ETH.
2. "news_risk" (Cost: 0.50 USDC): Scans real-time news for hacks, exploits, and regulatory enforcement.

Task:
1. Reason out loud about market uncertainty, risks, and whether each skill provides high expected information value.
2. Decide which skills (if any) to purchase. Do not spend money needlessly.

You must respond ONLY with a JSON object in this schema:
{{
  "chain_of_thought": "Detailed multi-sentence explanation of your economic logic and reasoning...",
  "skills_to_buy": ["correlation_break"]
}}
"""
        raw_text = self._generate_with_retry(prompt, temperature=0.2)
        decision = json.loads(raw_text)
        print(f"\n[Reasoning Log]:\n{decision.get('chain_of_thought')}\n")
        print(f"[Procurement Decision]: {decision.get('skills_to_buy')}")
        return decision

    def execute_skill_purchases(self, symbol: str, skills_to_buy: List[str]) -> Dict[str, Any]:
        print("\n" + "="*70)
        print("💳 PHASE 2: AUTONOMOUS x402 COMMERCE EXECUTION")
        print("="*70)

        purchased_intel = {}

        for skill_key in skills_to_buy:
            if skill_key not in SKILL_CATALOG:
                continue

            skill = SKILL_CATALOG[skill_key]
            cost = skill["cost_usdc"]

            if self.budget < cost:
                print(f"[!] Insufficient budget ({self.budget:.2f} USDC) for {skill['name']}. Skipping.")
                continue

            print(f"\n[*] Initiating x402 micro-payment for: {skill['name']} (${cost:.2f} USDC)")
            try:
                data_response = self.buyer_client.post_with_x402(
                    url=skill["url"],
                    payload={"symbol": symbol}
                )
                
                self.budget -= cost
                purchased_intel[skill_key] = data_response.get("data", {})
                
                settlement = data_response.get("settlement", {})
                print(f"[✓] Successfully acquired {skill['name']}. Remaining budget: ${self.budget:.2f} USDC")
                print("    ↳ [Settlement Audit]")
                print(f"      • Method: {settlement.get('settlement_method')}")
                print(f"      • Status: {settlement.get('status')}")
                if settlement.get("transaction_hash"):
                    print(f"      • Tx Hash: {settlement.get('transaction_hash')}")
                    if settlement.get("explorer_url"):
                        print(f"      • Explorer: {settlement.get('explorer_url')}")
                elif settlement.get("notice"):
                    print(f"      • Notice: {settlement.get('notice')}")

            except Exception as e:
                print(f"[✗] Failed to purchase {skill['name']}: {e}")

        return purchased_intel

    def synthesize_final_verdict(
        self, 
        symbol: str, 
        free_data: Dict[str, Any], 
        paid_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        print("\n" + "="*70)
        print("📊 PHASE 3: FINAL SYNTHESIS & ALPHA GENERATION")
        print("="*70)

        prompt = f"""
You are "The Analyst", producing an institutional crypto analysis.
Target Asset: {symbol}

1. Free Baseline Signal:
{json.dumps(free_data, indent=2)}

2. Purchased Proprietary Intelligence (Over x402):
{json.dumps(paid_data, indent=2)}

Budget Accounting:
- Initial Capital: ${self.initial_budget:.2f} USDC
- Capital Spent: ${(self.initial_budget - self.budget):.2f} USDC
- Capital Preserved: ${self.budget:.2f} USDC

CRITICAL GROUNDING INSTRUCTIONS:
- You MUST NOT state, infer, or hallucinate ANY external facts, token statistics, historical narratives, or price levels not explicitly provided in the Free Baseline or Purchased Proprietary Intelligence JSON above.
- If the risk score is 0.0 with empty matches, state strictly that no active security, exploit, or regulatory risks were detected in the analyzed headlines.
- Only cite prices, volumes, and evidence snippets that appear directly in the JSON above.

Synthesize all evidence into a definitive market stance.
Respond ONLY with a JSON object in this exact schema:
{{
  "market_stance": "BULLISH" | "BEARISH" | "NEUTRAL_UNCERTAIN",
  "confidence_score": 0-100,
  "executive_summary": "2-3 sentences summarizing the thesis grounded strictly in the provided data.",
  "key_findings": [
    "bullet 1 citing explicit data from above",
    "bullet 2 citing explicit data from above",
    "bullet 3 citing explicit data from above"
  ],
  "capital_efficiency_notes": "1 sentence on why the spent funds were or were not justified."
}}
"""
        raw_text = self._generate_with_retry(prompt, temperature=0.1)
        return json.loads(raw_text)

    def run_analysis_cycle(self, symbol: str) -> Dict[str, Any]:
        print(f"\n🚀 Launching The Analyst Orchestrator for: {symbol}")
        print(f"[*] Total Allocation: ${self.budget:.2f} USDC")

        free_signal = fetch_free_binance_signal(symbol)
        procurement = self.evaluate_budget_and_needs(symbol, free_signal)
        skills_to_buy = procurement.get("skills_to_buy", [])

        paid_intel = {}
        if skills_to_buy:
            paid_intel = self.execute_skill_purchases(symbol, skills_to_buy)

        print("\n" + "="*70)
        print("🔍 PURCHASED PROPRIETARY INTELLIGENCE DUMP (Raw)")
        print("="*70)
        print(json.dumps(paid_intel, indent=2))

        verdict = self.synthesize_final_verdict(symbol, free_signal, paid_intel)

        print("\n" + "#"*70)
        print(f"🎯 THE ANALYST FINAL READ: {symbol}")
        print("#"*70)
        print(f"STANCE: {verdict.get('market_stance')} | CONFIDENCE: {verdict.get('confidence_score')}%")
        print(f"\nSUMMARY:\n{verdict.get('executive_summary')}")
        print("\nKEY FINDINGS:")
        for kf in verdict.get("key_findings", []):
            print(f"  • {kf}")
        print(f"\nCAPITAL MANAGEMENT:")
        print(f"  • Spent: ${self.initial_budget - self.budget:.2f} USDC | Remaining: ${self.budget:.2f} USDC")
        print(f"  • Note: {verdict.get('capital_efficiency_notes')}")
        print("#"*70 + "\n")

        return verdict


if __name__ == "__main__":
    analyst = TheAnalystOrchestrator(initial_budget_usdc=2.00)
    analyst.run_analysis_cycle("SOLUSDT")
