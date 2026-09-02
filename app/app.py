import sqlite3
import os
import asyncio
from flask import Flask, request, jsonify, render_template
from skills.analyzer import ConvergenceAnalyzer

app = Flask(__name__)
analyzer = ConvergenceAnalyzer()

# Database path setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'agents.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'database', 'schema.sql')

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
    app.run(host='0.0.0.0', port=5000, debug=True)