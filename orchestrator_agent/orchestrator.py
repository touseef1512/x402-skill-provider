import hashlib
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from orchestrator_agent.binance_mcp_client import BinanceMCPClient
import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

from orchestrator_agent.b402_buyer import B402BuyerClient, SecurityException
from orchestrator_agent.safety_governor import SafetyGovernor
from orchestrator_agent.multi_provider_marketplace import PROVIDERS
from groq import Groq

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
buyer = B402BuyerClient()

CATALOG = {
    "news_risk": {
        "name": "Rapid News Exploit & Lawsuit Scanner",
        "endpoint": "http://127.0.0.1:5000/api/skills/news-risk",
        "price_desc": "Fast scan for breaking hacks, exploits, or regulatory actions.",
        "expected_price": 0.50
    },
    "correlation_break": {
        "name": "Cross-Asset Correlation Break Detector",
        "endpoint": "http://127.0.0.1:5000/api/skills/correlation",
        "price_desc": "Detects market decoupling from BTC and ETH.",
        "expected_price": 1.00
    },
    "deep_forensic_risk": {
        "name": "Deep Smart-Contract Forensic Risk Auditor",
        "endpoint": "http://127.0.0.1:5000/api/skills/deep-forensic-risk",
        "price_desc": "Deep contract audit, CVE scan, and governance anomaly analysis.",
        "expected_price": 0.75
    }
}

LEDGER_PATH = ROOT_DIR / "purchase_ledger.json"
DASHBOARD_EVENTS_PATH = ROOT_DIR / "dashboard_events.json"

def emit_dashboard_event(message, event_type="orchestrator"):
    events = []
    if DASHBOARD_EVENTS_PATH.exists():
        try:
            events = json.loads(DASHBOARD_EVENTS_PATH.read_text())
        except Exception:
            events = []
    events.append({"timestamp": int(time.time()), "type": event_type, "message": message})
    DASHBOARD_EVENTS_PATH.write_text(json.dumps(events[-200:], indent=2))

def record_purchase_in_ledger(symbol, skill_key, paid_amount, tx_hash, entry_price, reasoning_text=None):
    ledger = []
    if LEDGER_PATH.exists():
        try:
            ledger = json.loads(LEDGER_PATH.read_text())
        except Exception:
            ledger = []
            
    normalized_tx_hash = tx_hash if not tx_hash or tx_hash.startswith("0x") else f"0x{tx_hash}"
    purchase_entry = {
        "purchase_id": f"px_{int(time.time() * 1000)}",
        "timestamp": int(time.time()),
        "symbol": symbol,
        "skill": skill_key,
        "paid_usdc": paid_amount,
        "entry_price": entry_price,
        "tx_hash": normalized_tx_hash
    }
    
    # Add reasoning hash if provided
    if reasoning_text:
        reasoning_hash = hashlib.sha256(reasoning_text.encode()).hexdigest()
        purchase_entry["reasoning_hash"] = reasoning_hash
        purchase_entry["reasoning_preview"] = reasoning_text[:100]
    
    ledger.append(purchase_entry)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))
    print(f"    ↳ [Ledger] Recorded purchase {purchase_entry['purchase_id']} in purchase_ledger.json")

def fetch_baseline_market_data(symbol: str) -> dict:
    mcp = BinanceMCPClient()
    recon = mcp.get_market_recon(symbol)
    ticker = recon.get("ticker", {})
    last_px = float(ticker.get("lastPrice", 0))
    pct_change = float(ticker.get("priceChangePercent", 0))
    vol_quote = float(ticker.get("quoteVolume", 0))
    transport = recon.get("transport")
    reason = recon.get("degradation_reason")
    if transport == "binance_mcp":
        print(f"    ↳ [Binance Agent OS MCP] Connected via Streamable HTTP (Session: {recon.get("session_id")})")
    else:
        print(f"    ↳ [Binance Agent OS MCP] Notice: {reason}. Operating over Resilient Direct REST.")
    print(mcp.get_transport_report())
    return {
        "symbol": symbol,
        "transport": recon.get("transport"),
        "last_price": last_px,
        "change_24h_percent": pct_change,
        "volume_24h_usdt": vol_quote,
        "high_24h": float(ticker.get("highPrice", 0)),
        "low_24h": float(ticker.get("lowPrice", 0)),
        "weighted_avg_price": float(ticker.get("weightedAvgPrice", 0)),
        "preliminary_bias": "BULLISH" if pct_change > 0 else "BEARISH"
    }

