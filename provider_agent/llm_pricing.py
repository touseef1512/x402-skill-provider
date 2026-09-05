"""LLM-driven provider pricing and provider-side reasoning receipts."""

import hashlib
import json
import math
import os
import time
from pathlib import Path

from groq import Groq

ROOT_DIR = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT_DIR / "purchase_ledger.json"


def _client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from environment")
    return Groq(api_key=api_key)


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read {path.name}: {exc}") from exc


def quote_price(skill, symbol, provider_id, specialty, signals):
    """Ask Groq for a price and short rationale; never fall back silently."""
    prompt = f"""You are the pricing controller for {provider_id}, a {specialty}.
Set one fair USDC price for the requested paid intelligence skill.

Skill: {skill}
Symbol: {symbol}
Current provider demand/load signals: {json.dumps(signals, sort_keys=True)}

Price within these protocol limits: 0.01 to 2.00 USDC.
Return only valid JSON with exactly these fields:
{{"price_usdc": number, "reasoning": "short explanation"}}
The reasoning must mention the skill, symbol, and at least one supplied demand/load signal.
"""
    try:
        response = _client().chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            timeout=15,
        )
        result = json.loads(response.choices[0].message.content)
        price = float(result["price_usdc"])
        reasoning = str(result["reasoning"]).strip()
    except Exception as exc:
        raise RuntimeError(f"LLM pricing failed for {provider_id}/{skill}/{symbol}: {exc}") from exc

    if not math.isfinite(price) or not 0.01 <= price <= 2.00:
        raise RuntimeError(f"LLM pricing returned invalid price for {provider_id}/{skill}: {price!r}")
    if not reasoning:
        raise RuntimeError(f"LLM pricing returned empty reasoning for {provider_id}/{skill}")

    return round(price, 2), reasoning


def demand_signals(quote_cache, provider_id, extra=None):
    now = time.time()
    active_quotes = sum(1 for quote in quote_cache.values() if quote["expires_at"] > now)
    signals = {
        "active_quotes": active_quotes,
        "quote_cache_size": len(quote_cache),
        "provider_id": provider_id,
    }
    if extra:
        signals.update(extra)
    return signals


def record_provider_receipt(provider_id, symbol, skill, price, tx_hash, reasoning):
    """Append a provider pricing receipt to the shared purchase ledger."""
    if not tx_hash:
        raise RuntimeError("Cannot record provider reasoning without a transaction hash")
    normalized_hash = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
    ledger = _load_json(LEDGER_PATH, [])
    ledger.append({
        "purchase_id": f"provider_{normalized_hash[2:18]}",
        "timestamp": int(time.time()),
        "symbol": symbol,
        "skill": skill,
        "paid_usdc": price,
        "entry_price": None,
        "tx_hash": normalized_hash,
        "reasoning_hash": hashlib.sha256(reasoning.encode()).hexdigest(),
        "reasoning_preview": reasoning[:100],
        "provider": provider_id,
        "receipt_type": "provider_pricing",
    })
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))
