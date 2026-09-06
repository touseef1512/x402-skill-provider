# Convergence Signal Provider

Binance Agent OS Mini Hackathon, Track A (Payment Workflows / agent-to-agent payments)

## What this is

Two kinds of AI agents that buy and sell market intelligence from each other, with no human approving the transaction.A buyer agent (the Analyst) decides what data it needs and how much to spend. Three provider agents each sell the same three skills at their own price, set by their own LLM call, not a lookup table. The buyer compares all three, negotiates with the winner if it wants, and pays on-chain with a gasless EIP-3009 authorization. Everything either agent decides is logged with a hash of its reasoning, so you can check after the fact that the number it paid actually matches what it said it was doing.

The idea is a data refinery, not a trading bot. It doesn't trade. It buys risk signals (news exposure, correlation breakdown vs BTC, smart-contract forensic findings) and turns them into a stance and a confidence number, the same way a junior analyst would pull three reports before writing a note.

| Skill | What it does | Data source |
|---|---|---|
| **Rapid News Exploit & Lawsuit Scanner** | Scans for breaking hacks, exploits, or regulatory action tied to the asset, right now, not a cached digest. | Tavily live search, filtered against a real risk-term list (exploit, breach, lawsuit, investigation, etc.) |
| **Cross-Asset Correlation Break Detector** | Flags when an asset stops moving with BTC, the kind of decoupling that usually means something asset-specific is going on. | Real Binance kline data, Pearson correlation + realized volatility computed against BTC on the fly |
| **Deep Smart-Contract Forensic Risk Auditor** | Pulls known audit findings and exploit vectors for the asset's ecosystem: reentrancy, flash-loan surfaces, governance anomalies. | Live search against audit reports and incident writeups |

Three providers sell all three skills. They don't collude on price, Standard, Speed Specialist, and Value Hunter each run their own pricing model with their own demand signals, so the same skill can and does come back at three different prices in the same run. The buyer sees all three quotes side by side before deciding who to pay.
## What's real here and what isn't

Being upfront about this because it matters for judging:

- Settlement is real. It's an actual `transferWithAuthorization` (EIP-3009) call on BSC Testnet, signed with EIP-712, verified and relayed by the provider server. Every purchase in `purchase_ledger.json` has a real on-chain tx hash you can look up on BscScan.
- Pricing is real, not scripted. Each provider calls Groq independently to set its own price per quote, based on its own demand signals. Prices genuinely move between runs, you'll see this if you run the demo twice.
- The buyer's procurement decision is a real LLM call reasoning over live market data (price, volume, and whichever risk skills fit the budget), not a fixed script.
- The multi-provider marketplace actually decides where the money goes. The comparison table isn't decorative, the purchase step reads whichever provider the comparison picked and buys from that port.
- The negotiation step checks its own locked quote server-side. It doesn't trust whatever "original price" the buyer claims in the request. I specifically tested this by lying about the original price in a raw request and confirmed the server ignored the lie and used its own record.

What's NOT real, and I'd rather say so than have a judge find it:

