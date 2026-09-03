import requests
from typing import Dict, Any

BINANCE_24HR_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"

def fetch_free_binance_signal(symbol: str) -> Dict[str, Any]:
    """
    Pulls real-time 24hr market data from the public Binance REST API.
    Acts as the free baseline skill for the Orchestrator agent.
    """
    clean_symbol = symbol.upper()
    params = {"symbol": clean_symbol}
    
    print(f"[*] Fetching free baseline market signal for {clean_symbol} from Binance...")
    response = requests.get(BINANCE_24HR_TICKER_URL, params=params, timeout=10)
    
    if response.status_code != 200:
        raise RuntimeError(f"Binance 24hr API error [{response.status_code}]: {response.text}")
        
    data = response.json()
    
    last_price = float(data.get("lastPrice", 0.0))
    price_change_pct = float(data.get("priceChangePercent", 0.0))
    quote_volume = float(data.get("quoteVolume", 0.0))  # Volume in USDT
    vwap = float(data.get("weightedAvgPrice", 0.0))
    high_price = float(data.get("highPrice", 0.0))
    low_price = float(data.get("lowPrice", 0.0))
    
    # Simple heuristic baseline momentum signal
    if price_change_pct > 3.0 and last_price >= vwap:
        baseline_bias = "BULLISH"
    elif price_change_pct < -3.0 and last_price <= vwap:
        baseline_bias = "BEARISH"
    else:
        baseline_bias = "NEUTRAL"
        
    return {
        "symbol": clean_symbol,
        "last_price": last_price,
        "price_change_percent_24h": round(price_change_pct, 2),
        "quote_volume_24h_usdt": round(quote_volume, 2),
        "weighted_avg_price": round(vwap, 4),
        "range_24h": {
            "high": high_price,
            "low": low_price
        },
        "baseline_bias": baseline_bias,
        "cost_usdc": 0.0
    }


if __name__ == "__main__":
    test_symbol = "SOLUSDT"
    print(f"Testing free Binance signal skill for {test_symbol}...")
    result = fetch_free_binance_signal(test_symbol)
    
    print("\n--- Free Baseline Signal ---")
    for k, v in result.items():
        print(f"{k}: {v}")