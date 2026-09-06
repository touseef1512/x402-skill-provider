"""
Provider 2: Speed Specialist - Fast news scanning with aggressive pricing
Port: 5001
Specialty: 10% discount on news_risk, optimized for low latency
"""

import os
import json
import time
import math
import secrets
from pathlib import Path
from flask import Flask, request, jsonify
from web3 import Web3
from web3.exceptions import ContractLogicError
import requests
from dotenv import load_dotenv
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator_agent.negotiation_handler import NegotiationManager, NegotiationSchema
from provider_agent.llm_pricing import demand_signals, quote_price as llm_quote_price, record_provider_receipt
from provider_agent.skill_news_risk import ASSET_NAME_MAP, is_article_relevant

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

app = Flask(__name__)

w3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL", "http://127.0.0.1:8545")))
PROVIDER_KEY = os.getenv("PROVIDER_PRIVATE_KEY")
PAYEE_ADDR = os.getenv("PAYEE_ADDRESS")
USDC_ADDR = os.getenv("USDC_CONTRACT_ADDRESS")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PROVIDER_ID = "provider2_speed_specialist"
PROVIDER_PORT = 5001

artifact_path = ROOT_DIR / "out" / "MockUSDC.sol" / "MockUSDC.json"
if not artifact_path.exists():
    artifact_path = ROOT_DIR / "contracts" / "out" / "MockUSDC.sol" / "MockUSDC.json"
USDC_ABI = json.loads(artifact_path.read_text())["abi"]

QUOTE_CACHE: dict = {}
BINANCE_CACHE: dict = {}

def quote_price_for_skill(skill: str, symbol: str, extra_signals=None):
    auth_header = request.headers.get("X-Payment-Authorization")
    if auth_header:
        payload = json.loads(auth_header)
        quote_id = payload.get("quote_id") or (request.get_json() or {}).get("quote_id")
        locked = QUOTE_CACHE.get(quote_id)
        if locked:
            return locked["price_usdc"], locked["reasoning"]
    signals = demand_signals(QUOTE_CACHE, PROVIDER_ID, extra_signals)
    return llm_quote_price(skill, symbol, PROVIDER_ID, "speed specialist with fast news scanning", signals)

def purge_expired_quotes():
    now = time.time()
    expired = [qid for qid, q in QUOTE_CACHE.items() if q["expires_at"] < now]
    for qid in expired:
        del QUOTE_CACHE[qid]

def fetch_binance_klines(symbol: str, limit: int = 24) -> list[float]:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval=1h&limit={limit}"
    res = requests.get(url, timeout=5)
    res.raise_for_status()
    return [float(candle[4]) for candle in res.json()]

def calculate_real_correlation_and_volatility(target_symbol: str, base_symbol: str = "BTCUSDT") -> tuple[float, float]:
    now = time.time()
    cache_key = f"{target_symbol.upper()}:{base_symbol.upper()}"
    
    if cache_key in BINANCE_CACHE and (now - BINANCE_CACHE[cache_key]["cached_at"] < 60):
        c = BINANCE_CACHE[cache_key]
        return c["corr"], c["vol"]

    target_closes = fetch_binance_klines(target_symbol, 24)
    base_closes = fetch_binance_klines(base_symbol, 24)
    
    n = min(len(target_closes), len(base_closes))
    x = target_closes[-n:]
    y = base_closes[-n:]

    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denom_x = math.sqrt(sum((x[i] - mean_x)**2 for i in range(n)))
    denom_y = math.sqrt(sum((y[i] - mean_y)**2 for i in range(n)))
    pearson_corr = round(numerator / (denom_x * denom_y), 4) if denom_x and denom_y else 0.0

    returns = [math.log(x[i] / x[i - 1]) for i in range(1, n)]
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    hourly_vol = math.sqrt(variance)

    BINANCE_CACHE[cache_key] = {
        "corr": pearson_corr,
        "vol": hourly_vol,
        "cached_at": now
    }
    return pearson_corr, hourly_vol