- This does not use Binance's official Agent OS MCP server for live data. It tries to but The MCP endpoint (`agent.binance.com/mcp/agentic`) is gated behind an OAuth flow with a small allowlist of approved clients (Claude Code, ChatGPT, Copilot, etc.), a custom script gets a flat 401. I looked into working around that and decided against it; it isn't something Track A actually requires (Track A's requirement is the broader Agent OS toolkit: REST APIs, Wallet Agentic Hub, x402, Skill Hub, not MCP specifically), and getting around an API gate that exists on purpose felt like the wrong instinct even if it were possible. So the client tries the MCP handshake first, logs exactly why it failed, and falls back to Binance's public REST API. You'll see this in every run's output, it's not hidden.
- The x402 payment protocol here is self-hosted, running on my own MockUSDC contract and my own settlement server. It is not Binance's native B402 custodial merchant service. I'm calling this out explicitly because the two are easy to conflate and I don't want anyone assuming this is wired into Binance's actual payment rail.

## Architecture
Buyer (orchestrator_agent/)
-> queries baseline market data (Binance MCP, falls back to REST)
-> Groq decides which skills are worth buying within budget
-> gets quotes from all 3 providers, picks best value per skill
-> optionally negotiates a discount with the winning provider
-> signs an EIP-712 payment authorization, submits it
-> provider verifies + settles on-chain, returns the data
-> buyer synthesizes everything into a final read (Groq again)

## The catalog

This is what's actually for sale. Each one is a real skill call, not a stub, the data backing it is live, and the price attached to it changes every time you ask, because each provider is pricing it fresh with its own LLM call rather than reading off a price sheet.

## Security stuff worth knowing about

- Payment authorizations use canonical low-s ECDSA signatures, the contract explicitly rejects the malleable high-s form. There's a real test for this (`test_security_audit.py`) that signs both forms and checks the contract accepts one and reverts the other, rather than just asserting a constant equals itself.
- There's a circuit breaker (`safety_governor.py`) that the buyer checks before every purchase.
- `rogue_provider_demo.py` demonstrates what happens when a provider tries to misbehave.
- Every purchase and every price gets a SHA-256 hash of the reasoning behind it logged alongside the payment, so the reasoning can be checked for tampering without publishing the full text of every LLM call.

## Running it

You'll need a BSC Testnet RPC, a funded buyer/provider wallet pair (testnet BNB + the deployed MockUSDC), and API keys for Groq, Tavily, and Binance (the Binance key only needs read scope, nothing here trades or transfers on your Binance account).

```bash
cp .env.example .env
# fill in your keys and wallet details

pip install -r requirements.txt

./start_providers.sh
# starts all three providers on 5000/5001/5002

python3 run_full_demo.py
# runs the full marketplace -> negotiation -> purchase -> synthesis flow
```

Deployed MockUSDC contract on BSC Testnet: `0x4205B5506538b1D3c0600ACf241DCCCa416D0Fa6`

One thing that'll bite you if you don't know it: the provider servers don't auto-reload on code changes (debug mode is intentionally off, since leaving it on is a real exposure risk). If you edit anything in `provider_agent/` or `orchestrator_agent/`, kill and restart the provider processes before testing again, or you'll be testing stale code without realizing it.

```bash
lsof -ti:5000 | xargs kill -9
lsof -ti:5001 | xargs kill -9
lsof -ti:5002 | xargs kill -9
./start_providers.sh
```

## Watching it happen

There's also a live dashboard at `python app/app.py` (port 5050 by default), it polls the same JSON files the demo writes to, every 3 seconds, so you can watch the budget drain, quotes come in from all three providers, negotiation results land, and settlements confirm with real tx hashes, without staring at terminal output. Same data, easier to read.

## What I'd build next if I had more time

- A second buyer agent, so providers are also competing for scarce buyer attention, not just the other way around
- Tying the negotiation floor to something more principled than a flat percentage of the quote
- Actual persistent OAuth support for the real Agent OS MCP server, if Anthropic-class clients ever become an accessible option for this kind of project

## Sample run (real, unedited output)
Providers (provider_agent/)

provider1_standard (port 5000)
provider2_speed (port 5001)
provider3_value (port 5002)
each independently prices news_risk / correlation_break / deep_forensic_risk
via its own Groq call, and settles payment on receipt of a valid authorization
MULTI-PROVIDER MARKETPLACE: FETCHING QUOTES FROM ALL PROVIDERS
[Provider: Standard (Port 5000)] news_risk: $0.05 | correlation_break: $0.45 | deep_forensic_risk: $0.75
[Provider: Speed Specialist (Port 5001)] news_risk: $0.05 | correlation_break: $0.15 | deep_forensic_risk: $0.45
[Provider: Value Hunter (Port 5002)] news_risk: $0.05 | correlation_break: $0.45 | deep_forensic_risk: $0.45

NEGOTIATION: POSTING LIVE COUNTER-OFFER TO PROVIDER 1
{ "original_quote_usdc": 0.05, "counter_offer_usdc": 0.05, "reason": "Live demo budget constraint..." }
HTTP 200 -> { "status": "accepted", "message": "Counter-offer accepted." }

BINANCE AGENT OS MCP TELEMETRY & TRANSPORT REPORT
Served via MCP : 0 (0.0%)
Served via Fallback: 2
Transport State : DEGRADED (REST Fallback) <- expected, see "What's real here and what isn't" above

PHASE 1: AUTONOMOUS BUDGET REASONING (Groq, GPT-OSS 120B)
[Procurement Decision]: ['news_risk', 'correlation_break']

PHASE 2: AUTONOMOUS x402 COMMERCE EXECUTION
[Buyer] 402 Received! Required: 0.45 USDC on eip155:97
[Buyer] Submitting cryptographically signed EIP-712 authorization...
[Buyer] Payment verified on-chain (200 OK)! Intelligence unlocked.
[OK] Circuit breaker check passed
-> Tx Hash: 0xc9b76b1753f5e99fe49d81e28e31f34651ac967d983f1149e7fdd5a3acf6a8ee

PHASE 3: FINAL SYNTHESIS & ALPHA GENERATION (Groq, GPT-OSS 120B)
STANCE: BEARISH | CONFIDENCE: ~55%
[Full reasoning: correlation with BTC 0.76 (no break detected), 4 recent (this-week)
exploit/hack articles genuinely referencing Ethereum, risk score 1.0 CRITICAL,
position sizing and stop-loss levels generated from live data.]