def reason_and_procure(symbol: str, total_budget: float = 2.00, selected_providers: dict = None):
    # Initialize circuit breaker
    governor = SafetyGovernor()
    emit_dashboard_event(f"Started analysis for {symbol}", "session_started")
    
    print(f"\n🚀 Launching The Analyst Orchestrator for: {symbol}")
    print(f"[*] Total Allocation: ${total_budget:.2f} USDC")
    
    baseline = fetch_baseline_market_data(symbol)
    
    # Store reasoning prompt for hashing
    reasoning_prompts = []
    
    print("\n" + "="*70)
    print("🧠 PHASE 1: AUTONOMOUS BUDGET REASONING (Groq - GPT-OSS 120B)")
    print("="*70)
    
    reasoning_prompt = f"""You are 'The Analyst', an autonomous hedge-fund intelligence agent allocating a ${total_budget:.2f} USDC budget.
Free Baseline Signal from Binance:
{json.dumps(baseline, indent=2)}

Available Proprietary Skills:
- 'news_risk': Fast scan for breaking hacks, exploits, or regulatory actions.
- 'correlation_break': Detects market decoupling from BTC/ETH.
- 'deep_forensic_risk': Deep contract audit, CVE scan, and governance anomaly analysis.

Evaluate the baseline signal. Decide which skills are worth buying without exceeding ${total_budget:.2f}.
Respond strictly in JSON format:
{{
  "comparative_reasoning": "...",
  "selected_skills": ["skill_1", "skill_2"]
}}"""

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": reasoning_prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    
    plan = json.loads(response.choices[0].message.content)
    selected_skills = plan.get("selected_skills", ["news_risk"])
    
    # Capture reasoning for ledger
    comparative_reasoning = plan.get("comparative_reasoning", "")
    reasoning_prompts.append({
        "phase": "budget_allocation",
        "text": comparative_reasoning
    })
    
    print(f"\n[Comparative Reasoning Log]:\n{plan.get('comparative_reasoning')}\n")
    print(f"[Procurement Decision]: {selected_skills}")
    emit_dashboard_event(comparative_reasoning, "reasoning")

    print("\n" + "="*70)
    print("💳 PHASE 2: AUTONOMOUS x402 COMMERCE EXECUTION")
    print("="*70)
    
    remaining_budget = total_budget
    intelligence_payloads = {}
    
    for skill_key in selected_skills:
        if skill_key not in CATALOG:
            continue
        skill_meta = CATALOG[skill_key]
        provider_id = (selected_providers or {}).get(skill_key)
        provider = next((item for item in PROVIDERS if item["id"] == provider_id), None)
        purchase_endpoint = skill_meta["endpoint"]
        if provider:
            purchase_endpoint = f"http://127.0.0.1:{provider['port']}/api/{skill_meta['endpoint'].split('/api/', 1)[1]}"
        
        print(f"\n[*] Initiating x402 negotiation for: {skill_meta['name']} [{skill_meta['price_desc']}]")
        if provider:
            print(f"    ↳ Marketplace provider: {provider['id']} on port {provider['port']}")
        emit_dashboard_event(f"Requesting {skill_key} within ${remaining_budget:.2f} budget", "purchase_requested")
        
        try:
            # SEC-08 Enforcement: Pass remaining_budget as max_price_usdc
            result = buyer.post_with_x402(
                purchase_endpoint, 
                {"symbol": symbol},
                max_price_usdc=remaining_budget
            )
            
            data = result.get("data", {})
            settlement = result.get("settlement", {})
            paid = data.get("pricing_applied_usdc", 0.50)
            
            # Check circuit breaker safety before recording
            safe, halt_reason = governor.check_purchase_safety(symbol, skill_key, paid)
            if not halt_reason:
                print(f"[✓] Circuit breaker check passed")
            
            if not safe:
                print(f"[!] Circuit breaker triggered: {halt_reason}")
                print(f"[!] Halting orchestrator - no further purchases")
                break
            
            remaining_budget -= paid
            intelligence_payloads[skill_key] = data
            
            print(f"[✓] Successfully acquired {skill_meta['name']}. Remaining budget: ${remaining_budget:.2f} USDC")
            emit_dashboard_event(f"Settled {skill_key} for ${paid:.2f}; ${remaining_budget:.2f} remains", "settlement")
            print(f"    ↳ [Settlement Audit]")
            print(f"      • Method: {settlement.get('settlement_method')}")
            print(f"      • Status: {settlement.get('status')}")
            print(f"      • Tx Hash: {settlement.get('transaction_hash')}")
            
            # Pass reasoning from budget allocation phase
            record_purchase_in_ledger(
                symbol, skill_key, paid, 
                settlement.get("transaction_hash"), 
                baseline["last_price"],
                reasoning_text=comparative_reasoning
            )
            
        except SecurityException as se:
            print(f"[!] SECURITY HALT: {se}")
            emit_dashboard_event(f"Security halt on {skill_key}: {se}", "security_halt")
        except Exception as e:
            print(f"[!] Procurement failed for {skill_key}: {e}")
            emit_dashboard_event(f"Procurement failed for {skill_key}: {e}", "purchase_failed")
            
    print("\n" + "="*70)
    print("🔍 PURCHASED PROPRIETARY INTELLIGENCE DUMP (Raw)")
    print("="*70)
    print(json.dumps(intelligence_payloads, indent=2))
    
    print("\n" + "="*70)
    print("📊 PHASE 3: FINAL SYNTHESIS & ALPHA GENERATION (Groq - GPT-OSS 120B)")
    print("="*70)
    
    synthesis_prompt = f"""You are 'The Analyst'. Formulate an investment read for {symbol}.
Baseline Signal: {json.dumps(baseline)}
Purchased Intelligence: {json.dumps(intelligence_payloads)}
Spent Budget: ${total_budget - remaining_budget:.2f} USDC | Remaining: ${remaining_budget:.2f} USDC

Provide a concise, direct analysis with STANCE (BULLISH/BEARISH/NEUTRAL), CONFIDENCE %, SUMMARY, KEY FINDINGS, and CAPITAL MANAGEMENT."""

    final_read = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": synthesis_prompt}],
        temperature=0.2
    ).choices[0].message.content
    
    print("\n" + "#"*70)
    print(f"🎯 THE ANALYST FINAL READ: {symbol}")
    print("#"*70)
    print(final_read)
    print("#"*70 + "\n")

if __name__ == "__main__":
    reason_and_procure("SOLUSDT", total_budget=2.00)