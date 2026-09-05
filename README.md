# ⚡ Convergence Signal Provider (Binance Agent OS)

A decentralized, B2B Agent OS application that calculates high-probability market reversals and sells them to other trading agents via the Binance x402 payment protocol.

### 🏆 Track A: Build an AI agent with Agent OS

### 1. What is it?
The Convergence Signal Provider is an autonomous micro-business. Instead of trading directly, it acts as a data refinery for other agents. It synthesizes real-time retail social exhaustion (via Tavily) with stealth Layer 2 whale selling volume (via Binance MCP order books) to create a "Convergence Score."

### 2. Why is it needed?
Trading agents on the Binance Skill Hub need synthesized intelligence, not raw data. Downloading social context, running heavy NLP (TF-IDF), and scanning 50 levels of an order book is too slow for a high-frequency trading bot. Our agent does the heavy lifting and sells the calculated alpha instantly.

### 3. Who is it for?
This agent is built for **other AI agents**. It is designed to be listed on the Binance Skill Hub as a modular capability that other developers can plug into their trading workflows.

### 4. How does it work?
We natively integrate three pillars of the Agent OS ecosystem:
*   **Market Data (Binance MCP):** Connects to `https://agent.binance.com/mcp/agentic` to read live order book depth.
*   **Social Data (Tavily API):** Scrapes real-time retail hype to calculate mathematical social exhaustion using `scikit-learn` TF-IDF vectorization.
*   **Settlement (Binance x402 via Web3 API):** Gates the data behind a 0.50 USDC machine-to-machine micro-transaction.

### 🚀 How to Run Locally
1. Clone the repo and install dependencies: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your Binance/Tavily keys.
3. Start the Provider Server: `python app/app.py`
4. Run the simulated x402 Agent purchase: `python test_buyer.py`

## Architecture & Settlement Compliance Note
This implementation uses a **self-hosted x402 / EIP-3009 merchant architecture** deployed on **BNB Smart Chain (BSC Testnet, Chain ID 97)**. 
- Off-chain gasless signing uses standard EIP-712 typed authorizations ().
- Transactions are relayed and gas-settled on BSC Testnet by the provider node.
- Real-time market telemetry and reconnaissance are driven by the official **Binance Agent OS MCP Server** () with API fallback.
- Note for Hackathon Judges: Payments are processed via our self-hosted x402 smart contract primitive on BSC Testnet, not routed through a centralized Binance B402 custodial merchant account.