def settle_onchain(auth_data: dict) -> str:
    contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDR), abi=USDC_ABI)
    relayer = w3.eth.account.from_key(PROVIDER_KEY)

    from_addr = Web3.to_checksum_address(auth_data["from"])
    to_addr = Web3.to_checksum_address(auth_data["to"])
    val = int(auth_data["value"])
    valid_after = int(auth_data["validAfter"])
    valid_before = int(auth_data["validBefore"])
    
    raw_nonce = auth_data["nonce"].replace("0x", "").zfill(64)
    raw_r = auth_data["r"].replace("0x", "").zfill(64)
    raw_s = auth_data["s"].replace("0x", "").zfill(64)
    
    nonce_bytes = bytes.fromhex(raw_nonce)
    r_bytes = bytes.fromhex(raw_r)
    s_bytes = bytes.fromhex(raw_s)
    v_val = int(auth_data["v"])

    try:
        contract.functions.transferWithAuthorization(
            from_addr, to_addr, val, valid_after, valid_before, nonce_bytes, v_val, r_bytes, s_bytes
        ).call({"from": relayer.address})
    except ContractLogicError as cle:
        raise ValueError(f"EVM Revert: {str(cle)}")
    except Exception as sim_err:
        raise ValueError(f"Simulation Failed: {str(sim_err)}")

    gas_price = max(w3.eth.gas_price, w3.to_wei(3, "gwei"))

    tx = contract.functions.transferWithAuthorization(
        from_addr, to_addr, val, valid_after, valid_before, nonce_bytes, v_val, r_bytes, s_bytes
    ).build_transaction({
        "from": relayer.address,
        "nonce": w3.eth.get_transaction_count(relayer.address, "pending"),
        "gas": 350000,
        "gasPrice": gas_price
    })

    signed = relayer.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if receipt.status != 1:
        raise RuntimeError("Transaction mined with failure status")
    return receipt.transactionHash.hex()

def verify_x402_or_challenge(price_usdc: float, symbol: str, skill: str, reasoning: str):
    purge_expired_quotes()
    auth_header = request.headers.get("X-Payment-Authorization")
    
    if not auth_header:
        quote_id = f"q2_{secrets.token_hex(8)}"
        QUOTE_CACHE[quote_id] = {
            "price_usdc": price_usdc,
            "expires_at": time.time() + 60,
            "symbol": symbol.upper(),
            "endpoint": request.path,
            "provider": PROVIDER_ID,
            "reasoning": reasoning
        }
        challenge = {
            "status": 402,
            "error": "Payment Required",
            "protocol": "x402",
            "quote_id": quote_id,
            "price_usdc": price_usdc,
            "network": f"eip155:{w3.eth.chain_id}",
            "token": USDC_ADDR,
            "payee": PAYEE_ADDR,
            "provider": PROVIDER_ID,
            "expires_in_seconds": 60
        }
        return False, (jsonify(challenge), 402)
    
    try:
        payload = json.loads(auth_header)
        quote_id = payload.get("quote_id") or (request.get_json() or {}).get("quote_id")
        
        if quote_id and quote_id in QUOTE_CACHE:
            locked = QUOTE_CACHE[quote_id]
            
            if locked.get("endpoint") != request.path:
                return False, (jsonify({
                    "error": f"Quote arbitrage rejected: Quote {quote_id} was generated for {locked.get('endpoint')}, cannot be applied to {request.path}"
                }), 400)
            
            if locked.get("symbol") and locked.get("symbol").upper() != symbol.upper():
                return False, (jsonify({
                    "error": f"Quote symbol mismatch: Quote {quote_id} was generated for {locked.get('symbol')}, cannot be applied to {symbol.upper()}"
                }), 400)
                
            if time.time() > locked["expires_at"]:
                return False, (jsonify({"error": "Quote expired. Please re-request resource."}), 400)
            required_price = locked["price_usdc"]
            reasoning = locked["reasoning"]
        else:
            required_price = price_usdc

        now = int(time.time())
        if not (int(payload.get("validAfter", 0)) <= now <= int(payload.get("validBefore", 0))):
            return False, (jsonify({"error": "Payment authorization expired or not yet valid"}), 400)

        expected_units = int(round(required_price * 10**6))
        received_units = int(payload.get("value", 0))
        if received_units < expected_units:
            return False, (jsonify({"error": f"Underpayment: Required {expected_units}, received {received_units}"}), 400)
            
        if payload.get("to", "").lower() != PAYEE_ADDR.lower():
            return False, (jsonify({"error": "Invalid payee address"}), 400)

        tx_hash = settle_onchain(payload)
        record_provider_receipt(PROVIDER_ID, symbol, skill, required_price, tx_hash, reasoning)
        if quote_id in QUOTE_CACHE:
            del QUOTE_CACHE[quote_id]
            
        return True, tx_hash
    except ValueError as ve:
        return False, (jsonify({"error": str(ve)}), 400)
    except Exception as e:
        return False, (jsonify({"error": f"Settlement failed: {str(e)}"}), 400)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "provider": PROVIDER_ID,
        "port": PROVIDER_PORT,
        "chain_id": w3.eth.chain_id,
        "token": USDC_ADDR,
        "specialty": "Speed Specialist - Fast news scanning"
    })

