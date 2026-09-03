import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from b402_merchant import (
    create_payment_requirements,
    verify_eip712_payment_signature
)
from skill_correlation import analyze_correlation_break
from skill_news_risk import analyze_news_risk
from settlement import PaymentSettlementEngine

load_dotenv()

app = Flask(__name__)
settlement_engine = PaymentSettlementEngine()
USED_NONCES = set()

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "agent": "The Analyst Skill Provider",
        "status": "online",
        "network": "eip155:97",
        "paid_skills": {
            "/api/skills/correlation": "0.50 USDC",
            "/api/skills/news-risk": "0.50 USDC"
        }
    }), 200

@app.route("/api/skills/correlation", methods=["POST"])
def skill_correlation_endpoint():
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "SOLUSDT")
    payment_payload = data.get("payment")

    if not payment_payload:
        requirements = create_payment_requirements("correlation_break", price_usdc=0.50)
        return jsonify({
            "error": "Payment Required",
            "message": "Resource requires 0.50 USDC via x402 payment authorization.",
            "paymentRequirements": requirements
        }), 402

    nonce = payment_payload.get("authorization", {}).get("nonce")
    if not nonce or nonce in USED_NONCES:
        return jsonify({"error": "Payment Rejected: Nonce missing or already redeemed."}), 400

    expected_reqs = create_payment_requirements("correlation_break", price_usdc=0.50)
    expected_reqs["nonce"] = nonce

    is_valid, signer_or_reason = verify_eip712_payment_signature(payment_payload, expected_reqs)
    if not is_valid:
        return jsonify({"error": "Payment Verification Failed", "details": signer_or_reason}), 403

    USED_NONCES.add(nonce)
    print(f"[*] Verified x402 payment from: {signer_or_reason}")

    # Settle payment payload via settlement engine (passes token address)
    settlement_result = settlement_engine.settle_payment(
        payment_payload, 
        token_address=expected_reqs["token"]
    )

    try:
        result = analyze_correlation_break(symbol)
        return jsonify({
            "status": "success",
            "paid_to": expected_reqs["payTo"],
            "payer": signer_or_reason,
            "settlement": settlement_result,
            "data": result
        }), 200
    except Exception as e:
        return jsonify({"error": f"Execution error: {str(e)}"}), 500


@app.route("/api/skills/news-risk", methods=["POST"])
def skill_news_risk_endpoint():
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "SOLUSDT")
    payment_payload = data.get("payment")

    if not payment_payload:
        requirements = create_payment_requirements("news_risk", price_usdc=0.50)
        return jsonify({
            "error": "Payment Required",
            "message": "Resource requires 0.50 USDC via x402 payment authorization.",
            "paymentRequirements": requirements
        }), 402

    nonce = payment_payload.get("authorization", {}).get("nonce")
    if not nonce or nonce in USED_NONCES:
        return jsonify({"error": "Payment Rejected: Nonce missing or already redeemed."}), 400

    expected_reqs = create_payment_requirements("news_risk", price_usdc=0.50)
    expected_reqs["nonce"] = nonce

    is_valid, signer_or_reason = verify_eip712_payment_signature(payment_payload, expected_reqs)
    if not is_valid:
        return jsonify({"error": "Payment Verification Failed", "details": signer_or_reason}), 403

    USED_NONCES.add(nonce)
    print(f"[*] Verified x402 payment from: {signer_or_reason}")

    # Settle payment payload via settlement engine (passes token address)
    settlement_result = settlement_engine.settle_payment(
        payment_payload, 
        token_address=expected_reqs["token"]
    )

    try:
        result = analyze_news_risk(symbol)
        return jsonify({
            "status": "success",
            "paid_to": expected_reqs["payTo"],
            "payer": signer_or_reason,
            "settlement": settlement_result,
            "data": result
        }), 200
    except Exception as e:
        return jsonify({"error": f"Execution error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)