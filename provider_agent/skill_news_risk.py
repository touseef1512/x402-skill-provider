import os
import re
from typing import Dict, Any, List
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

# Disambiguation dictionary for tickers commonly prone to collision
ASSET_NAME_MAP = {
    "SOL": "Solana",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "BNB": "BNB Chain",
    "DUSK": "Dusk Network",
    "AVAX": "Avalanche",
    "NEAR": "NEAR Protocol",
    "ADA": "Cardano",
    "DOT": "Polkadot",
    "MATIC": "Polygon",
    "POL": "Polygon"
}

# Weighted risk indicators
HIGH_RISK_TERMS = {
    "exploit": 0.35,
    "hack": 0.35,
    "drain": 0.35,
    "rugpull": 0.40,
    "rug pull": 0.40,
    "sec lawsuit": 0.35,
    "indictment": 0.35,
    "insolvent": 0.35,
    "subpoena": 0.30,
    "arrest": 0.30,
    "freeze": 0.25,
    "stolen": 0.30
}

MEDIUM_RISK_TERMS = {
    "investigation": 0.15,
    "vulnerability": 0.15,
    "outage": 0.15,
    "network halt": 0.25,
    "downtime": 0.15,
    "fine": 0.15,
    "probe": 0.15,
    "warning": 0.10,
    "delisting": 0.20
}

CRYPTO_CONTEXT_WORDS = [
    "crypto", "cryptocurrency", "blockchain", "token", "defi", "web3", "wallet", "smart contract", "mainnet"
]

def clean_symbol(symbol: str) -> str:
    """Strips common quote currencies from pair strings."""
    clean = symbol.upper()
    for quote in ["USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH"]:
        if clean.endswith(quote) and len(clean) > len(quote):
            return clean[:-len(quote)]
    return clean

def get_asset_identifiers(base_asset: str) -> List[str]:
    """Returns aliases for entity recognition."""
    full_name = ASSET_NAME_MAP.get(base_asset, base_asset)
    identifiers = [base_asset.lower()]
    if full_name.lower() != base_asset.lower():
        identifiers.append(full_name.lower())
    return identifiers

def is_article_relevant(text: str, identifiers: List[str]) -> bool:
    """
    Validates that the article actually mentions the target entity AND 
    has crypto context, preventing unrelated enterprise IT false positives.
    """
    text_lower = text.lower()
    
    # 1. Must mention the target asset identifier
    has_entity = any(re.search(r"\b" + re.escape(name) + r"\b", text_lower) for name in identifiers)
    if not has_entity:
        return False
        
    # 2. Must contain crypto context
    has_crypto_context = any(re.search(r"\b" + re.escape(word) + r"\b", text_lower) for word in CRYPTO_CONTEXT_WORDS)
    return has_crypto_context

def analyze_news_risk(symbol: str, lookback_days: int = 2) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or api_key == "your_tavily_key_here":
        raise ValueError("TAVILY_API_KEY is missing or unconfigured in .env")

    tavily = TavilyClient(api_key=api_key)
    base_asset = clean_symbol(symbol)
    full_name = ASSET_NAME_MAP.get(base_asset, base_asset)
    identifiers = get_asset_identifiers(base_asset)

    # Disambiguated query targeting crypto and the actual asset name
    query = f'"{full_name}" crypto (exploit OR hack OR lawsuit OR outage OR vulnerability OR "sec")'
    print(f"[*] Dispatching disambiguated Tavily scan for: {full_name} ({base_asset})...")

    try:
        response = tavily.search(
            query=query,
            topic="news",
            days=lookback_days,
            max_results=5
        )
    except Exception as e:
        print(f"[!] Topic search fallback: {e}")
        response = tavily.search(query=query, max_results=5)

    results = response.get("results", [])
    accumulated_risk = 0.0
    flagged_signals: List[str] = []
    evidence: List[Dict[str, Any]] = []
    relevant_articles_count = 0

    for item in results:
        title = item.get("title", "")
        content = item.get("content", "")
        url = item.get("url", "")
        full_text = f"{title} {content}"

        # Relevance gate: Ignore unrelated news
        if not is_article_relevant(full_text, identifiers):
            continue

        relevant_articles_count += 1
        matched_for_article = []
        text_lower = full_text.lower()

        for term, weight in HIGH_RISK_TERMS.items():
            if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
                accumulated_risk += weight
                matched_for_article.append(term)
                if term not in flagged_signals:
                    flagged_signals.append(term)

        for term, weight in MEDIUM_RISK_TERMS.items():
            if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
                accumulated_risk += weight
                matched_for_article.append(term)
                if term not in flagged_signals:
                    flagged_signals.append(term)

        evidence.append({
            "title": title,
            "url": url,
            "snippet": content[:180] + "..." if len(content) > 180 else content,
            "matched_terms": matched_for_article
        })

    normalized_score = min(round(accumulated_risk, 2), 1.0)

    if normalized_score >= 0.70:
        risk_level = "CRITICAL"
    elif normalized_score >= 0.40:
        risk_level = "HIGH"
    elif normalized_score >= 0.20:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "symbol": symbol,
        "base_asset": base_asset,
        "full_name": full_name,
        "raw_results_returned": len(results),
        "relevant_articles_analyzed": relevant_articles_count,
        "risk_score": normalized_score,
        "risk_level": risk_level,
        "flagged_signals": flagged_signals,
        "evidence": evidence
    }


if __name__ == "__main__":
    test_symbol = "SOLUSDT"
    print(f"Testing disambiguated news risk skill for {test_symbol}...")
    report = analyze_news_risk(test_symbol, lookback_days=2)

    print("\n--- News Risk Report ---")
    print(f"Asset: {report['full_name']} ({report['symbol']})")
    print(f"Relevant Articles Evaluated: {report['relevant_articles_analyzed']} (Filtered from {report['raw_results_returned']})")
    print(f"Risk Score: {report['risk_score']} | Level: {report['risk_level']}")
    print(f"Flagged Terms: {report['flagged_signals']}")
    if report["evidence"]:
        print("\nRelevant Evidence:")
        for ev in report["evidence"][:2]:
            print(f"- {ev['title']}")
            print(f"  Matches: {ev['matched_terms']}")