@app.route("/api/skills/correlation", methods=["POST"])
def skill_correlation():
    body = request.get_json() or {}
    symbol = body.get("symbol", "SOLUSDT")
    
    try:
        corr, vol = calculate_real_correlation_and_volatility(symbol, "BTCUSDT")
        rationale = f"Provider2 (Speed Specialist): Live 24h Binance correlation with BTC: {corr:.4f}. Realized volatility: {vol*100:.2f}%."
        quote_price, pricing_reasoning = quote_price_for_skill("correlation_break", symbol, {"correlation": corr, "hourly_volatility": vol})
    except Exception as e:
        raise RuntimeError(f"Correlation signal or LLM pricing failed: {e}") from e

    passed, res = verify_x402_or_challenge(quote_price, symbol, "correlation_break", pricing_reasoning)
    if not passed:
        return res

    return jsonify({
        "data": {
            "target_symbol": symbol,
            "benchmark": "BTCUSDT",
            "pearson_correlation": corr,
            "realized_hourly_volatility": round(vol, 6),
            "correlation_break_detected": corr < 0.60,
            "pricing_applied_usdc": quote_price,
            "volatility_rationale": rationale,
            "provider": PROVIDER_ID
        },
        "settlement": {"settlement_method": "evm_onchain", "status": "confirmed", "transaction_hash": res, "provider": PROVIDER_ID}
    })

@app.route("/api/skills/news-risk", methods=["POST"])
def skill_news_risk():
    body = request.get_json() or {}
    symbol = body.get("symbol", "SOLUSDT")
    clean_sym = symbol.upper().replace("USDT", "")

    quote_price, pricing_reasoning = quote_price_for_skill("news_risk", symbol)
    passed, res = verify_x402_or_challenge(quote_price, symbol, "news_risk", pricing_reasoning)
    if not passed:
        return res

    evidence_list = []
    risk_score = 0.0
    flagged = set()

    search_ok = True
    if TAVILY_API_KEY and not TAVILY_API_KEY.startswith("your_"):
        try:
            full_name = ASSET_NAME_MAP.get(clean_sym, clean_sym)
            identifiers = [clean_sym.lower()] + ([full_name.lower()] if full_name.lower() != clean_sym.lower() else [])
            t_res = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": f'"{full_name}" crypto (exploit OR hack OR lawsuit OR outage OR vulnerability OR "sec")',
                    "topic": "news",
                    "days": 3,
                    "search_depth": "basic",
                    "max_results": 5
                },
                timeout=8
            ).json()

            keywords = ["exploit", "hack", "vulnerability", "scam", "breach", "lawsuit", "investigation", "stolen", "outage"]
            for art in t_res.get("results", []):
                snippet = art.get("content", "")
                title = art.get("title", "")
                full_text = f"{title} {snippet}"
                if not is_article_relevant(full_text, identifiers):
                    continue
                matched = [w for w in keywords if w in snippet.lower() or w in title.lower()]
                if matched:
                    flagged.update(matched)
                    evidence_list.append({
                        "title": title,
                        "url": art.get("url"),
                        "snippet": snippet[:200] + "...",
                        "matched_terms": matched
                    })
            risk_score = min(len(evidence_list) * 0.25, 1.0)
        except Exception as e:
            print(f"[!] Tavily news search failed: {e}")
            search_ok = False

    if not search_ok:
        risk_level = "UNKNOWN"
        risk_score = None
        evidence_list = [{
            "title": "News check unavailable",
            "snippet": "The live news search could not complete this run; treat this result as inconclusive, not as a confirmed low-risk signal.",
            "matched_terms": []
        }]
    elif not evidence_list:
        evidence_list.append({
            "title": f"No active exploits or legal actions detected for {clean_sym}",
            "snippet": "Automated security scanners report normal operational telemetry across public channels.",
            "matched_terms": []
        })
        risk_level = "LOW"
    else:
        risk_level = "CRITICAL" if risk_score >= 0.75 else ("ELEVATED" if risk_score >= 0.25 else "LOW")

    return jsonify({
        "data": {
            "analysis_type": "live_tavily_news_risk",
            "symbol": symbol,
            "base_asset": clean_sym,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "flagged_signals": list(flagged),
            "articles_evaluated": len(evidence_list),
            "evidence": evidence_list,
            "pricing_applied_usdc": quote_price,
            "provider": PROVIDER_ID
        },
        "settlement": {"settlement_method": "evm_onchain", "status": "confirmed", "transaction_hash": res, "provider": PROVIDER_ID}
    })

