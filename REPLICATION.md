# Replication Guide

This walks through running the project from a completely clean environment  the same steps I used to verify it myself in a brand new GitHub Codespace.

## What you'll need before starting

- A BSC Testnet RPC endpoint (the public one in `.env.example` works, or use your own)
- A wallet with testnet BNB (for gas) and testnet USDC on the deployed MockUSDC contract
- API keys: Groq, Tavily, and a Binance API key (read-only scope is enough — nothing here trades or transfers on your Binance account)

**On the wallet funding**: this is the part most likely to trip you up if you're setting this up fresh rather than reusing mine. The buyer wallet needs both testnet BNB to pay gas and testnet USDC to actually settle the x402 payments. If you don't already have a funded testnet wallet, reach out to me and I'll either fund an address for you or point you to how to mint test USDC against the deployed contract. Without funded wallets, everything up through the marketplace comparison and negotiation steps will still work — it's only the actual on-chain settlement step that needs real (testnet) funds.

## Setup

```bash
git clone https://github.com/touseef1512/x402-skill-provider
cd x402-skill-provider

cp .env.example .env
# open .env and fill in your RPC URL, wallet keys/addresses, and API keys
# the USDC contract address is already deployed, you don't need to redeploy it:
# 0x4205B5506538b1D3c0600ACf241DCCCa416D0Fa6

pip install -r requirements.txt
```

## Running it

Start the three provider servers first:

```bash
./start_providers.sh
```

You should see all three confirm as running on ports 5000, 5001, and 5002. If you see a line about `venv/bin/activate: No such file or directory`, that's harmless — ignore it, it's just the script checking for a virtual environment that may not exist in your setup, and it doesn't stop the providers from starting.

Then run the full demo:

```bash
python3 run_full_demo.py
```

This runs the whole flow end to end: all three providers quote independently, the marketplace compares them, one negotiation round happens with the winning provider, the buyer reasons about what to purchase within its budget, real on-chain settlements happen, and a final synthesized read gets generated.

## Watching it live (optional)

In a separate terminal:

```bash
python3 app/app.py
```

Then open the forwarded port 5050 in your browser. This shows the same data as the terminal output, but as a dashboard you can watch update in real time while `run_full_demo.py` runs.

## If something doesn't restart correctly

The provider servers don't auto-reload when you change code (debug mode is intentionally off). If you're modifying anything and re-testing, kill and restart them first:

```bash
lsof -ti:5000 | xargs kill -9
lsof -ti:5001 | xargs kill -9
lsof -ti:5002 | xargs kill -9
./start_providers.sh
```

## What "working" looks like

A clean run ends with a synthesized BEARISH/BULLISH stance and confidence score for whatever symbol you ran it against (default is SOLUSDT), with 2-3 real on-chain settlements logged in `purchase_ledger.json`, each with a real transaction hash you can look up on BscScan Testnet.