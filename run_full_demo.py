"""Run the complete x402 hackathon demonstration in one command."""

import argparse
import json
import time
from pathlib import Path

import requests

from orchestrator_agent.multi_provider_marketplace import MultiProviderMarketplace
from orchestrator_agent.orchestrator import reason_and_procure

ROOT_DIR = Path(__file__).resolve().parent


def latest_record(path: Path, timestamp: int = None):
    """Return the most recently written record. `timestamp` is accepted for
    call-site compatibility but unused — matching on it was flaky (server and
    client clocks can tick a second apart), and the log is append-only, so the
    last entry is always the freshest one."""
    records = json.loads(path.read_text())
    return records[-1]

def run_demo(symbol: str, total_budget: float):
    print("\n" + "=" * 80)
    print("FULL x402 DEMO: MARKETPLACE -> NEGOTIATION -> PURCHASE FLOW")
    print("=" * 80)

    marketplace = MultiProviderMarketplace(symbol)
    if not marketplace.request_quotes_from_all_providers():
        raise RuntimeError("Marketplace did not receive a quote for every skill")
    marketplace.log_comparison_table()
    marketplace.print_marketplace_summary()

    quote = marketplace.quotes["provider1_standard"]["news_risk"]
    original_quote = float(quote["price"])
    counter_offer = round(original_quote * 0.95, 2)
    negotiation_payload = {
        "quote_id": quote["quote_id"],
        "symbol": symbol,
        "skill": "news_risk",
        "original_quote_usdc": original_quote,
        "counter_offer_usdc": counter_offer,
        "reason": "Live demo budget constraint; requesting a 5% one-round discount.",
    }

    print("\n" + "=" * 80)
    print("NEGOTIATION: POSTING LIVE COUNTER-OFFER TO PROVIDER 1")
    print("=" * 80)
    print(json.dumps(negotiation_payload, indent=2))
    negotiation_response = requests.post(
        "http://127.0.0.1:5000/api/negotiate",
        json=negotiation_payload,
        timeout=10,
    )
    print(f"HTTP {negotiation_response.status_code}")
    print(json.dumps(negotiation_response.json(), indent=2))
    if negotiation_response.status_code not in (200, 400):
        raise RuntimeError(f"Negotiation request failed: {negotiation_response.text}")

    negotiation_path = ROOT_DIR / "negotiation_history.json"
    negotiation_record = latest_record(negotiation_path, int(time.time()))
    print("Fresh negotiation_history.json entry:")
    print(json.dumps(negotiation_record, indent=2))

    marketplace_path = ROOT_DIR / "marketplace_comparison.json"
    marketplace_record = latest_record(marketplace_path, marketplace.comparison_log["timestamp"])
    print("Fresh marketplace_comparison.json entry:")
    print(json.dumps(marketplace_record, indent=2))

    print("\n" + "=" * 80)
    print("PURCHASE FLOW: CALLING EXISTING reason_and_procure()")
    print("=" * 80)
    reason_and_procure(
        symbol,
        total_budget=total_budget,
        selected_providers=marketplace.selected_providers,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--budget", type=float, default=2.00)
    args = parser.parse_args()
    run_demo(args.symbol, args.budget)