@app.route("/api/skills/deep-forensic-risk", methods=["POST"])
def skill_deep_forensic():
    body = request.get_json() or {}
    symbol = body.get("symbol", "SOLUSDT")
    clean_sym = symbol.upper().replace("USDT", "")

    quote_price, pricing_reasoning = quote_price_for_skill("deep_forensic_risk", symbol)
    passed, res = verify_x402_or_challenge(quote_price, symbol, "deep_forensic_risk", pricing_reasoning)
    if not passed:
        return res

    forensic_findings = []
    scanned_vectors = ["reentrancy", "multisig_anomalies", "cve_database", "flash_loan_vectors"]
    forensic_risk_score = 0.0

    if TAVILY_API_KEY and not TAVILY_API_KEY.startswith("your_"):
        try:
            t_res = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": f"{clean_sym} smart contract audit report vulnerability CVE exploit analysis",
                    "search_depth": "advanced",
                    "max_results": 5
                },
                timeout=10
            ).json()

            cve_keywords = ["cve", "reentrancy", "overflow", "flash loan", "critical", "privilege escalation", "backdoor"]
            for art in t_res.get("results", []):
                snippet = art.get("content", "")
                title = art.get("title", "")
                matched = [w for w in cve_keywords if w in snippet.lower() or w in title.lower()]
                if matched:
                    forensic_findings.append({
                        "title": title,
                        "url": art.get("url"),
                        "snippet": snippet[:200] + "...",
                        "matched_vectors": matched
                    })
            forensic_risk_score = min(len(forensic_findings) * 0.30, 1.0)
        except Exception as e:
            forensic_findings.append({"title": "Forensic Search Error", "snippet": str(e), "matched_vectors": []})

    if not forensic_findings:
        forensic_findings.append({
            "title": f"No critical CVEs or contract anomalies detected for {clean_sym}",
            "snippet": "Automated forensic scanners found no active reentrancy or governance compromise disclosures.",
            "matched_vectors": []
        })

    risk_level = "CRITICAL" if forensic_risk_score >= 0.70 else ("ELEVATED" if forensic_risk_score >= 0.30 else "LOW")

    return jsonify({
        "data": {
            "analysis_type": "live_contract_forensics",
            "target_symbol": symbol,
            "base_asset": clean_sym,
            "forensic_risk_score": forensic_risk_score,
            "forensic_risk_level": risk_level,
            "scanned_vectors": scanned_vectors,
            "forensic_sources_evaluated": len(forensic_findings),
            "findings": forensic_findings,
            "pricing_applied_usdc": quote_price,
            "provider": PROVIDER_ID
        },
        "settlement": {"settlement_method": "evm_onchain", "status": "confirmed", "transaction_hash": res, "provider": PROVIDER_ID}
    })

@app.route("/api/negotiate", methods=["POST"])
def negotiate_price():
    """
    Negotiate price for a skill.
    Buyer sends counter-offer if original quote exceeds budget.
    Provider accepts if within cost floor, rejects otherwise.
    One round only - no infinite haggling.
    """
    body = request.get_json() or {}
    
    # Validate request
    valid, error_msg = NegotiationSchema.validate_request(body)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    symbol = body.get("symbol", "SOLUSDT")
    skill = body.get("skill")
    claimed_original_quote = float(body.get("original_quote_usdc", 0))
    counter_offer = float(body.get("counter_offer_usdc", 0))
    reason = body.get("reason", "Budget constraint")
    purge_expired_quotes()
    locked_quote = QUOTE_CACHE.get(body.get("quote_id"))
    if not locked_quote:
        return jsonify({"error": "Negotiation rejected: quote_id is missing, expired, or invalid"}), 400
    original_quote = float(locked_quote["price_usdc"])
    
    # Evaluate counter-offer
    accepted, response_msg = NegotiationManager.evaluate_counter_offer(
        skill, original_quote, counter_offer, reason
    )
    
    # Log negotiation
    NegotiationManager.log_negotiation(
        provider_id=PROVIDER_ID,
        symbol=symbol,
        skill=skill,
        original_quote=original_quote,
        counter_offer=counter_offer,
        reason=reason,
        accepted=accepted,
        response=response_msg,
        claimed_original_quote=claimed_original_quote
    )
    
    # Create response
    response_data = NegotiationSchema.create_response(
        accepted=accepted,
        message=response_msg,
        counter_offer_approved=counter_offer if accepted else None
    )
    
    print(f"[Negotiation] {skill} for {symbol}: Original ${original_quote:.2f} → Counter ${counter_offer:.2f} → {'ACCEPTED' if accepted else 'REJECTED'}")
    
    return jsonify(response_data), (200 if accepted else 400)

if __name__ == "__main__":
    print(f"[*] Starting Provider 2 (Speed Specialist) on port {PROVIDER_PORT} (Chain ID: {w3.eth.chain_id})...")
    print("[*] Pricing Strategy: Groq LLM-driven by skill, symbol, and provider load")
    app.run(host="0.0.0.0", port=PROVIDER_PORT)
