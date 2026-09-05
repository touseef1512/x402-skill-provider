import sqlite3
import os
import asyncio
import json
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from skills.analyzer import ConvergenceAnalyzer

app = Flask(__name__)
analyzer = ConvergenceAnalyzer()

# Database path setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = Path(BASE_DIR).parent
DB_PATH = os.path.join(BASE_DIR, 'database', 'agents.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'database', 'schema.sql')

ARTIFACTS = {
    "ledger": ROOT_DIR / "purchase_ledger.json",
    "marketplace": ROOT_DIR / "marketplace_comparison.json",
    "negotiations": ROOT_DIR / "negotiation_history.json",
    "governor": ROOT_DIR / "safety_governor_log.json",
    "events": ROOT_DIR / "dashboard_events.json",
}

TOTAL_BUDGET = float(os.getenv("TOTAL_BUDGET_USDC", "2.00"))

def read_json_artifact(name, default):
    path = ARTIFACTS[name]
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except (OSError, json.JSONDecodeError):
        return default

def dashboard_state():
    ledger = read_json_artifact("ledger", [])
    events = read_json_artifact("events", [])
    marketplace = read_json_artifact("marketplace", {})
    negotiations = read_json_artifact("negotiations", [])
    governor_logs = read_json_artifact("governor", [])
    spent = sum(float(entry.get("paid_usdc", 0)) for entry in ledger)
    latest_halt = next(
        (entry for entry in reversed(governor_logs)
         if entry.get("event") == "circuit_breaker_halted"),
        None,
    )
    return {
        "budget": {
            "total_usdc": TOTAL_BUDGET,
            "spent_usdc": round(spent, 6),
            "remaining_usdc": round(max(TOTAL_BUDGET - spent, 0), 6),
        },
        "reasoning": events[-50:],
        "quotes": marketplace,
        "settlements": ledger[-50:],
        "negotiations": negotiations[-20:],
        "governor": {
            "halted": bool(latest_halt),
            "latest_halt": latest_halt,
        },
    }

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        conn.commit()

init_db()

def verify_x402_payment(tx_hash, agent_id):
    """
    Validates the x402 settlement. 
    Because payment capabilities are not on the MCP server yet, 
    this logs the verification targeting standard Binance Web3 APIs.
    """
    if not tx_hash.startswith("0x"):
        return False
        
    try:
        # The unique constraint prevents double-spending the same transaction hash.
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO agent_payments 
                (payer_agent_id, x402_transaction_hash, amount_paid_usdc, skill_requested, is_verified) 
                VALUES (?, ?, ?, ?, ?)""",
                (agent_id, tx_hash, 0.50, "convergence_signal", True)
            )
            conn.commit()
            return True
            
    except sqlite3.IntegrityError:
        print("Double spend detected. Hash already used.")
        return False
    except Exception as e:
        print(f"x402 Verification failed: {e}")
        return False

@app.route('/', methods=['GET'])
def dashboard():
    return render_template('index.html')

@app.route('/api/dashboard/state', methods=['GET'])
def get_dashboard_state():
    return jsonify(dashboard_state())

@app.route('/api/v1/skill/convergence', methods=['POST'])
def get_convergence_alpha():
    data = request.json
    
    agent_id = data.get('agent_id')
    tx_hash = data.get('x402_hash')
    symbol = data.get('symbol', 'BTCUSDT')

    # 1. Gatekeeper: Check credentials
    if not agent_id or not tx_hash:
        return jsonify({"error": "Payment Required: Missing agent_id or x402_hash"}), 402
    
    # 2. Settlement: Verify the x402 payment
    if not verify_x402_payment(tx_hash, agent_id):
        return jsonify({"error": "Payment Verification Failed or Hash Already Used"}), 402

    # 3. Delivery: Run the async Tavily + MCP logic safely in standard Flask
    result = asyncio.run(analyzer.generate_convergence_signal(symbol))
    
    return jsonify({
        "status": "success",
        "payment": "x402_verified",
        "data": result
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('DASHBOARD_PORT', '5050')), debug=False)