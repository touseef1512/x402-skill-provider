import requests
import pandas as pd
import numpy as np
from typing import List, Dict, Any

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

def fetch_klines(symbol: str, interval: str = "1h", limit: int = 50) -> pd.DataFrame:
    """
    Fetches real historical candlestick (Kline) data from Binance Spot REST API.
    """
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit
    }
    
    response = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"Binance API error [{response.status_code}]: {response.text}")
        
    raw_data = response.json()
    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise ValueError(f"No kline data returned for symbol: {symbol}")
        
    records = []
    for candle in raw_data:
        records.append({
            "close_time": pd.to_datetime(candle[6], unit="ms"),
            "close": float(candle[4]),
            "volume": float(candle[5])
        })
        
    df = pd.DataFrame(records)
    df.set_index("close_time", inplace=True)
    return df


def analyze_correlation_break(
    target_symbol: str,
    benchmarks: List[str] = ["BTCUSDT", "ETHUSDT"],
    interval: str = "1h",
    lookback: int = 48,
    recent_window: int = 12
) -> Dict[str, Any]:
    """
    Pulls real price series for the target and benchmarks, calculates rolling returns,
    and checks if recent correlation has sharply decoupled from its baseline.
    """
    target_clean = target_symbol.upper()
    print(f"[*] Fetching {lookback} {interval} candles for {target_clean} and benchmarks {benchmarks}...")
    
    # 1. Pull target price data
    target_df = fetch_klines(target_clean, interval=interval, limit=lookback)
    price_series = {target_clean: target_df["close"]}
    
    # 2. Pull benchmark price data
    for b in benchmarks:
        b_clean = b.upper()
        b_df = fetch_klines(b_clean, interval=interval, limit=lookback)
        price_series[b_clean] = b_df["close"]
        
    # 3. Align timestamps and calculate percentage returns
    prices_df = pd.DataFrame(price_series).dropna()
    returns_df = prices_df.pct_change().dropna()
    
    if len(returns_df) < recent_window + 5:
        raise ValueError(f"Insufficient aligned returns: {len(returns_df)} periods available.")
        
    # Composite benchmark return (mean return of BTC + ETH)
    benchmark_returns = returns_df[[b.upper() for b in benchmarks]].mean(axis=1)
    target_returns = returns_df[target_clean]
    
    # 4. Statistical computations
    # Overall baseline Pearson correlation over the full period
    baseline_corr = float(target_returns.corr(benchmark_returns))
    
    # Recent correlation over the trailing `recent_window`
    recent_target = target_returns.tail(recent_window)
    recent_benchmark = benchmark_returns.tail(recent_window)
    recent_corr = float(recent_target.corr(recent_benchmark))
    
    # Handle NaN values if variance was 0 during low volatility
    baseline_corr = 0.0 if np.isnan(baseline_corr) else baseline_corr
    recent_corr = 0.0 if np.isnan(recent_corr) else recent_corr
    
    correlation_delta = recent_corr - baseline_corr
    
    # 5. Break condition:
    # Asset had positive baseline relationship (>= 0.35) and recent decoupled sharply (delta <= -0.30 or dropped below 0)
    break_detected = bool(baseline_corr >= 0.35 and (correlation_delta <= -0.30 or recent_corr < 0.0))
    
    return {
        "target_symbol": target_clean,
        "benchmarks": [b.upper() for b in benchmarks],
        "lookback_periods": len(returns_df),
        "interval": interval,
        "baseline_correlation": round(baseline_corr, 4),
        "recent_correlation": round(recent_corr, 4),
        "correlation_delta": round(correlation_delta, 4),
        "correlation_break_detected": break_detected,
        "latest_close": float(prices_df[target_clean].iloc[-1])
    }


if __name__ == "__main__":
    # Test on a real token against BTC & ETH
    test_target = "SOLUSDT"
    print(f"Testing real correlation-break logic for {test_target}...")
    result = analyze_correlation_break(test_target, benchmarks=["BTCUSDT", "ETHUSDT"])
    
    print("\n--- Result ---")
    for key, val in result.items():
        print(f"{key}: {val}")